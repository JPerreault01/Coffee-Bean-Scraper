# scrapers/resolvers/_playwright.py
"""
Optional Playwright price fallback — the last tier in the price chain.

Only used when a chromium binary is actually installed (binary_exists()), and
only after the requests-based tiers (Shopify JSON, JSON-LD/meta) have failed on
a JS-heavy roaster page. Playwright imports are deferred into the functions so
this module stays import-cheap when Playwright is absent.
"""

from __future__ import annotations

import re
from pathlib import Path

import json as _json

from ._http import USER_AGENT, _parse_price, _is_product_node, _price_from_offers, _iter_jsonld_nodes

# Common roaster price selectors (Shopify/Woo themes), most-specific first.
ROASTER_PRICE_SELECTORS = (
    "[itemprop='price']",
    "meta[property='product:price:amount']",
    ".price__current .money",
    ".price-item--regular",
    ".product__price .money",
    ".product-single__price",
    "[data-product-price]",
    ".product-price",
    ".price .money",
    ".price",
    # Broad fallback for custom storefronts (Blue Bottle, Intelligentsia, Onyx)
    # whose class names contain "price" as a substring (.price only matches the
    # literal standalone class token, not compound names like "product-price").
    "[class*=price]",
)


def binary_exists() -> bool:
    """True only if a chromium binary is installed (reused detection pattern
    from fetch_bean_images.py)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"\d[\d,]*\.?\d*", str(text).replace(",", ""))
    if not m:
        return None
    try:
        val = float(m.group())
        return val if val > 0 else None
    except ValueError:
        return None


def _extract_jsonld_price(page) -> float | None:
    """Pull JSON-LD blocks out of the live DOM (catches SPA-injected structured
    data that requests never sees). Returns the first Product Offer price found."""
    try:
        texts = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'script[type=\"application/ld+json\"]'))"
            ".map(s => s.textContent || '')"
        )
    except Exception:
        return None
    # Stitch into a fake HTML wrapper so the existing parser handles it.
    fake_html = "".join(
        f'<script type="application/ld+json">{t}</script>' for t in (texts or [])
    )
    for node in _iter_jsonld_nodes(fake_html):
        if _is_product_node(node):
            price = _price_from_offers(node.get("offers"))
            if price:
                return price
    return None


def get_price(url: str, *, timeout: int = 25000) -> float | None:
    """Render the page, then try JSON-LD extraction (catches SPA-injected
    structured data) before falling back to DOM selectors. Returns None if
    nothing parses. Raises on a Playwright/transport error so the resolver
    can retry."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            ctx = browser.new_context(
                user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-US"
            )
            page = ctx.new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            # Give React/Next.js storefronts time to hydrate and inject JSON-LD.
            page.wait_for_timeout(3000)

            # Tier A: JSON-LD from the live DOM (catches SPA-injected data).
            price = _extract_jsonld_price(page)
            if price:
                return price

            # Tier B: DOM selectors for standard Shopify/Woo themes.
            for sel in ROASTER_PRICE_SELECTORS:
                try:
                    el = page.query_selector(sel)
                except Exception:
                    continue
                if not el:
                    continue
                raw = el.get_attribute("content") or el.get_attribute("data-product-price")
                if not raw:
                    try:
                        raw = el.inner_text()
                    except Exception:
                        raw = None
                price = _parse_price(raw)
                if price:
                    return price
            return None
        finally:
            browser.close()
