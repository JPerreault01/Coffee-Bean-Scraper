# scrapers/fetch_bean_images.py
"""
Bean image pipeline — robust, Playwright-optional bulk image backfill.

Source priority per bean (first success wins):
  0. Cached file already on disk (>10 KB) — skip entirely.
  1. PA-API GetItems         (only if PAAPI_ENABLED + creds + ASIN).
  2. Amazon product page og:image via requests (ASIN, no PA-API needed).
  3. Roaster product page og:image via requests (skips affiliate redirects
     and placeholder URLs — same URL for 3+ products of the same brand).
  4. waytocoffee.com og:image via requests (reference_slug).
  5. Playwright headless (only if a chromium binary is installed and all
     requests-based approaches failed).
  6. MANUAL NEEDED — logged; upload by hand.

The SigV4 PA-API signing and the og:image / Amazon-page / roaster scrape logic
now live in scrapers/resolvers/{_amazon,_http}.py — this script imports them so
there is ONE implementation in the repo (see refresh_data.py for the resolver
chain that powers product_data_health). This file remains the heavier image
backfill tool (Amazon page scrape + waytocoffee + Playwright gallery fallback).

robots.txt is NOT consulted — fetching a product's own image for review display
is legitimate one-off use, not crawling.

Run on the VPS:
  /opt/venv/bin/python3 /opt/scrapers/fetch_bean_images.py

Dependencies: requests, beautifulsoup4, lxml  (playwright is optional)
"""

import json
import logging
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent
sys.path.insert(0, str(_REPO_ROOT))

from scrapers.resolvers import _amazon, _http  # noqa: E402
from scrapers.resolvers.base import env_flag, load_env  # noqa: E402
from scrapers.url_filters import build_placeholder_urls, is_skippable_url  # noqa: E402


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


PRODUCTS_FILE = _resolve("/opt/scrapers/products.json", _SCRAPERS_DIR / "products.json")
CACHE_DIR = _resolve("/opt/scrapers", _SCRAPERS_DIR) / ".image-cache"
MANIFEST_FILE = CACHE_DIR / "manifest.json"

MIN_IMAGE_BYTES = 10 * 1024  # 10 KB
USER_AGENT = _http.USER_AGENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_ENV: dict = {}


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _playwright_binary_exists() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Image-source wrappers — delegate fetching to the shared resolver helpers.
# These swallow failures (return None) because main() walks the next source;
# the retry/health bookkeeping lives in refresh_data.py + the resolver chain.
# ---------------------------------------------------------------------------

def get_image_paapi(asin: str) -> str | None:
    if not (env_flag(_ENV, "PAAPI_ENABLED") and _amazon.has_credentials(_ENV) and asin):
        return None
    try:
        return _amazon.get_image(asin, _ENV)
    except Exception as exc:
        log.warning("PA-API failed for %s: %s", asin, exc)
        return None


def get_image_amazon_requests(asin: str) -> str | None:
    try:
        return _http.get_amazon_page_image(asin)
    except Exception as exc:
        log.warning("Amazon scrape failed for %s: %s", asin, exc)
        return None


def get_image_roaster_requests(url: str) -> str | None:
    try:
        return _http.get_og_image(url)
    except Exception as exc:
        log.warning("Roaster fetch failed for %s: %s", url, exc)
        return None


def get_image_waytocoffee(reference_slug: str) -> str | None:
    try:
        return _http.get_waytocoffee_image(reference_slug)
    except Exception as exc:
        log.warning("WayToCoffee fetch failed for %s: %s", reference_slug, exc)
        return None


# ---------------------------------------------------------------------------
# Source 5: Playwright fallback (JS-heavy pages, only if binary installed)
# ---------------------------------------------------------------------------

_GALLERY_SELECTORS = [
    ".product-gallery img", ".product__media img", ".product-single__photo img",
    ".product-images img", ".woocommerce-product-gallery img",
    "[class*='gallery'] img", "[class*='product'] img",
]


def get_image_playwright(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-US"
            )
            page = ctx.new_page()
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            og = (page.query_selector('meta[property="og:image"]') or
                  page.query_selector('meta[name="og:image"]'))
            if og:
                content = og.get_attribute("content")
                if content:
                    browser.close()
                    return urljoin(url, content.strip())

            best_url, best_area = None, 0
            for sel in _GALLERY_SELECTORS:
                try:
                    imgs = page.query_selector_all(sel)
                except Exception:
                    continue
                for img in imgs:
                    src = (img.get_attribute("src") or img.get_attribute("data-src")
                           or img.get_attribute("data-original"))
                    if not src or src.startswith("data:"):
                        continue
                    try:
                        box = img.bounding_box()
                        area = (box["width"] * box["height"]) if box else 0
                    except Exception:
                        area = 0
                    if area == 0:
                        try:
                            area = (img.evaluate("el => el.naturalWidth") or 0) * \
                                   (img.evaluate("el => el.naturalHeight") or 0)
                        except Exception:
                            area = 0
                    if area > best_area:
                        best_area, best_url = area, urljoin(url, src.strip())
                if best_url:
                    break

            browser.close()
            return best_url
    except Exception as exc:
        log.error("Playwright error for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Download + validation
# ---------------------------------------------------------------------------

_IMAGE_SIGS = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"RIFF")


