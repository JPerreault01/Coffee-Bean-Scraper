import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PRODUCTS_FILE = REPO_ROOT / "scrapers" / "products.json"
DB_PATH = REPO_ROOT / "data" / "prices.db"


def init_db(conn):
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


def seed():
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        all_products = json.load(f)

    products = all_products[:5]
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    now = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    summary = []

    for idx, product in enumerate(products):
        pid = product["id"]
        weight_oz = product.get("weight_oz", 12.0)

        base_price_per_oz = random.uniform(0.80, 1.80)
        base_price = round(weight_oz * base_price_per_oz, 2)

        # 29 historical prices: day -29 through day -1
        historical = []
        for days_ago in range(29, 0, -1):
            variance = random.uniform(-0.04, 0.04)
            price = round(base_price * (1 + variance), 2)
            historical.append((days_ago, price))

        # today's price
        if idx == 0:
            # trigger the alert: 15% below 7-day average
            last_7_prices = [p for (_, p) in historical[-7:]]
            seven_day_avg = sum(last_7_prices) / 7
            today_price = round(seven_day_avg * 0.85, 2)
        else:
            variance = random.uniform(-0.04, 0.04)
            today_price = round(base_price * (1 + variance), 2)

        all_records = historical + [(0, today_price)]

        for days_ago, price in all_records:
            checked_at = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            price_per_oz = round(price / weight_oz, 4)
            conn.execute(
                "INSERT INTO price_history (product_id, price, source, weight_oz, price_per_oz, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, price, "seed", weight_oz, price_per_oz, checked_at),
            )

        conn.commit()

        last_7_prices = [p for (_, p) in historical[-7:]]
        seven_day_avg = sum(last_7_prices) / 7
        pct_change = (today_price - seven_day_avg) / seven_day_avg * 100

        summary.append({
            "product_id": pid,
            "days_seeded": len(all_records),
            "current_price": today_price,
            "seven_day_avg": seven_day_avg,
            "pct_change": pct_change,
        })

    conn.close()

    print(f"\n{'product_id':<35} {'days':>4} {'current':>9} {'7d avg':>9} {'% change':>9}")
    print("-" * 72)
    for row in summary:
        print(
            f"{row['product_id']:<35} {row['days_seeded']:>4} "
            f"${row['current_price']:>8.2f} ${row['seven_day_avg']:>8.2f} "
            f"{row['pct_change']:>+8.1f}%"
        )
    print()


if __name__ == "__main__":
    seed()
