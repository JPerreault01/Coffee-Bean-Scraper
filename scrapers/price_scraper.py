# scrapers/price_scraper.py
"""
Coffee bean price scraper.
Fetches prices from Amazon product pages and direct roaster URLs via Playwright.
Stores results in SQLite. Designed for daily cron execution.

Cron entry:
  0 6 * * * /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1

Dependencies:
  pip install playwright
  python -m playwright install chromium
"""

import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ENV_FILE = Path("/opt/.env")
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BASE_DIR / "data" / "scraper.log"
PRODUCTS_FILE = Path(__file__).resolve().parent / "products.json"

sys.path.insert(0, str(BASE_DIR))
from scrapers.db import get_connection  # noqa: E402

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

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


# Amazon selectors in priority order — .a-offscreen has the full price string
AMAZON_PRICE_SELECTORS = [
    ".a-offscreen",
    ".a-price-whole",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "span[data-a-color='price'] .a-offscreen",
]

ROASTER_PRICE_SELECTORS = [
    "[data-price]",
    ".price",
    ".product-price",
    ".product__price",
    ".product__price .price",
    "[data-product-price]",
    ".price--main",
    ".price__regular",
    ".price-item--regular",
    "[class*='price']",
    "span.money",
    ".woocommerce-Price-amount",
]


def _parse_price(text: str) -> float | None:
    match = re.search(r"\d[\d,]*\.?\d*", text.replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            return None
    return None


def scrape_price(url: str, selectors: list[str]) -> float | None:
    is_amazon = "amazon.com" in url
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
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = context.new_page()
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.evaluate("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page.wait_for_timeout(5000 if is_amazon else 2000)

            for selector in selectors:
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


def print_summary(results: list[dict]) -> None:
    if not results:
        print("\nNo prices collected.")
        return

    col_name = max((len(r["name"]) for r in results), default=12)
    col_name = max(col_name, 12)

    header = f"{'Product':<{col_name}}  {'Price':>8}  {'Price/oz':>9}  URL"
    separator = "-" * min(len(header) + 40, 120)
    print(f"\n{header}")
    print(separator)

    for r in results:
        price_str = f"${r['price']:.2f}" if r["price"] is not None else "—"
        ppoz_str = f"${r['price_per_oz']:.3f}" if r.get("price_per_oz") is not None else "—"
        print(f"{r['name']:<{col_name}}  {price_str:>8}  {ppoz_str:>9}  {r['url']}")

    print()


def run() -> None:
    env = load_env()  # noqa: F841 — kept for env loading pattern consistency

    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        products = json.load(f)

    results = []
    success = 0
    failed = 0

    with get_connection() as conn:
        for i, product in enumerate(products):
            pid = product["id"]
            name = product["name"]
            weight_oz = product.get("weight_oz")
            asin = product.get("amazon_asin")
            roaster_url = product.get("roaster_url")

            if i > 0:
                delay = random.uniform(3, 8)
                log.info("Waiting %.1f seconds before next request...", delay)
                time.sleep(delay)

            price: float | None = None
            source_url: str = ""
            source: str = ""

            if asin:
                source_url = f"https://www.amazon.com/dp/{asin}"
                log.info("Scraping Amazon price for %s (%s)", name, source_url)
                price = scrape_price(source_url, AMAZON_PRICE_SELECTORS)
                source = "amazon"
            elif roaster_url:
                source_url = roaster_url
                log.info("Scraping roaster price for %s (%s)", name, roaster_url)
                price = scrape_price(source_url, ROASTER_PRICE_SELECTORS)
                source = "roaster"
            else:
                log.warning("No ASIN or roaster URL for %s — skipping", name)
                failed += 1
                continue

            if price is None:
                log.warning("No price found for %s — skipping", name)
                failed += 1
                results.append({"name": name, "price": None, "price_per_oz": None, "url": source_url})
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
            results.append({"name": name, "price": price, "price_per_oz": price_per_oz, "url": source_url})
            success += 1

    log.info("Done. %d succeeded, %d failed.", success, failed)
    print_summary(results)


if __name__ == "__main__":
    run()