def _looks_like_image(data: bytes) -> bool:
    if len(data) < MIN_IMAGE_BYTES:
        return False
    if data[:4] == b"RIFF" and data[8:12] != b"WEBP":
        return False
    return any(data.startswith(s) for s in _IMAGE_SIGS)


def download_image(image_url: str, dest: Path) -> bool:
    try:
        resp = requests.get(image_url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        resp.raise_for_status()
        data = resp.content
    except Exception as exc:
        log.error("Download failed %s: %s", image_url, exc)
        return False
    if not _looks_like_image(data):
        log.warning("Not a valid image >10KB (%d bytes): %s", len(data), image_url)
        return False
    dest.write_bytes(data)
    log.info("Saved %s (%d KB) from %s", dest.name, len(data) // 1024, image_url)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _ENV
    _ENV = load_env()
    products = load_products()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    paapi_ready = env_flag(_ENV, "PAAPI_ENABLED") and _amazon.has_credentials(_ENV)
    playwright_ok = _playwright_binary_exists()
    placeholder_pairs = build_placeholder_urls(products)

    log.info(
        "PA-API: %s | Amazon scrape: yes | Playwright: %s | %d placeholder URL(s) flagged",
        "ready" if paapi_ready else "disabled (PAAPI_ENABLED off or no creds)",
        "available" if playwright_ok else "binary missing — skipping",
        len(placeholder_pairs),
    )

    manifest: dict[str, str | None] = {}
    counts = {"paapi": 0, "amazon": 0, "roaster": 0, "waytocoffee": 0, "playwright": 0, "manual": 0}
    last_fetch = 0.0

    def _polite():
        nonlocal last_fetch
        gap = time.time() - last_fetch
        if gap < 1.5:
            time.sleep(1.5 - gap)
        last_fetch = time.time()

    for product in products:
        pid = product["id"]
        asin = product.get("amazon_asin", "")
        roaster_url = product.get("roaster_url", "")
        reference_slug = product.get("reference_slug", "")
        brand = product.get("brand", "")
        dest = CACHE_DIR / f"{pid}.jpg"

        # 0. Already cached
        if dest.exists() and dest.stat().st_size >= MIN_IMAGE_BYTES:
            log.info("CACHED %s", pid)
            manifest[pid] = str(dest)
            continue

        image_url: str | None = None
        source: str = ""

        # 1. PA-API (authoritative when enabled + creds + ASIN)
        if not image_url and paapi_ready and asin:
            image_url = get_image_paapi(asin)
            if image_url:
                source = "paapi"

        # 2. Amazon product page scrape (no PA-API needed)
        if not image_url and asin:
            _polite()
            log.info("Amazon scrape %s (ASIN %s)", pid, asin)
            image_url = get_image_amazon_requests(asin)
            if image_url:
                source = "amazon"

        # 3. Roaster URL — requests-based (skip affiliates + placeholders)
        if not image_url and roaster_url:
            if is_skippable_url(roaster_url):
                log.info("SKIP %s — affiliate/social URL: %s", pid, roaster_url)
            elif (brand, roaster_url) in placeholder_pairs:
                log.info("SKIP %s — placeholder URL (same URL for 3+ %s products)", pid, brand)
            else:
                _polite()
                log.info("Roaster fetch %s (%s)", pid, roaster_url)
                image_url = get_image_roaster_requests(roaster_url)
                if image_url:
                    source = "roaster"

        # 4. waytocoffee.com via reference_slug
        if not image_url and reference_slug:
            _polite()
            log.info("WayToCoffee fetch %s (slug: %s)", pid, reference_slug)
            image_url = get_image_waytocoffee(reference_slug)
            if image_url:
                source = "waytocoffee"

        # 5. Playwright (JS-heavy pages, only if binary installed)
        if not image_url and playwright_ok and roaster_url and not is_skippable_url(roaster_url):
            _polite()
            log.info("Playwright %s", pid)
            image_url = get_image_playwright(roaster_url)
            if image_url:
                source = "playwright"

        # Resolve → download → manifest
        if image_url and download_image(image_url, dest):
            manifest[pid] = str(dest)
            counts[source] += 1
            log.info("RESOLVED %s via %s", pid, source)
        else:
            manifest[pid] = None
            counts["manual"] += 1
            log.warning("MANUAL NEEDED: %s", pid)

    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
    log.info(
        "Done. PA-API:%d Amazon:%d Roaster:%d WayToCoffee:%d Playwright:%d Manual:%d | Manifest: %s",
        counts["paapi"], counts["amazon"], counts["roaster"],
        counts["waytocoffee"], counts["playwright"], counts["manual"],
        MANIFEST_FILE,
    )


if __name__ == "__main__":
    main()
