# scrapers/price_scraper.py
"""
Coffee bean price scraper.
Fetches prices from Amazon PA-API 5.0 and direct roaster URLs via Playwright.
Stores results in SQLite. Designed for daily cron execution.

Cron entry:
  0 6 * * * /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1

Dependencies:
  pip install requests playwright
  python -m playwright install chromium
"""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ENV_FILE = Path("/opt/.env")
DB_PATH = Path("/opt/data/prices.db")
LOG_PATH = Path("/opt/data/scraper.log")
PRODUCTS_FILE = Path("/opt/scrapers/products.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


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
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_checked
        ON price_history (product_id, checked_at)
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Amazon PA-API 5.0 with AWS Signature Version 4
# ---------------------------------------------------------------------------

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signing_key(secret_key: str, date: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def amazon_get_price(asin: str, partner_tag: str, env: dict) -> float | None:
    access_key = env.get("AMAZON_ACCESS_KEY", "")
    secret_key = env.get("AMAZON_SECRET_KEY", "")
    partner_tag = partner_tag or env.get("AMAZON_PARTNER_TAG", "")

    if not all([access_key, secret_key, partner_tag]):
        log.warning("Amazon PA-API credentials not configured — skipping ASIN %s", asin)
        return None

    host = "webservices.amazon.com"
    region = "us-east-1"
    service = "ProductAdvertisingAPI"
    endpoint = f"https://{host}/paapi5/getitems"

    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    payload = {
        "ItemIds": [asin],
        "PartnerTag": partner_tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.com",
        "Resources": [
            "Offers.Listings.Price",
            "Offers.Listings.SavingBasis",
            "ItemInfo.Title",
        ],
    }
    payload_json = json.dumps(payload)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    headers_to_sign = {
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=utf-8",
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems",
    }
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted(headers_to_sign.items()))
    signed_headers = ";".join(sorted(headers_to_sign.keys()))

    canonical_request = "\n".join([
        "POST",
        "/paapi5/getitems",
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
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    request_headers = {
        **headers_to_sign,
        "Authorization": auth_header,
    }

    try:
        resp = requests.post(endpoint, data=payload_json, headers=request_headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("ItemsResult", {}).get("Items", [])
        if not items:
            log.warning("No items returned for ASIN %s", asin)
            return None
        listings = items[0].get("Offers", {}).get("Listings", [])
        if not listings:
            log.warning("No listings for ASIN %s", asin)
            return None
        price = listings[0].get("Price", {}).get("Amount")
        return float(price) if price is not None else None
    except Exception as exc:
        log.error("Amazon PA-API error for ASIN %s: %s", asin, exc)
        return None


# ---------------------------------------------------------------------------
# Roaster URL scraping via Playwright
# ---------------------------------------------------------------------------

PRICE_SELECTORS = [
    "[data-price]",
    ".price",
    ".product-price",
    ".product__price",
    ".price__regular",
    ".price-item--regular",
    "[class*='price']",
    "span.money",
    ".woocommerce-Price-amount",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    ".a-price .a-offscreen",
]


def scrape_roaster_price(url: str) -> float | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed — run: pip install playwright && python -m playwright install chromium")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            for selector in PRICE_SELECTORS:
                try:
                    el = page.query_selector(selector)
                    if el:
                        text = (el.get_attribute("data-price") or el.inner_text()).strip()
                        price = _parse_price(text)
                        if price and price > 0:
                            browser.close()
                            return price
                except Exception:
                    continue

            browser.close()
            log.warning("Could not find price on %s", url)
            return None
    except Exception as exc:
        log.error("Playwright error for %s: %s", url, exc)
        return None


def _parse_price(text: str) -> float | None:
    import re
    match = re.search(r"\d[\d,]*\.?\d*", text.replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    env = load_env()

    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)

    with open(PRODUCTS_FILE) as f:
        products = json.load(f)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    success = 0
    failed = 0

    for product in products:
        pid = product["id"]
        name = product["name"]
        weight_oz = product.get("weight_oz")
        asin = product.get("amazon_asin")
        roaster_url = product.get("roaster_url")
        affiliate_tag = product.get("affiliate_tag")

        price: float | None = None
        source: str = ""

        if asin:
            log.info("Fetching Amazon price for %s (ASIN: %s)", name, asin)
            price = amazon_get_price(asin, affiliate_tag or "", env)
            source = "amazon"
        elif roaster_url:
            log.info("Scraping roaster price for %s (%s)", name, roaster_url)
            price = scrape_roaster_price(roaster_url)
            source = "roaster"

        if price is None:
            log.warning("No price found for %s — skipping", name)
            failed += 1
            continue

        price_per_oz = round(price / weight_oz, 4) if weight_oz else None

        conn.execute(
            """
            INSERT INTO price_history (product_id, price, source, weight_oz, price_per_oz)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pid, price, source, weight_oz, price_per_oz),
        )
        conn.commit()

        log.info(
            "Saved: %s | $%.2f | %s%s",
            name,
            price,
            source,
            f" (${price_per_oz:.3f}/oz)" if price_per_oz else "",
        )
        success += 1

    conn.close()
    log.info("Done. %d succeeded, %d failed.", success, failed)


if __name__ == "__main__":
    run()
