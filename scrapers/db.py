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
    # Per-field resolution health: one row per (product, field). Tracks the
    # last-good value/source and whether the most recent attempt succeeded.
    # A failed attempt marks the row 'stale' and KEEPS the last-good value —
    # a dead source never blanks a previously resolved field.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_data_health (
            product_id      TEXT,
            field           TEXT,
            value           TEXT,
            source          TEXT,
            status          TEXT,
            last_success_at TIMESTAMP,
            last_attempt_at TIMESTAMP,
            fail_count      INTEGER DEFAULT 0,
            error           TEXT,
            PRIMARY KEY (product_id, field)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_health_status
        ON product_data_health (status, field)
    """)
    conn.commit()


def record_health_success(conn, product_id, field, value, source) -> None:
    """Upsert a successful resolve: set value/source, status='ok',
    last_success_at=now, reset fail_count=0, clear error."""
    conn.execute(
        """
        INSERT INTO product_data_health
            (product_id, field, value, source, status,
             last_success_at, last_attempt_at, fail_count, error)
        VALUES (?, ?, ?, ?, 'ok', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, NULL)
        ON CONFLICT(product_id, field) DO UPDATE SET
            value           = excluded.value,
            source          = excluded.source,
            status          = 'ok',
            last_success_at = CURRENT_TIMESTAMP,
            last_attempt_at = CURRENT_TIMESTAMP,
            fail_count      = 0,
            error           = NULL
        """,
        (product_id, field, _as_text(value), source),
    )
    conn.commit()


def record_health_failure(conn, product_id, field, source, error) -> None:
    """Record a failed resolve: status='stale', bump fail_count, set
    last_attempt_at=now, store error. KEEPS the existing last-good value,
    source, and last_success_at (never overwrites a good value with blank)."""
    conn.execute(
        """
        INSERT INTO product_data_health
            (product_id, field, value, source, status,
             last_success_at, last_attempt_at, fail_count, error)
        VALUES (?, ?, NULL, ?, 'stale', NULL, CURRENT_TIMESTAMP, 1, ?)
        ON CONFLICT(product_id, field) DO UPDATE SET
            status          = 'stale',
            last_attempt_at = CURRENT_TIMESTAMP,
            fail_count      = product_data_health.fail_count + 1,
            error           = excluded.error
        """,
        (product_id, field, source or None, _as_text(error)),
    )
    conn.commit()


def _as_text(value) -> str | None:
    if value is None:
        return None
    return str(value)


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
