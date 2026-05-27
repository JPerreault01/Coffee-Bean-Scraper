# scrapers/price_scraper.py
"""
Price scraper for Amazon (PA-API 5.0) and direct roaster URLs (Playwright).
Runs daily via cron. Stores results in SQLite at /opt/data/prices.db.

Cron: 0 6 * * * /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1
"""

import json
import os
import sqlite3
import hmac
import hashlib
import datetime
import logging
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path("/opt")
DATA_DIR = BASE_DIR / "data"
SCRAPERS_DIR = BASE_DIR / "scrapers"
ENV_FILE = BASE_DIR / ".env"
PRODUCTS_FILE = SCRAPERS_DIR / "products.json"
DB_FILE = DATA_DIR / "prices.db"
LOG_FILE = DATA_DIR / "scraper.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment loader
# ---------------------------------------------------------------------------

def load_env(path: Path) -> None:
    if not path.exists():
        log.warning(f".env not found at {path}, relying on existing environment")
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            source TEXT NOT NULL,
            weight_oz REAL,
            price_per_oz REAL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def record_price(
    conn: sqlite3.Connection,
    product_id: str,
    price: float,
    source: str,
    weight_oz: float | None,
    currency: str = "USD",
) -> None:
    price_per_oz = round(price / weight_oz, 4) if weight_oz and weight_oz > 0 else None
    conn.execute(
        """
        INSERT INTO price_history (product_id, price, currency, source, weight_oz, price_per_oz)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (product_id, price, currency, source, weight_oz, price_per_oz),
    )
    conn.commit()
    log.info(
        f"Recorded {product_id}: ${price:.2f} ({source})"
        + (f" = ${price_per_oz:.4f}/oz" if price_per_oz else "")
    )


# ---------------------------------------------------------------------------
# Amazon PA-API 5.0 with AWS Signature Version 4
# ---------------------------------------------------------------------------

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def fetch_amazon_price(
    asin: str,
    partner_tag: str,
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
) -> float | None:
    """Fetch current price from Amazon PA-API 5.0 using AWS Signature V4."""

    endpoint = "webservices.amazon.com"
    path = "/paapi5/getitems"
    service = "ProductAdvertisingAPI"

    payload = {
        "ItemIds": [asin],
        "PartnerTag": partner_tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.com",
        "Resources": [
            "Offers.Listings.Price",
            "Offers.Listings.DeliveryInfo.IsPrimeEligible",
        ],
    }
    payload_json = json.dumps(payload)

    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    content_type = "application/json; charset=utf-8"
    content_encoding = "amz-sdk-request; attempt=1; max=1"
    target = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"

    canonical_headers = (
        f"content-encoding:{content_encoding}\n"
        f"content-type:{content_type}\n"
        f"host:{endpoint}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"

    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    canonical_request = "\n".join([
        "POST",
        path,
        "",
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = _get_signing_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    headers = {
        "content-encoding": content_encoding,
        "content-type": content_type,
        "host": endpoint,
        "x-amz-date": amz_date,
        "x-amz-target": target,
        "Authorization": auth_header,
    }

    try:
        resp = requests.post(
            f"https://{endpoint}{path}",
            headers=headers,
            data=payload_json,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("ItemsResult", {}).get("Items", [])
        if not items:
            log.warning(f"Amazon PA-API: no items returned for ASIN {asin}")
            return None

        listings = (
            items[0]
            .get("Offers", {})
            .get("Listings", [])
        )
        if not listings:
            log.warning(f"Amazon PA-API: no listings for ASIN {asin}")
            return None

        price_info = listings[0].get("Price", {})
        amount = price_info.get("Amount")
        if amount is None:
            log.warning(f"Amazon PA-API: no price amount for ASIN {asin}")
            return None

        return float(amount)

    except requests.RequestException as e:
        log.error(f"Amazon PA-API request failed for ASIN {asin}: {e}")
        return None
    except (KeyError, ValueError, IndexError) as e:
        log.error(f"Amazon PA-API parse error for ASIN {asin}: {e}")
        return None


# ---------------------------------------------------------------------------
# Roaster URL scraper (Playwright)
# ---------------------------------------------------------------------------

PRICE_SELECTORS = [
    "[class*='price'] .money",
    "[class*='price--sale']",
    "[class*='product-price']",
    "[class*='ProductPrice']",
    "[data-product-price]",
    ".price .amount",
    ".woocommerce-Price-amount",
    "[class*='price']:not([class*='compare']):not([class*='original'])",
    "span.price",
    ".product__price",
    "[itemprop='price']",
    ".offer-price",
    ".sale-price",
    ".current-price",
]


def _parse_price_text(text: str) -> float | None:
    import re
    # Strip currency symbols, spaces, and extract numeric value
    cleaned = re.sub(r"[^\d.]", "", text.strip())
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_roaster_price(url: str) -> float | None:
    """Scrape price from a direct roaster product page using Playwright."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
            except PWTimeout:
                log.warning(f"Page load timeout for {url}")
                browser.close()
                return None

            for selector in PRICE_SELECTORS:
                try:
                    el = page.query_selector(selector)
                    if el:
                        text = el.inner_text()
                        price = _parse_price_text(text)
                        if price and price > 0.5:
                            log.debug(f"Price found via selector '{selector}': {price}")
                            browser.close()
                            return price
                except Exception:
                    continue

            # Fallback: check meta tag
            try:
                meta_price = page.get_attribute("meta[property='product:price:amount']", "content")
                if meta_price:
                    price = _parse_price_text(meta_price)
                    if price and price > 0.5:
                        browser.close()
                        return price
            except Exception:
                pass

            browser.close()
            log.warning(f"Could not extract price from {url}")
            return None

    except Exception as e:
        log.error(f"Playwright error scraping {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_env(ENV_FILE)

    amazon_access_key = os.environ.get("AMAZON_ACCESS_KEY", "")
    amazon_secret_key = os.environ.get("AMAZON_SECRET_KEY", "")

    if not PRODUCTS_FILE.exists():
        log.error(f"products.json not found at {PRODUCTS_FILE}")
        sys.exit(1)

    with open(PRODUCTS_FILE) as f:
        products = json.load(f)

    conn = get_db()
    init_db(conn)

    log.info(f"Starting price check for {len(products)} products")

    for product in products:
        pid = product["id"]
        name = product.get("name", pid)
        weight_oz = product.get("weight_oz")
        asin = product.get("amazon_asin")
        roaster_url = product.get("roaster_url")
        affiliate_tag = product.get("affiliate_tag", "")

        price = None
        source = None

        # Prefer Amazon PA-API if ASIN available and keys configured
        if asin and amazon_access_key and amazon_secret_key:
            log.info(f"Fetching Amazon price for {name} (ASIN: {asin})")
            price = fetch_amazon_price(
                asin=asin,
                partner_tag=affiliate_tag or "mycoffeebeans-20",
                access_key=amazon_access_key,
                secret_key=amazon_secret_key,
            )
            if price:
                source = "amazon"

        # Fall back to roaster URL scraping
        if price is None and roaster_url:
            log.info(f"Scraping roaster URL for {name}: {roaster_url}")
            price = fetch_roaster_price(roaster_url)
            if price:
                source = "roaster"

        if price is None:
            log.warning(f"No price found for {name} — skipping")
            continue

        record_price(conn, pid, price, source, weight_oz)

    conn.close()
    log.info("Price check complete")


if __name__ == "__main__":
    main()
