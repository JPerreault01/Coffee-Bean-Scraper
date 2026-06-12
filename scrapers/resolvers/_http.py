# scrapers/resolvers/_http.py
"""
requests-based scrape helpers — og:image, roaster price, Amazon page scrape.

Canonical home for the og:image extraction and roaster-fetch logic that used
to live in fetch_bean_images.py, plus a requests-first roaster *price*
extractor (JSON-LD Offer / og:price / microdata) that replaces the Playwright
price path in price_scraper.py for the common Shopify/Woo case.

Every public fetch here raises on a transport error (so fetch_with_retry can
retry) and returns None for "fetched fine, nothing found". robots.txt is not
consulted: fetching a product's own page for price/image display is legitimate
one-off use, not crawling.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..url_filters import is_skippable_url  # noqa: F401 — re-exported for callers

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

WAYTOCOFFEE_BASE = "https://www.waytocoffee.com/coffee/"

# is_skippable_url now lives in scrapers/url_filters.py and is imported above
# so price_scraper.py, fetch_bean_images.py, and this module share one copy.

GRAMS_PER_OZ = 28.3495


# ---------------------------------------------------------------------------
# og:image extraction (moved verbatim from fetch_bean_images.py)
# ---------------------------------------------------------------------------

def extract_og_image(html: str, base_url: str) -> str | None:
    """Best product image URL from raw HTML: og:image -> regex -> JSON-LD."""
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = (
            soup.find("meta", attrs={"property": "og:image"})
            or soup.find("meta", attrs={"name": "og:image"})
            or soup.find("meta", property="og:image")
        )
        if tag and tag.get("content", "").strip():
            return urljoin(base_url, tag["content"].strip())
    except Exception:
        pass

    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            img = m.group(1).strip()
            if img and not img.startswith("data:"):
                return urljoin(base_url, img)

    for pat in (
        r'"@type"\s*:\s*"Product"[^}]*?"image"\s*:\s*\[?\s*["\']([^"\']+)',
        r'"image"\s*:\s*["\']([^"\']+)["\'][^}]*?"@type"\s*:\s*"Product"',
    ):
        m = re.search(pat, html, re.S)
        if m:
            candidate = m.group(1).strip()
            if candidate.startswith("http"):
                return candidate
    return None


def get_og_image(url: str, *, timeout: int = 20, extra_headers: dict | None = None) -> str | None:
    """GET url, return its og:image (or None). Raises on transport error."""
    headers = {**_BASE_HEADERS, **(extra_headers or {})}
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if resp.status_code not in (200, 206):
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    return extract_og_image(resp.text, resp.url)


def get_waytocoffee_image(reference_slug: str, *, timeout: int = 20) -> str | None:
    if not reference_slug:
        return None
    return get_og_image(f"{WAYTOCOFFEE_BASE}{reference_slug}/", timeout=timeout)


# ---------------------------------------------------------------------------
# Amazon product-page scrape (moved from fetch_bean_images.py)
# ---------------------------------------------------------------------------

_AMAZON_EXTRA = {
    "Referer": "https://www.google.com/",
    "sec-ch-ua": '"Chromium";v="120", "Not_A Brand";v="99"',
    "sec-ch-ua-platform": '"Linux"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
_AMAZON_IMAGE_RE = re.compile(
    r'"(?:large|hiRes|mainUrl)"\s*:\s*"(https://(?:m\.)?(?:images-)?[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
    re.I,
)


_AMAZON_DEAD_MARKERS = (
    "Page Not Found",
    "Looking for something?",
    "we couldn't find that page",
    "The Web address you entered is not a functioning page",
    "Sorry! We couldn't find that page",
)


def amazon_asin_status(asin: str, *, timeout: int = 20) -> str:
    """Best-effort liveness of an ASIN WITHOUT PA-API.

    Returns "alive" (resolved to a real product page), "dead" (clear
    not-found page), or "unknown" (anti-bot/CAPTCHA/ambiguous — cannot
    confirm either way, so the caller must not flag it dead). Raises on a
    transport error so it can be retried."""
    url = f"https://www.amazon.com/dp/{asin}"
    resp = requests.get(
        url, headers={**_BASE_HEADERS, **_AMAZON_EXTRA}, timeout=timeout, allow_redirects=True
    )
    if resp.status_code == 404:
        return "dead"
    if resp.status_code != 200:
        raise RuntimeError(f"Amazon HTTP {resp.status_code} for ASIN {asin}")
    head = resp.text[:6000]
    if "captcha" in resp.url.lower() or "Type the characters" in head:
        return "unknown"
    if any(marker in head for marker in _AMAZON_DEAD_MARKERS):
        return "dead"
    # A real product page carries the ASIN in canonical/dp links and a title block.
    if f"/dp/{asin}" in resp.text or 'id="productTitle"' in resp.text:
        return "alive"
    return "unknown"


def get_amazon_page_image(asin: str, *, timeout: int = 20) -> str | None:
    """Scrape amazon.com/dp/{asin} for the primary image. Raises on transport
    error; returns None on CAPTCHA/anti-bot (treated as 'nothing found')."""
    url = f"https://www.amazon.com/dp/{asin}"
    resp = requests.get(url, headers={**_BASE_HEADERS, **_AMAZON_EXTRA}, timeout=timeout, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"Amazon HTTP {resp.status_code} for ASIN {asin}")
    if "captcha" in resp.url.lower() or "Type the characters" in resp.text[:2000]:
        return None
    img = extract_og_image(resp.text, resp.url)
    if img:
        return img
    m = _AMAZON_IMAGE_RE.search(resp.text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Roaster price extraction — requests-first (JSON-LD / og:price / microdata)
# ---------------------------------------------------------------------------

# JSON-LD Offer.price is the most reliable signal on Shopify/Woo product pages.
_PRICE_META_RE = (
    r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([\d.,]+)["\']',
    r'<meta[^>]+property=["\']og:price:amount["\'][^>]+content=["\']([\d.,]+)["\']',
    r'<meta[^>]+itemprop=["\']price["\'][^>]+content=["\']([\d.,]+)["\']',
)


def _parse_price(text: str) -> float | None:
    if text is None:
        return None
    m = re.search(r"\d[\d,]*\.?\d*", str(text).replace(",", ""))
    if not m:
        return None
    try:
        val = float(m.group())
        return val if val > 0 else None
    except ValueError:
        return None


def _iter_jsonld_nodes(html: str):
    """Yield every dict node across all ld+json blocks, flattening @graph
    arrays, bare objects, and top-level lists alike."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                graph = cur.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
                yield cur


