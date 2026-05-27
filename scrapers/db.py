# scrapers/db.py
"""Shared SQLite initialization and connection management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent

_VPS_DB = Path("/opt/data/prices.db")
_VPS_PRODUCTS = Path("/opt/scrapers/products.json")


def get_db_path() -> Path:
    if _VPS_DB.exists() or _VPS_PRODUCTS.exists():
        return _VPS_DB
    return _REPO_ROOT / "data" / "prices.db"


DB_PATH = get_db_path()


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            trigger_price REAL NOT NULL,
            seven_day_avg REAL NOT NULL,
            drop_pct REAL NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alert_product
        ON alert_log (product_id, sent_at)
    """)
    conn.commit()


@contextmanager
def get_connection():
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()
