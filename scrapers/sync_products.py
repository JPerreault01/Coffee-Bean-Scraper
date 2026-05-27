# scrapers/sync_products.py
"""
Syncs products.json into the SQLite products table.

Run this whenever products.json is updated — adds new products, updates
existing ones, and leaves price_history untouched.

Usage:
  python scrapers/sync_products.py                  # uses default paths
  python scrapers/sync_products.py --dry-run        # prints what would change
  /opt/venv/bin/python3 /opt/scrapers/sync_products.py

Dependencies: none (stdlib only)
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — resolved relative to this script so it works locally and on VPS
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

PRODUCTS_FILE = SCRIPT_DIR / "products.json"
DB_PATH = REPO_ROOT / "data" / "prices.db"

# On VPS, override to /opt paths:
VPS_PRODUCTS = Path("/opt/scrapers/products.json")
VPS_DB = Path("/opt/data/prices.db")
if VPS_DB.exists() or VPS_PRODUCTS.exists():
    PRODUCTS_FILE = VPS_PRODUCTS
    DB_PATH = VPS_DB


def init_products_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id               TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            brand            TEXT,
            roast_level      TEXT,
            origin           TEXT,
            process_method   TEXT,
            weight_oz        REAL,
            amazon_asin      TEXT,
            roaster_url      TEXT,
            affiliate_tag    TEXT,
            best_brew_methods TEXT,
            flavor_notes     TEXT,
            acidity          INTEGER,
            body             INTEGER,
            sweetness        INTEGER,
            bitterness       INTEGER,
            roast_intensity  INTEGER,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add flavor vector columns to existing tables that predate this schema
    existing = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    flavor_cols = {
        "acidity": "INTEGER",
        "body": "INTEGER",
        "sweetness": "INTEGER",
        "bitterness": "INTEGER",
        "roast_intensity": "INTEGER",
    }
    for col, col_type in flavor_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} {col_type}")
    conn.commit()


def load_products(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: products.json not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def upsert_products(
    conn: sqlite3.Connection, products: list[dict], dry_run: bool = False
) -> tuple[int, int]:
    """Upsert all products. Returns (inserted, updated) counts."""
    inserted = 0
    updated = 0

    for p in products:
        existing = conn.execute(
            "SELECT id FROM products WHERE id = ?", (p["id"],)
        ).fetchone()

        best_brew = json.dumps(p.get("best_brew_methods", []))
        flavor_notes = json.dumps(p.get("flavor_notes", []))

        row = (
            p["id"],
            p.get("name", ""),
            p.get("brand"),
            p.get("roast_level"),
            p.get("origin"),
            p.get("process_method"),
            p.get("weight_oz"),
            p.get("amazon_asin"),
            p.get("roaster_url"),
            p.get("affiliate_tag"),
            best_brew,
            flavor_notes,
            p.get("acidity"),
            p.get("body"),
            p.get("sweetness"),
            p.get("bitterness"),
            p.get("roast_intensity"),
        )

        if existing:
            action = "UPDATE"
            updated += 1
        else:
            action = "INSERT"
            inserted += 1

        if dry_run:
            print(f"  [{action}] {p['id']} — {p.get('name', '')}")
            continue

        conn.execute(
            """
            INSERT INTO products (
                id, name, brand, roast_level, origin, process_method,
                weight_oz, amazon_asin, roaster_url, affiliate_tag,
                best_brew_methods, flavor_notes,
                acidity, body, sweetness, bitterness, roast_intensity,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name             = excluded.name,
                brand            = excluded.brand,
                roast_level      = excluded.roast_level,
                origin           = excluded.origin,
                process_method   = excluded.process_method,
                weight_oz        = excluded.weight_oz,
                amazon_asin      = excluded.amazon_asin,
                roaster_url      = excluded.roaster_url,
                affiliate_tag    = excluded.affiliate_tag,
                best_brew_methods = excluded.best_brew_methods,
                flavor_notes     = excluded.flavor_notes,
                acidity          = excluded.acidity,
                body             = excluded.body,
                sweetness        = excluded.sweetness,
                bitterness       = excluded.bitterness,
                roast_intensity  = excluded.roast_intensity,
                updated_at       = CURRENT_TIMESTAMP
            """,
            row,
        )

    if not dry_run:
        conn.commit()

    return inserted, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync products.json → SQLite products table")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted/updated without writing to DB",
    )
    parser.add_argument(
        "--db", type=Path, default=None, help="Override SQLite DB path"
    )
    parser.add_argument(
        "--products", type=Path, default=None, help="Override products.json path"
    )
    args = parser.parse_args()

    db_path = args.db or DB_PATH
    products_path = args.products or PRODUCTS_FILE

    products = load_products(products_path)
    print(f"Loaded {len(products)} products from {products_path}")

    if args.dry_run:
        print("\nDry run — no changes will be written:\n")
        # Still connect to show insert vs update status
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            init_products_table(conn)
        else:
            print("  (DB does not exist yet — all would be INSERTs)")
            for p in products:
                print(f"  [INSERT] {p['id']} — {p.get('name', '')}")
            return
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        init_products_table(conn)

    inserted, updated = upsert_products(conn, products, dry_run=args.dry_run)

    if not args.dry_run:
        conn.close()
        print(f"\nDone: {inserted} inserted, {updated} updated → {db_path}")
    else:
        conn.close()
        print(f"\nDry run complete: {inserted} would insert, {updated} would update")


if __name__ == "__main__":
    main()
