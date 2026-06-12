# scrapers/refresh_data.py
"""
Single entry point for refreshing bean data (price, image, asin).

Replaces ad-hoc runs of the individual scrapers for data-health purposes. Each
field is resolved through its provider chain (scrapers/resolvers/), and every
attempt updates product_data_health: a success stores the value + resets the
fail counter; a failure marks the row 'stale', bumps fail_count, and KEEPS the
last-good value. No fetch failure can crash the run.

PA-API providers lead every chain but stay disabled behind PAAPI_ENABLED +
creds, so roaster-only resolution works today and Amazon activates with a single
.env change once the Associates account is approved.

Usage:
  python scrapers/refresh_data.py --all
  python scrapers/refresh_data.py --field price|image|asin
  python scrapers/refresh_data.py --product <id>
  python scrapers/refresh_data.py --health-report     # print stale/failing rows
  python scrapers/refresh_data.py --validate-asins     # cross-check every ASIN
  python scrapers/refresh_data.py --all --mock         # offline, synthetic data

Combine --product / --field with a run to scope it; add --mock to any run for
offline local testing.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE_DIR))

from scrapers.db import (  # noqa: E402
    get_connection,
    record_health_failure,
    record_health_success,
)
from scrapers.resolvers import (  # noqa: E402
    CHAINS,
    FIELDS,
    build_context,
    load_env,
    resolve_field,
)

PRODUCTS_FILE = Path(__file__).resolve().parent / "products.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def refresh(fields: list[str], only_product: str | None, mock: bool, polite: bool = True) -> None:
    catalog = load_products()
    env = load_env()
    ctx = build_context(catalog, env=env, mock=mock)

    targets = catalog
    if only_product:
        targets = [p for p in catalog if p["id"] == only_product]
        if not targets:
            log.error("No product with id %s", only_product)
            sys.exit(1)

    paapi_on = any(
        prov.name == "amazon_paapi" and prov.enabled(ctx)
        for field in fields for prov in CHAINS[field]
    )
    log.info(
        "Refreshing %s for %d product(s) | PA-API: %s | mock: %s",
        ", ".join(fields), len(targets), "enabled" if paapi_on else "disabled", mock,
    )

    tally = {f: {"ok": 0, "stale": 0} for f in fields}
    with get_connection() as conn:
        for product in targets:
            pid = product["id"]
            for field in fields:
                res = resolve_field(product, CHAINS[field], ctx)
                if res.ok:
                    record_health_success(conn, pid, field, res.value, res.source)
                    tally[field]["ok"] += 1
                else:
                    record_health_failure(conn, pid, field, res.source, res.error or res.status)
                    tally[field]["stale"] += 1
                if polite and not mock and res.source:
                    time.sleep(1.0)

    for field in fields:
        log.info("  %-6s ok=%d stale=%d", field, tally[field]["ok"], tally[field]["stale"])
    log.info("Done. Run --health-report to inspect stale/failing rows.")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def health_report() -> int:
    """Print every stale/failing row. Returns count of problem rows."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT product_id, field, status, fail_count, source,
                   COALESCE(value, ''), COALESCE(last_success_at, 'never'),
                   COALESCE(error, '')
            FROM product_data_health
            WHERE status != 'ok' OR fail_count > 0
            ORDER BY field, fail_count DESC, product_id
            """
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM product_data_health").fetchone()[0]

    if not rows:
        print(f"\nproduct_data_health: {total} row(s), none stale/failing. All green.\n")
        return 0

    print(f"\nproduct_data_health: {len(rows)} stale/failing of {total} row(s)\n")
    header = f"{'product_id':<46} {'field':<6} {'status':<7} {'fails':>5}  {'source':<18} last_success  error"
    print(header)
    print("-" * min(len(header) + 24, 160))
    for pid, field, status, fails, source, _value, last_ok, error in rows:
        last_ok = (last_ok or "never")[:19]
        print(f"{pid:<46} {field:<6} {status:<7} {fails:>5}  {(source or '-'):<18} {last_ok:<12}  {error[:60]}")
    print()
    return len(rows)


def validate_asins(mock: bool) -> None:
    """Cross-check every product's ASIN; flag dead/wrong/missing for backfill."""
    log.info("Validating ASINs (mock=%s)...", mock)
    refresh(fields=["asin"], only_product=None, mock=mock, polite=True)
    catalog = load_products()
    with_asin = sum(1 for p in catalog if (p.get("amazon_asin") or "").strip())
    with get_connection() as conn:
        flagged = conn.execute(
            """
            SELECT product_id, status, COALESCE(error, '')
            FROM product_data_health
            WHERE field = 'asin' AND status != 'ok'
            ORDER BY product_id
            """
        ).fetchall()
    print(f"\nASIN validation: {len(catalog)} products, {with_asin} with an ASIN, "
          f"{len(flagged)} flagged for backfill\n")
    if not flagged:
        print("  No dead/invalid/missing ASINs.\n")
        return
    for pid, status, error in flagged:
        print(f"  [{status:<11}] {pid:<46} {error[:70]}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh bean data (price/image/asin) with graceful degradation + health tracking.",
    )
    parser.add_argument("--all", action="store_true", help="Refresh all fields (price, image, asin).")
    parser.add_argument("--field", choices=FIELDS, action="append",
                        help="Refresh only this field (repeatable).")
    parser.add_argument("--product", help="Limit a refresh to this product id.")
    parser.add_argument("--health-report", action="store_true", help="Print stale/failing rows and exit.")
    parser.add_argument("--validate-asins", action="store_true", help="Cross-check every ASIN, flag dead/wrong.")
    parser.add_argument("--mock", action="store_true", help="Offline synthetic data for local testing.")
    args = parser.parse_args()

    if args.health_report:
        sys.exit(1 if health_report() else 0)

    if args.validate_asins:
        validate_asins(mock=args.mock)
        return

    if args.field:
        fields = list(dict.fromkeys(args.field))  # de-dup, keep order
    elif args.all or args.product:
        # --product alone refreshes every field for that one product.
        fields = list(FIELDS)
    else:
        parser.error("nothing to do — pass --all, --field, --product, --health-report, or --validate-asins")

    refresh(fields=fields, only_product=args.product, mock=args.mock)


if __name__ == "__main__":
    main()
