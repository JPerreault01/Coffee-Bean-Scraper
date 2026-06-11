# scrapers/fetch_bean_images.py
"""
Bean image pipeline — robust, Playwright-optional.

Source priority per bean (first success wins):
  0. Cached file already on disk (>10 KB) — skip entirely.
  1. PA-API GetItems (only if creds present + ASIN).
  2. Amazon product page og:image via requests (ASIN, no PA-API needed).
  3. Roaster product page og:image via requests (skips affiliate redirects
     and placeholder URLs — same URL for 3+ products of the same brand).
  4. waytocoffee.com og:image via requests (reference_slug).
  5. Playwright headless (only if chromium binary is installed and all
     requests-based approaches failed).
  6. MANUAL NEEDED — logged; upload by hand.

robots.txt is NOT consulted — fetching product images for review display
is legitimate use; robots.txt compliance is for crawlers, not one-off lookups.

Run on the VPS:
  /opt/venv/bin/python3 /opt/scrapers/fetch_bean_images.py

Dependencies: requests, beautifulsoup4, lxml  (playwright is optional)
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


ENV_FILE      = _resolve("/opt/.env",              _REPO_ROOT / ".env")
PRODUCTS_FILE = _resolve("/opt/scrapers/products.json", _SCRAPERS_DIR / "products.json")
# Cache lives next to the scraper, not in the repo root
CACHE_DIR     = _resolve("/opt/scrapers", _SCRAPERS_DIR) / ".image-cache"
MANIFEST_FILE = CACHE_DIR / "manifest.json"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BASE_HEADERS = {
    "User-Agent":      USER_AGENT,
    "Accept":          "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

MIN_IMAGE_BYTES = 10 * 1024  # 10 KB

# URL patterns that are affiliate redirects, social media, or otherwise unscrapable
_SKIP_URL_PATTERNS = (
    "awin1.com", "shareasale.com", "linksynergy.com", "impact.com",
    "pinterest.", "prf.hn", "go.redirectingat.com", "track.effiliation.com",
    "sovrn.com", "viglink.com",
)

WAYTOCOFFEE_BASE = "https://www.waytocoffee.com/coffee/"

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

def load_env() -> dict:
    env: dict = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def is_skippable_url(url: str) -> bool:
    """True for affiliate redirects and social media URLs we cannot scrape."""
    if not url:
        return True
    return any(p in url for p in _SKIP_URL_PATTERNS)


def build_placeholder_urls(products: list[dict]) -> set[tuple[str, str]]:
    """Return (brand, url) pairs where the same URL appears for 3+ products.

    These are catalog-expansion artifacts where the wrong URL was copied
    across multiple products (e.g. all Volcanica beans pointing to the same
    sumatra page, all Lily Willy's pointing to teddys-blend).
    """
    counter: Counter = Counter()
    for p in products:
        brand = p.get("brand", "")
        url   = p.get("roaster_url", "")
        if brand and url:
            counter[(brand, url)] += 1
    return {pair for pair, n in counter.items() if n >= 3}


def _playwright_binary_exists() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# og:image extraction — requests-based, BS4-backed
# ---------------------------------------------------------------------------

def _extract_og_image(html: str, base_url: str) -> str | None:
    """Extract the best product image URL from raw HTML."""
    # 1. BeautifulSoup og:image (handles any attribute order)
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = (
            soup.find("meta", attrs={"property": "og:image"}) or
            soup.find("meta", attrs={"name": "og:image"}) or
            soup.find("meta", property="og:image")
        )
        if tag and tag.get("content", "").strip():
            return urljoin(base_url, tag["content"].strip())
    except Exception:
        pass

    # 2. Regex fallback (handles malformed HTML BS4 trips on)
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

    # 3. JSON-LD schema Product.image
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


def get_og_image_requests(url: str, timeout: int = 20,
                           extra_headers: dict | None = None) -> str | None:
    """GET url, return og:image. No robots.txt check."""
    headers = {**_BASE_HEADERS, **(extra_headers or {})}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code not in (200, 206):
            log.debug("HTTP %s for %s", resp.status_code, url)
            return None
        return _extract_og_image(resp.text, resp.url)
    except requests.exceptions.Timeout:
        log.warning("Timeout fetching %s", url)
        return None
    except Exception as exc:
        log.warning("requests failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Source 1: PA-API GetItems (SigV4 — unchanged)
# ---------------------------------------------------------------------------

PAAPI_HOST    = "webservices.amazon.com"
PAAPI_REGION  = "us-east-1"
PAAPI_SERVICE = "ProductAdvertisingAPI"
PAAPI_PATH    = "/paapi5/getitems"
PAAPI_TARGET  = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def get_image_paapi(asin: str) -> str | None:
    access_key = _ENV.get("AMAZON_ACCESS_KEY", "")
    secret_key = _ENV.get("AMAZON_SECRET_KEY", "")
    partner_tag = _ENV.get("AMAZON_PARTNER_TAG", "")
    if not (access_key and secret_key and partner_tag and asin):
        return None

    payload = json.dumps(
        {"ItemIds": [asin], "Resources": ["Images.Primary.Large", "Images.Primary.Medium"],
         "PartnerTag": partner_tag, "PartnerType": "Associates",
         "Marketplace": "www.amazon.com"},
        separators=(",", ":"),
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date   = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    canonical_headers = (
        f"content-encoding:amz-1.0\nhost:{PAAPI_HOST}\n"
        f"x-amz-date:{amz_date}\nx-amz-target:{PAAPI_TARGET}\n"
    )
    signed_headers  = "content-encoding;host;x-amz-date;x-amz-target"
    payload_hash    = hashlib.sha256(payload.encode()).hexdigest()
    canonical_req   = f"POST\n{PAAPI_PATH}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    algorithm       = "AWS4-HMAC-SHA256"
    cred_scope      = f"{date_stamp}/{PAAPI_REGION}/{PAAPI_SERVICE}/aws4_request"
    string_to_sign  = (
        f"{algorithm}\n{amz_date}\n{cred_scope}\n"
        f"{hashlib.sha256(canonical_req.encode()).hexdigest()}"
    )
    sig_key   = _signature_key(secret_key, date_stamp, PAAPI_REGION, PAAPI_SERVICE)
    signature = hmac.new(sig_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (f"{algorithm} Credential={access_key}/{cred_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")

    try:
        resp = requests.post(
            f"https://{PAAPI_HOST}{PAAPI_PATH}", data=payload, timeout=15,
            headers={"content-encoding": "amz-1.0",
                     "content-type": "application/json; charset=utf-8",
                     "host": PAAPI_HOST, "x-amz-date": amz_date,
                     "x-amz-target": PAAPI_TARGET, "Authorization": auth},
        )
        if resp.status_code != 200:
            log.warning("PA-API HTTP %s for %s", resp.status_code, asin)
            return None
        items = resp.json().get("ItemsResult", {}).get("Items", [])
        if not items:
            return None
        imgs = items[0].get("Images", {}).get("Primary", {})
        for size in ("Large", "Medium"):
            url = imgs.get(size, {}).get("URL")
            if url:
                return url
        return None
    except Exception as exc:
        log.warning("PA-API failed for %s: %s", asin, exc)
        return None


# ---------------------------------------------------------------------------
# Source 2: Amazon product page scrape (no PA-API creds needed)
# ---------------------------------------------------------------------------

_AMAZON_EXTRA = {
    "Referer":                "https://www.google.com/",
    "sec-ch-ua":              '"Chromium";v="120", "Not_A Brand";v="99"',
    "sec-ch-ua-platform":     '"Linux"',
    "Sec-Fetch-Dest":         "document",
    "Sec-Fetch-Mode":         "navigate",
    "Sec-Fetch-Site":         "none",
    "Sec-Fetch-User":         "?1",
    "Upgrade-Insecure-Requests": "1",
}

_AMAZON_IMAGE_RE = re.compile(
    r'"(?:large|hiRes|mainUrl)"\s*:\s*"(https://(?:m\.)?(?:images-)?[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
    re.I,
)


def get_image_amazon_requests(asin: str) -> str | None:
    """Scrape amazon.com/dp/{asin} for the primary product image."""
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        resp = requests.get(url, headers={**_BASE_HEADERS, **_AMAZON_EXTRA},
                            timeout=20, allow_redirects=True)
        if resp.status_code != 200:
            log.debug("Amazon HTTP %s for ASIN %s", resp.status_code, asin)
            return None
        if "captcha" in resp.url.lower() or "Type the characters" in resp.text[:2000]:
            log.warning("Amazon CAPTCHA for ASIN %s", asin)
            return None
        # og:image first
        img = _extract_og_image(resp.text, resp.url)
        if img:
            return img
        # Fallback: Amazon's internal image data block
        m = _AMAZON_IMAGE_RE.search(resp.text)
        if m:
            return m.group(1)
        return None
    except Exception as exc:
        log.warning("Amazon scrape failed for %s: %s", asin, exc)
        return None


# ---------------------------------------------------------------------------
# Source 3: Roaster URL — requests-based og:image
# ---------------------------------------------------------------------------

def get_image_roaster_requests(url: str) -> str | None:
    """Fetch og:image from the roaster product page via requests."""
    return get_og_image_requests(url)


# ---------------------------------------------------------------------------
# Source 4: waytocoffee.com via reference_slug
# ---------------------------------------------------------------------------

def get_image_waytocoffee(reference_slug: str) -> str | None:
    if not reference_slug:
        return None
    url = f"{WAYTOCOFFEE_BASE}{reference_slug}/"
    return get_og_image_requests(url)


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
            ctx  = browser.new_context(user_agent=USER_AGENT,
                                       viewport={"width": 1280, "height": 800},
                                       locale="en-US")
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
                        box  = img.bounding_box()
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
        resp = requests.get(image_url, headers=_BASE_HEADERS, timeout=20, stream=True)
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

    paapi_ready   = all(_ENV.get(k) for k in ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"))
    playwright_ok = _playwright_binary_exists()
    placeholder_pairs = build_placeholder_urls(products)

    log.info(
        "PA-API: %s | Amazon scrape: yes | Playwright: %s | %d placeholder URL(s) flagged",
        "ready" if paapi_ready else "no creds — skipping",
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
        pid            = product["id"]
        asin           = product.get("amazon_asin", "")
        roaster_url    = product.get("roaster_url", "")
        reference_slug = product.get("reference_slug", "")
        brand          = product.get("brand", "")
        dest           = CACHE_DIR / f"{pid}.jpg"

        # 0. Already cached
        if dest.exists() and dest.stat().st_size >= MIN_IMAGE_BYTES:
            log.info("CACHED %s", pid)
            manifest[pid] = str(dest)
            continue

        image_url: str | None = None
        source: str = ""

        # 1. PA-API (authoritative when creds + ASIN)
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
