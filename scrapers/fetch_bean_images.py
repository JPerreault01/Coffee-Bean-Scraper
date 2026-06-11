# scrapers/fetch_bean_images.py
"""
Bean image pipeline.

Resolves one product image per bean, in priority order:
  1. Amazon PA-API GetItems  (only if creds + ASIN exist; failure is non-fatal)
  2. Roaster product page     (Playwright: og:image, then largest gallery <img>)
  3. None                     (logs "MANUAL NEEDED: {id}" — upload by hand)

Each resolved image is downloaded to scrapers/.image-cache/{id}.jpg (gitignored),
validated as a real image >10KB, and recorded in scrapers/.image-cache/manifest.json
as { "<id>": "<local_path>" or null }.

The companion scrapers/set_featured_images.php reads that manifest and sets each
image as the WordPress featured image on the matching bean CPT post.

Run on the VPS:
  /opt/venv/bin/python3 /opt/scrapers/fetch_bean_images.py

Dependencies (already in requirements.txt):
  requests, playwright   (+ python -m playwright install chromium)
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Paths — prefer the live VPS layout (/opt/...) but fall back to the repo so
# the fetcher can be run and tested locally. Mirrors generate_review.py.
# ---------------------------------------------------------------------------

_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


ENV_FILE = _resolve("/opt/.env", _REPO_ROOT / ".env")
PRODUCTS_FILE = _resolve("/opt/scrapers/products.json", _SCRAPERS_DIR / "products.json")
CACHE_DIR = _SCRAPERS_DIR / ".image-cache"
MANIFEST_FILE = CACHE_DIR / "manifest.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MIN_IMAGE_BYTES = 10 * 1024  # 10KB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# Module-level env, populated in main(). get_image_paapi(asin) reads from it.
_ENV: dict = {}


def load_env() -> dict:
    env = {}
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


# ---------------------------------------------------------------------------
# (1) Amazon PA-API 5.0 GetItems — SigV4-signed POST, no external SDK.
# ---------------------------------------------------------------------------

PAAPI_HOST = "webservices.amazon.com"
PAAPI_REGION = "us-east-1"
PAAPI_SERVICE = "ProductAdvertisingAPI"
PAAPI_PATH = "/paapi5/getitems"
PAAPI_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def get_image_paapi(asin: str) -> str | None:
    """Return a primary image URL for an ASIN via PA-API GetItems, or None.

    Reads credentials from the module-level _ENV. Any failure (missing creds,
    the common 'not yet approved for PA-API' 401/403, network, parse) returns
    None so the caller can fall through to the roaster fetch.
    """
    access_key = _ENV.get("AMAZON_ACCESS_KEY", "")
    secret_key = _ENV.get("AMAZON_SECRET_KEY", "")
    partner_tag = _ENV.get("AMAZON_PARTNER_TAG", "")

    if not (access_key and secret_key and partner_tag and asin):
        return None

    payload = json.dumps(
        {
            "ItemIds": [asin],
            "Resources": [
                "Images.Primary.Large",
                "Images.Primary.Medium",
            ],
            "PartnerTag": partner_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com",
        },
        separators=(",", ":"),
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Canonical request (headers must be sorted, lowercase, signed in order).
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"host:{PAAPI_HOST}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{PAAPI_TARGET}\n"
    )
    signed_headers = "content-encoding;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"POST\n{PAAPI_PATH}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{PAAPI_REGION}/{PAAPI_SERVICE}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _signature_key(secret_key, date_stamp, PAAPI_REGION, PAAPI_SERVICE)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=utf-8",
        "host": PAAPI_HOST,
        "x-amz-date": amz_date,
        "x-amz-target": PAAPI_TARGET,
        "Authorization": authorization,
    }

    try:
        resp = requests.post(
            f"https://{PAAPI_HOST}{PAAPI_PATH}",
            data=payload,
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning(
                "PA-API GetItems for %s returned HTTP %s (likely not approved): %s",
                asin,
                resp.status_code,
                resp.text[:200],
            )
            return None
        data = resp.json()
        items = data.get("ItemsResult", {}).get("Items", [])
        if not items:
            log.info("PA-API returned no items for %s", asin)
            return None
        images = items[0].get("Images", {}).get("Primary", {})
        for size in ("Large", "Medium"):
            url = images.get(size, {}).get("URL")
            if url:
                return url
        return None
    except Exception as exc:
        log.warning("PA-API GetItems failed for %s: %s — falling through", asin, exc)
        return None


# ---------------------------------------------------------------------------
# (2) Roaster product page — Playwright.
# ---------------------------------------------------------------------------

# Largest <img> within one of these gallery containers wins (after og:image).
GALLERY_SELECTORS = [
    ".product-gallery img",
    ".product__media img",
    ".product-single__photo img",
    ".product-images img",
    ".woocommerce-product-gallery img",
    "[class*='gallery'] img",
    "[class*='product'] img",
]


def _robots_allows(url: str) -> bool:
    """Best-effort robots.txt check. If robots cannot be read, allow."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def get_image_roaster(url: str) -> str | None:
    """Resolve the primary product image from a roaster page.

    og:image meta first; then the largest <img> found in a product-gallery
    container. Returns an absolute URL or None.
    """
    if not _robots_allows(url):
        log.warning("robots.txt disallows fetching %s — skipping roaster image", url)
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = context.new_page()
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # og:image first.
            og = page.query_selector('meta[property="og:image"]') or page.query_selector(
                'meta[name="og:image"]'
            )
            if og:
                content = og.get_attribute("content")
                if content:
                    browser.close()
                    return urljoin(url, content.strip())

            # Largest <img> in a gallery container (by rendered area, then
            # natural dimensions as a fallback).
            best_url = None
            best_area = 0
            for selector in GALLERY_SELECTORS:
                try:
                    imgs = page.query_selector_all(selector)
                except Exception:
                    continue
                for img in imgs:
                    src = (
                        img.get_attribute("src")
                        or img.get_attribute("data-src")
                        or img.get_attribute("data-original")
                    )
                    if not src or src.startswith("data:"):
                        continue
                    try:
                        box = img.bounding_box()
                        area = (box["width"] * box["height"]) if box else 0
                    except Exception:
                        area = 0
                    if area == 0:
                        try:
                            nw = img.evaluate("el => el.naturalWidth") or 0
                            nh = img.evaluate("el => el.naturalHeight") or 0
                            area = nw * nh
                        except Exception:
                            area = 0
                    if area > best_area:
                        best_area = area
                        best_url = urljoin(url, src.strip())
                if best_url:
                    break

            browser.close()
            return best_url
    except Exception as exc:
        log.error("Playwright error fetching roaster image %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Download + validation.
# ---------------------------------------------------------------------------

# Magic-byte signatures for the common web image formats.
_IMAGE_SIGNATURES = (
    b"\xff\xd8\xff",            # JPEG
    b"\x89PNG\r\n\x1a\n",       # PNG
    b"GIF87a",                  # GIF
    b"GIF89a",                  # GIF
    b"RIFF",                    # WebP (RIFF....WEBP)
)


def _looks_like_image(data: bytes) -> bool:
    if len(data) < MIN_IMAGE_BYTES:
        return False
    if data[:4] == b"RIFF" and data[8:12] != b"WEBP":
        return False
    return any(data.startswith(sig) for sig in _IMAGE_SIGNATURES)


def download_image(image_url: str, dest: Path) -> bool:
    """Download to dest. Returns True only if the result is a valid image >10KB."""
    try:
        resp = requests.get(
            image_url,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            stream=True,
        )
        resp.raise_for_status()
        data = resp.content
    except Exception as exc:
        log.error("Failed to download %s: %s", image_url, exc)
        return False

    if not _looks_like_image(data):
        log.warning(
            "Downloaded file from %s is not a valid image >10KB (%d bytes) — discarding",
            image_url,
            len(data),
        )
        return False

    dest.write_bytes(data)
    log.info("Saved %s (%d KB) from %s", dest.name, len(data) // 1024, image_url)
    return True


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main() -> None:
    global _ENV
    _ENV = load_env()
    products = load_products()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    paapi_ready = all(
        _ENV.get(k)
        for k in ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG")
    )
    log.info(
        "PA-API credentials %s — %s",
        "present" if paapi_ready else "missing",
        "will attempt Amazon image lookups" if paapi_ready else "skipping PA-API, roaster-only",
    )

    manifest: dict[str, str | None] = {}
    counts = {"paapi": 0, "roaster": 0, "manual": 0}
    did_roaster_fetch = False

    for product in products:
        pid = product["id"]
        asin = product.get("amazon_asin")
        roaster_url = product.get("roaster_url")
        dest = CACHE_DIR / f"{pid}.jpg"

        image_url = None
        source = None

        # Skip if we already have a valid cached file for this product.
        if dest.exists() and dest.stat().st_size >= MIN_IMAGE_BYTES:
            log.info("CACHED %s — skipping fetch", pid)
            manifest[pid] = str(dest)
            continue

        # (1) PA-API
        if paapi_ready and asin:
            image_url = get_image_paapi(asin)
            if image_url:
                source = "paapi"

        # (2) Roaster page
        if not image_url and roaster_url:
            # 1–2s politeness delay between consecutive roaster fetches.
            if did_roaster_fetch:
                time.sleep(1.5)
            log.info("Fetching roaster image for %s (%s)", pid, roaster_url)
            image_url = get_image_roaster(roaster_url)
            did_roaster_fetch = True
            if image_url:
                source = "roaster"

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
        "Done. PA-API: %d | Roaster: %d | Manual needed: %d | Manifest: %s",
        counts["paapi"],
        counts["roaster"],
        counts["manual"],
        MANIFEST_FILE,
    )


if __name__ == "__main__":
    main()