def _is_product_node(node: dict) -> bool:
    t = node.get("@type")
    if isinstance(t, list):
        return any(str(x).lower() == "product" for x in t)
    return str(t).lower() == "product"


def _price_from_offers(offers) -> float | None:
    """offers may be a dict, a list, and each offer may carry price directly or
    nested under priceSpecification."""
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list):
        return None
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price = _parse_price(offer.get("price") or offer.get("lowPrice"))
        if price:
            return price
        spec = offer.get("priceSpecification")
        for s in (spec if isinstance(spec, list) else [spec]):
            if isinstance(s, dict):
                price = _parse_price(s.get("price"))
                if price:
                    return price
    return None


def _price_from_jsonld(html: str) -> float | None:
    for node in _iter_jsonld_nodes(html):
        if _is_product_node(node):
            price = _price_from_offers(node.get("offers"))
            if price:
                return price
    return None


def get_roaster_price(url: str, *, timeout: int = 20) -> float | None:
    """Back-compat single-value wrapper: returns the price only (or None)."""
    price, _ = get_roaster_price_tiered(url, timeout=timeout)
    return price


def get_roaster_price_tiered(url: str, *, timeout: int = 20) -> tuple[float | None, str | None]:
    """Extract a price from a roaster product page via requests, reporting which
    tier produced it.

    Returns (price, source) where source is 'jsonld' or 'meta', or (None, None)
    if the page loads but exposes no machine-readable price (caller may fall
    back to a Playwright pass). Raises on transport error."""
    resp = requests.get(url, headers=_BASE_HEADERS, timeout=timeout, allow_redirects=True)
    if resp.status_code not in (200, 206):
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    html = resp.text
    price = _price_from_jsonld(html)
    if price:
        return price, "jsonld"
    for pat in _PRICE_META_RE:
        m = re.search(pat, html, re.I)
        if m:
            price = _parse_price(m.group(1))
            if price:
                return price, "meta"
    return None, None


# ---------------------------------------------------------------------------
# Shopify JSON endpoints — /products/{handle}.js (cents) and .json (string $)
# ---------------------------------------------------------------------------

_SHOPIFY_HANDLE_RE = re.compile(r"/products/([^/?#]+)")


