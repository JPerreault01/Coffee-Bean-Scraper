import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "prices.db"
PRODUCTS_FILE = REPO_ROOT / "scrapers" / "products.json"

sys.path.insert(0, str(REPO_ROOT))


def check(label, condition, reason=""):
    status = "PASS" if condition else "FAIL"
    reason_str = f" — {reason}" if reason else ""
    print(f"[{status}] {label}{reason_str}")
    return condition


def run_scraper_subset():
    import scrapers.price_scraper as scraper

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        all_products = json.load(f)

    subset = all_products[:3]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(subset, f)
        temp_path = Path(f.name)

    original_products_file = scraper.PRODUCTS_FILE
    try:
        scraper.PRODUCTS_FILE = temp_path
        scraper.run()
    except SystemExit as e:
        if e.code != 0:
            print(f"Scraper exited with code {e.code}")
    finally:
        scraper.PRODUCTS_FILE = original_products_file
        temp_path.unlink(missing_ok=True)


def main():
    print("Running scraper against first 3 products...")
    run_scraper_subset()
    print()

    results = []

    results.append(check(
        "Database file exists",
        DB_PATH.exists(),
        str(DB_PATH),
    ))

    if not DB_PATH.exists():
        print("\nFAIL — database not created, skipping remaining checks.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    results.append(check(
        "price_history table exists",
        "price_history" in tables,
        f"tables found: {tables}",
    ))

    cutoff = (datetime.utcnow() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    count = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE checked_at >= ?", (cutoff,)
    ).fetchone()[0]
    results.append(check(
        "At least 1 row inserted in the last 5 minutes",
        count >= 1,
        f"{count} row(s) found since {cutoff}",
    ))

    bad_rows = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE price <= 0 OR product_id IS NULL"
    ).fetchone()[0]
    results.append(check(
        "All rows have price > 0 and non-null product_id",
        bad_rows == 0,
        f"{bad_rows} invalid row(s) found",
    ))

    conn.close()

    print()
    if all(results):
        print("All checks passed.")
        sys.exit(0)
    else:
        failed = sum(1 for r in results if not r)
        print(f"{failed} check(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
