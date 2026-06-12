# scrapers/price_scraper.py
"""
Coffee bean price scraper.

Resolves a current price for each product by walking the price resolver chain
(scrapers/resolvers/price.py) and writes the first success to price_history.
Resolution order, first hit wins, recorded in the `source` column:

  1. amazon              PA-API (gated behind PAAPI_ENABLED + creds; --skip-amazon off)
  2. shopify             /products/{handle}.js / .json JSON endpoints (variant-aware)
  3. jsonld / meta       requests + BeautifulSoup: JSON-LD Offer.price / price meta tags
  4. roaster-playwright  headless render fallback (only if a chromium binary is installed)

Requests tiers (2-3) share a 1.5s rate limiter. Playwright/PA-API tiers (1, 4)
self-impose the random 3-8s delay only just before their call, so skipped or
early-resolved products never pay it. Each attempt also updates
product_data_health so a failed fetch degrades the field to 'stale' (keeping the
last-good value) instead of blanking it. No fetch failure can raise out of the
resolver.

Cron entry (unchanged — default run = all products, writes to DB):
  0 6 * * * /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1

Usage:
  python scrapers/price_scraper.py                      # real run, all products
  python scrapers/price_scraper.py --limit 3 --dry-run  # first 3, resolve only, no writes
  python scrapers/price_scraper.py --product <id>       # single product by id
  python scrapers/price_scraper.py --skip-amazon        # roaster-only (skip PA-API tier)
  python scrapers/price_scraper.py --mock               # offline synthetic prices

Dependencies: requests, beautifulsoup4, lxml  (playwright optional for tier 4)
"""

import argparse
import json
import logging
import sys
from collections import Counter
from contextlib import nullcontext
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE_DIR))

from scrapers.db import (  # noqa: E402
    get_connection,
    record_health_failure,
    record_health_success,
)
from scrapers.resolvers import build_context, load_env, resolve_field  # noqa: E402
from scrapers.resolvers._playwright import binary_exists  # noqa: E402
from scrapers.resolvers.base import STATUS_ERROR  # noqa: E402
from scrapers.resolvers.price import PRICE_CHAIN  # noqa: E402

PRODUCTS_FILE = Path(__file__).resolve().parent / "products.json"
LOG_PATH = _BASE_DIR / "data" / "scraper.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# Order tier names are listed in the summary breakdown line.
_SOURCE_ORDER = ("amazon", "shopify", "jsonld", "meta", "roaster-playwright")


def print_summary(results: list[dict], source_counts: Counter, skipped: int, failed: int) -> None:
    if not results:
        print("\nNo prices collected.")
        return

    col_name = max(max((len(r["name"]) for r in results), default=12), 12)

    header = f"{'Product':<{col_name}}  {'Price':>8}  {'Price/oz':>9}  Source"
    separator = "-" * min(len(header) + 30, 120)
    print(f"\n{header}")
    print(separator)
    for r in results:
        price_str = f"${r['price']:.2f}" if r["price"] is not None else "(stale)"
        ppoz_str = f"${r['price_per_oz']:.3f}" if r.get("price_per_oz") is not None else "-"
        print(f"{r['name']:<{col_name}}  {price_str:>8}  {ppoz_str:>9}  {r['source']}")
    print()

    resolved = sum(source_counts.values())
    ordered = list(_SOURCE_ORDER) + [s for s in source_counts if s not in _SOURCE_ORDER]
    breakdown = " ".join(f"{s}:{source_counts[s]}" for s in ordered if source_counts[s])
    print(
        f"Resolved: {resolved}/{len(results)} — {breakdown or '(none)'} "
        f"| skipped:{skipped} failed:{failed}"
    )


def run(
    mock: bool = False,
    only_product: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    skip_amazon: bool = False,
) -> None:
    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        catalog = json.load(f)

    products = catalog
    if only_product:
        products = [p for p in catalog if p["id"] == only_product]
        if not products:
            log.error("No product with id %s", only_product)
            sys.exit(1)
    if limit is not None:
        products = products[:limit]

    env = load_env()
    # build_context needs the FULL catalog to detect shared placeholder URLs.
    ctx = build_context(catalog, env=env, mock=mock)
    ctx["skip_amazon"] = skip_amazon
    ctx["playwright_ok"] = False if mock else binary_exists()

    paapi_on = any(p.enabled(ctx) for p in PRICE_CHAIN if p.name == "amazon_paapi")
    log.info(
        "Price run — %d product(s) | PA-API: %s | Playwright: %s | mock: %s | dry-run: %s",
        len(products),
        "enabled" if paapi_on else ("skipped (--skip-amazon)" if skip_amazon else "disabled"),
        "available" if ctx["playwright_ok"] else "binary missing",
        mock, dry_run,
    )

    results: list[dict] = []
    source_counts: Counter = Counter()
    success = skipped = failed = 0

    conn_cm = nullcontext(None) if dry_run else get_connection()
    with conn_cm as conn:
        for product in products:
            pid = product["id"]
            name = product["name"]
            weight_oz = product.get("weight_oz")

            res = resolve_field(product, PRICE_CHAIN, ctx)

            if res.ok:
                price = float(res.value)
                price_per_oz = res.extra.get("price_per_oz")
                if price_per_oz is None:
                    price_per_oz = round(price / weight_oz, 4) if weight_oz else None
                if res.extra.get("out_of_stock"):
                    log.info("%s out of stock — recording price anyway ($%.2f)", name, price)
                if conn is not None:
                    conn.execute(
                        """
                        INSERT INTO price_history (product_id, price, source, weight_oz, price_per_oz)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (pid, price, res.source, weight_oz, price_per_oz),
                    )
                    conn.commit()
                    record_health_success(conn, pid, "price", price, res.source)
                log.info(
                    "Saved: %s | $%.2f | %s%s",
                    name, price, res.source,
                    f" (${price_per_oz:.3f}/oz)" if price_per_oz else "",
                )
                results.append({"name": name, "price": price, "price_per_oz": price_per_oz, "source": res.source})
                source_counts[res.source] += 1
                success += 1
            elif res.status == STATUS_ERROR:
                if conn is not None:
                    record_health_failure(conn, pid, "price", res.source, res.error or res.status)
                log.warning("FAILED %s — %s (%s)", name, res.source or "-", res.error)
                # Keep the tier name for errors so the user knows which tier failed.
                results.append({"name": name, "price": None, "price_per_oz": None, "source": res.source or "-"})
                failed += 1
            else:
                if conn is not None:
                    record_health_failure(conn, pid, "price", res.source, res.error or res.status)
                log.info("SKIP %s — no scrapable source (%s)", name, res.error or "no usable tier")
                # Show "-" for skips: the last-attempted tier name is irrelevant.
                results.append({"name": name, "price": None, "price_per_oz": None, "source": "-"})
                skipped += 1

    log.info("Done. %d priced, %d skipped, %d failed.", success, skipped, failed)
    print_summary(results, source_counts, skipped, failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve and store coffee bean prices.")
    parser.add_argument("--mock", action="store_true", help="Offline synthetic prices for local testing.")
    parser.add_argument("--product", help="Only this product id.")
    parser.add_argument("--limit", type=int, help="Only process the first N products.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve fully but write nothing; print the summary.")
    parser.add_argument("--skip-amazon", action="store_true", help="Skip the Amazon (PA-API) tier entirely.")
    args = parser.parse_args()
    run(
        mock=args.mock,
        only_product=args.product,
        limit=args.limit,
        dry_run=args.dry_run,
        skip_amazon=args.skip_amazon,
    )


if __name__ == "__main__":
    main()
