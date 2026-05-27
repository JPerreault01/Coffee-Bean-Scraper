# alerts/send_alerts.py
"""
Price drop alert sender. Detects when a product's price has dropped >10%
below its 7-day average and sends an email via Beehiiv Broadcasts API.

Cron: 15 6 * * * /opt/venv/bin/python3 /opt/alerts/send_alerts.py >> /opt/data/alerts.log 2>&1
"""

import json
import os
import sqlite3
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path("/opt")
DATA_DIR = BASE_DIR / "data"
SCRAPERS_DIR = BASE_DIR / "scrapers"
ENV_FILE = BASE_DIR / ".env"
PRODUCTS_FILE = SCRAPERS_DIR / "products.json"
DB_FILE = DATA_DIR / "prices.db"

PRICE_DROP_THRESHOLD = 0.10  # 10% drop triggers an alert
LOOKBACK_DAYS = 7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def load_env(path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_alert_log_table(conn: sqlite3.Connection) -> None:
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
    conn.commit()


def get_current_price(conn: sqlite3.Connection, product_id: str) -> float | None:
    row = conn.execute(
        """
        SELECT price FROM price_history
        WHERE product_id = ?
        ORDER BY checked_at DESC
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    return row["price"] if row else None


def get_seven_day_avg(conn: sqlite3.Connection, product_id: str) -> float | None:
    cutoff = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    row = conn.execute(
        """
        SELECT AVG(price) as avg_price
        FROM price_history
        WHERE product_id = ?
          AND checked_at >= ?
        """,
        (product_id, cutoff),
    ).fetchone()
    if row and row["avg_price"] is not None:
        return float(row["avg_price"])
    return None


def get_current_price_per_oz(conn: sqlite3.Connection, product_id: str) -> float | None:
    row = conn.execute(
        """
        SELECT price_per_oz FROM price_history
        WHERE product_id = ? AND price_per_oz IS NOT NULL
        ORDER BY checked_at DESC
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    return row["price_per_oz"] if row else None


def already_alerted_today(conn: sqlite3.Connection, product_id: str, trigger_price: float) -> bool:
    today = datetime.utcnow().date().isoformat()
    row = conn.execute(
        """
        SELECT id FROM alert_log
        WHERE product_id = ?
          AND trigger_price = ?
          AND date(sent_at) = ?
        """,
        (product_id, trigger_price, today),
    ).fetchone()
    return row is not None


def record_alert(
    conn: sqlite3.Connection,
    product_id: str,
    trigger_price: float,
    seven_day_avg: float,
    drop_pct: float,
) -> None:
    conn.execute(
        """
        INSERT INTO alert_log (product_id, trigger_price, seven_day_avg, drop_pct)
        VALUES (?, ?, ?, ?)
        """,
        (product_id, trigger_price, seven_day_avg, drop_pct),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Beehiiv email sender
# ---------------------------------------------------------------------------

def build_email_html(
    product_name: str,
    current_price: float,
    seven_day_avg: float,
    drop_pct: float,
    price_per_oz: float | None,
    affiliate_url: str,
) -> str:
    ppo_line = ""
    if price_per_oz:
        ppo_line = f"<p style='margin:0 0 8px;'><strong>Price per oz:</strong> ${price_per_oz:.2f}</p>"

    return f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#2c1810;margin:0 0 16px;">Price Drop Alert: {product_name}</h2>

  <div style="background:#f8f3ee;border-left:4px solid #c8681e;padding:16px;margin:0 0 20px;border-radius:4px;">
    <p style="margin:0 0 8px;font-size:24px;font-weight:bold;color:#c8681e;">
      Now: ${current_price:.2f}
    </p>
    <p style="margin:0 0 8px;color:#666;">
      7-day average: ${seven_day_avg:.2f} &nbsp;|&nbsp;
      <strong style="color:#2d7a22;">You save {drop_pct:.1f}%</strong>
    </p>
    {ppo_line}
  </div>

  <p style="margin:0 0 20px;color:#333;">
    This is one of the better prices we've tracked for {product_name} over the past week.
    These drops don't always last long.
  </p>

  <a href="{affiliate_url}"
     style="display:inline-block;background:#c8681e;color:#fff;padding:12px 24px;
            text-decoration:none;border-radius:4px;font-weight:bold;font-size:16px;">
    See Current Price on Amazon →
  </a>

  <p style="margin:24px 0 0;font-size:12px;color:#999;">
    You're receiving this because you subscribed to price-drop alerts.
    Prices may change at any time. Links are affiliate links.
  </p>
</div>
"""


def send_beehiiv_broadcast(
    api_key: str,
    publication_id: str,
    subject: str,
    html_body: str,
    product_name: str,
) -> bool:
    """Send a broadcast via Beehiiv API v2."""
    url = f"https://api.beehiiv.com/v2/publications/{publication_id}/broadcasts"

    payload = {
        "subject": subject,
        "content": {
            "free": {
                "web": html_body,
                "email": html_body,
            }
        },
        "audience": "free",
        "send_at": "now",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        broadcast_id = data.get("data", {}).get("id", "unknown")
        log.info(f"Beehiiv broadcast sent for '{product_name}' — id: {broadcast_id}")
        return True
    except requests.RequestException as e:
        log.error(f"Beehiiv API error for '{product_name}': {e}")
        if hasattr(e, "response") and e.response is not None:
            log.error(f"Response body: {e.response.text}")
        return False


def build_affiliate_url(product: dict) -> str:
    asin = product.get("amazon_asin")
    tag = product.get("affiliate_tag", "mycoffeebeans-20")
    if asin and tag:
        return f"https://www.amazon.com/dp/{asin}?tag={tag}"
    roaster_url = product.get("roaster_url", "")
    if roaster_url and tag:
        separator = "&" if "?" in roaster_url else "?"
        return f"{roaster_url}{separator}aff={tag}"
    return roaster_url or ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_env(ENV_FILE)

    beehiiv_api_key = os.environ.get("BEEHIIV_API_KEY", "")
    beehiiv_pub_id = os.environ.get("BEEHIIV_PUBLICATION_ID", "")

    if not beehiiv_api_key or not beehiiv_pub_id:
        log.error("BEEHIIV_API_KEY and BEEHIIV_PUBLICATION_ID must be set in /opt/.env")
        sys.exit(1)

    if not PRODUCTS_FILE.exists():
        log.error(f"products.json not found at {PRODUCTS_FILE}")
        sys.exit(1)

    with open(PRODUCTS_FILE) as f:
        products = json.load(f)
    products_by_id = {p["id"]: p for p in products}

    if not DB_FILE.exists():
        log.warning(f"Database not found at {DB_FILE} — run price_scraper.py first")
        sys.exit(0)

    conn = get_db()
    ensure_alert_log_table(conn)

    alerts_sent = 0

    for product in products:
        pid = product["id"]
        name = product.get("name", pid)

        current_price = get_current_price(conn, pid)
        if current_price is None:
            log.debug(f"No price data for {name}")
            continue

        seven_day_avg = get_seven_day_avg(conn, pid)
        if seven_day_avg is None:
            log.debug(f"Not enough history for {name}")
            continue

        # Skip if price is not meaningfully below the 7-day average
        if seven_day_avg <= 0:
            continue

        drop_pct = (seven_day_avg - current_price) / seven_day_avg
        if drop_pct < PRICE_DROP_THRESHOLD:
            continue

        # Don't re-send for the same price today
        if already_alerted_today(conn, pid, current_price):
            log.info(f"Alert already sent today for {name} at ${current_price:.2f}")
            continue

        price_per_oz = get_current_price_per_oz(conn, pid)
        affiliate_url = build_affiliate_url(product)

        subject = f"Price drop: {name} is down {drop_pct:.0%} — ${current_price:.2f}"
        html_body = build_email_html(
            product_name=name,
            current_price=current_price,
            seven_day_avg=seven_day_avg,
            drop_pct=drop_pct * 100,
            price_per_oz=price_per_oz,
            affiliate_url=affiliate_url,
        )

        log.info(
            f"Sending alert for {name}: ${current_price:.2f} vs ${seven_day_avg:.2f} avg "
            f"({drop_pct:.1%} drop)"
        )

        sent = send_beehiiv_broadcast(
            api_key=beehiiv_api_key,
            publication_id=beehiiv_pub_id,
            subject=subject,
            html_body=html_body,
            product_name=name,
        )

        if sent:
            record_alert(conn, pid, current_price, seven_day_avg, drop_pct * 100)
            alerts_sent += 1

    conn.close()
    log.info(f"Alert check complete — {alerts_sent} alert(s) sent")


if __name__ == "__main__":
    main()
