import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PRODUCTS_FILE = REPO_ROOT / "scrapers" / "products.json"
FLAVORS_FILE = REPO_ROOT / "data" / "flavors.json"

sys.path.insert(0, str(REPO_ROOT))

from scrapers.db import DB_PATH  # noqa: E402


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


class TestFlavorJSON(unittest.TestCase):
    _data = None

    @classmethod
    def setUpClass(cls):
        if FLAVORS_FILE.exists():
            with open(FLAVORS_FILE, encoding="utf-8") as f:
                cls._data = json.load(f)

    def _skip_if_missing(self):
        if self._data is None:
            self.skipTest(
                "data/flavors.json not found — run scrapers/build_flavors_json.py first"
            )

    def test_flavors_json_exists(self):
        if not FLAVORS_FILE.exists():
            self.skipTest(
                "data/flavors.json not found — run scrapers/build_flavors_json.py first"
            )

    def test_all_products_have_families(self):
        self._skip_if_missing()
        for product in self._data["products"]:
            self.assertGreater(
                len(product.get("note_families", [])),
                0,
                f"{product['id']} has empty note_families",
            )

    def test_scores_in_range(self):
        self._skip_if_missing()
        score_keys = ("acidity", "body", "sweetness", "bitterness", "roast_intensity")
        for product in self._data["products"]:
            scores = product.get("scores", {})
            for key in score_keys:
                val = scores.get(key)
                self.assertIsInstance(
                    val, int, f"{product['id']}.scores.{key} is not int"
                )
                self.assertGreaterEqual(
                    val, 1, f"{product['id']}.scores.{key} < 1"
                )
                self.assertLessEqual(
                    val, 5, f"{product['id']}.scores.{key} > 5"
                )

    def test_affiliate_urls_not_bare(self):
        self._skip_if_missing()
        for product in self._data["products"]:
            url = product.get("affiliate_url", "")
            if url.startswith("https://www.amazon.com/dp/"):
                self.assertIn(
                    "?tag=",
                    url,
                    f"{product['id']} has Amazon URL without affiliate tag: {url}",
                )