def shopify_handle(url: str) -> str | None:
    """The {handle} from a /products/{handle} URL, or None if it isn't one."""
    m = _SHOPIFY_HANDLE_RE.search(url or "")
    return m.group(1) if m else None


def _price_per_oz(price: float, grams, weight_oz) -> float | None:
    """price_per_oz from the variant's OWN grams when present (more accurate),
    else from products.json weight_oz, else None."""
    try:
        grams = float(grams or 0)
    except (TypeError, ValueError):
        grams = 0.0
    if grams > 0:
        return round(price / (grams / GRAMS_PER_OZ), 4)
    if weight_oz:
        return round(price / weight_oz, 4)
    return None


def _variant_available(v: dict) -> bool:
    a = v.get("available")
    return True if a is None else bool(a)


def _select_variant(variants: list, weight_oz) -> tuple[dict | None, bool]:
    """Pick a variant and report stock status.

    Prefer available variants; among them (or all, if none available) pick the
    one whose grams are closest to weight_oz, else the first. Returns
    (variant_or_None, out_of_stock)."""
    if not variants:
        return None, True
    available = [v for v in variants if _variant_available(v)]
    out_of_stock = not available
    pool = available or variants
    if weight_oz:
        target = weight_oz * GRAMS_PER_OZ
        with_grams = [v for v in pool if (v.get("grams") or 0) > 0]
        if with_grams:
            return min(with_grams, key=lambda v: abs((v.get("grams") or 0) - target)), out_of_stock
    return pool[0], out_of_stock


def _shopify_from_js(data: dict, weight_oz) -> tuple[float, float | None, bool] | None:
    """.js shape: top-level + variants[].price are in CENTS."""
    variant, out_of_stock = _select_variant(data.get("variants") or [], weight_oz)
    if variant is not None:
        cents, grams = variant.get("price"), variant.get("grams")
    else:
        cents, grams = data.get("price"), 0
    price = round((cents or 0) / 100.0, 2)
    if price <= 0:
        return None
    return price, _price_per_oz(price, grams, weight_oz), out_of_stock


def _shopify_from_json(product: dict, weight_oz) -> tuple[float, float | None, bool] | None:
    """.json shape: product.variants[].price is a STRING in DOLLARS."""
    variant, out_of_stock = _select_variant(product.get("variants") or [], weight_oz)
    if variant is None:
        return None
    price = _parse_price(variant.get("price"))
    if not price:
        return None
    return round(price, 2), _price_per_oz(price, variant.get("grams"), weight_oz), out_of_stock


def get_shopify_price(
    url: str,
    weight_oz=None,
    *,
    dead_hosts: dict | None = None,
    throttle=None,
    timeout: int = 15,
) -> tuple[float, float | None, bool] | None:
    """Resolve price from a Shopify /products/{handle} URL.

    Tries {base}.js (price in cents) then {base}.json (price string in dollars).
    Returns (price, price_per_oz_or_None, out_of_stock_bool), or None if neither
    endpoint is a Shopify product JSON. Raises on transport error so the caller
    can retry. If dead_hosts is given, a .js 404 bumps that host's counter so the
    caller can stop probing a non-Shopify host after two misses. throttle(), if
    given, is called before each HTTP request for inter-request rate limiting."""
    handle = shopify_handle(url)
    if not handle:
        return None
    parsed = urlparse(url)
    host = parsed.netloc
    base = f"{parsed.scheme}://{host}/products/{handle}"

    if throttle:
        throttle()
    js_resp = requests.get(base + ".js", headers=_BASE_HEADERS, timeout=timeout, allow_redirects=True)
    if js_resp.status_code == 200:
        try:
            data = js_resp.json()
        except Exception:
            data = None
        if isinstance(data, dict) and "price" in data:
            result = _shopify_from_js(data, weight_oz)
            if result:
                return result
    elif js_resp.status_code == 404 and dead_hosts is not None:
        dead_hosts[host] = dead_hosts.get(host, 0) + 1

    if throttle:
        throttle()
    json_resp = requests.get(base + ".json", headers=_BASE_HEADERS, timeout=timeout, allow_redirects=True)
    if json_resp.status_code == 200:
        try:
            data = json_resp.json()
        except Exception:
            data = None
        product = data.get("product") if isinstance(data, dict) else None
        if isinstance(product, dict):
            result = _shopify_from_json(product, weight_oz)
            if result:
                return result
    return None
