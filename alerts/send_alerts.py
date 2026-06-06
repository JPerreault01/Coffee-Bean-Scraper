# alerts/send_alerts.py
"""
Price drop alert system for Coffee Beans site.
Detects drops > 10% vs 7-day average and sends Beehiiv email alerts.
Records sent alerts to avoid duplicate sends.

Dependencies:
  pip install requests

Run:
  /opt/venv/bin/python3 /opt/alerts/send_alerts.py
"""

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# BASE_DIR is /opt on the VPS (this file lives at /opt/alerts/send_alerts.py) and
# the repo root locally — so the same relative paths resolve correctly in both.
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from scrapers.db import get_connection  # noqa: E402

ENV_FILE = Path("/opt/.env") if Path("/opt/.env").exists() else (BASE_DIR / ".env")
LOG_PATH = BASE_DIR / "data" / "alerts.log"
PRODUCTS_FILE = (
    Path("/opt/scrapers/products.json")
    if Path("/opt/scrapers/products.json").exists()
    else (BASE_DIR / "scrapers" / "products.json")
)

DROP_THRESHOLD = 0.10  # 10% drop triggers alert

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


def get_current_price(conn: sqlite3.Connection, product_id: str) -> tuple[float, float] | None:
    """Return (current_price, price_per_oz) for the most recent record."""
    row = conn.execute(
        """
        SELECT price, price_per_oz
        FROM price_history
        WHERE product_id = ?
        ORDER BY checked_at DESC
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def get_seven_day_avg(conn: sqlite3.Connection, product_id: str) -> float | None:
    """Return average price over the last 7 days (excluding the most recent record)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    row = conn.execute(
        """
        SELECT AVG(price)
        FROM price_history
        WHERE product_id = ?
          AND checked_at >= ?
          AND id != (
              SELECT id FROM price_history
              WHERE product_id = ?
              ORDER BY checked_at DESC
              LIMIT 1
          )
        """,
        (product_id, cutoff, product_id),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def already_alerted(conn: sqlite3.Connection, product_id: str, current_price: float) -> bool:
    """Return True if we already sent an alert for this price level today."""
    today = datetime.now(timezone.utc).date().isoformat()
    row = conn.execute(
        """
        SELECT id FROM alert_log
        WHERE product_id = ?
          AND trigger_price = ?
          AND date(sent_at) = ?
        """,
        (product_id, current_price, today),
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
        (product_id, trigger_price, seven_day_avg, round(drop_pct * 100, 2)),
    )
    conn.commit()


def build_affiliate_url(product: dict) -> str:
    asin = product.get("amazon_asin")
    tag = product.get("affiliate_tag") or "coffeebeanind-20"
    if asin:
        return f"https://www.amazon.com/dp/{asin}?tag={tag}"
    roaster_url = product.get("roaster_url", "")
    if roaster_url:
        sep = "&" if "?" in roaster_url else "?"
        return f"{roaster_url}{sep}ref={tag}"
    return product.get("roaster_url", "")


def send_beehiiv_alert(
    product: dict,
    current_price: float,
    avg_price: float,
    drop_pct: float,
    price_per_oz: float | None,
    env: dict,
) -> bool:
    api_key = env.get("BEEHIIV_API_KEY", "")
    pub_id = env.get("BEEHIIV_PUBLICATION_ID", "")

    if not api_key or not pub_id:
        log.error("BEEHIIV_API_KEY or BEEHIIV_PUBLICATION_ID not set in /opt/.env")
        return False

    affiliate_url = build_affiliate_url(product)
    name = product["name"]
    drop_pct_display = round(drop_pct * 100, 1)
    savings = round(avg_price - current_price, 2)

    subject = f"Price Drop: {name} is {drop_pct_display}% off right now"

    html_body = f"""
<h2>Price Drop Alert: {name}</h2>
<table style="border-collapse:collapse;font-family:sans-serif;">
  <tr><td style="padding:6px 12px;font-weight:bold;">Current price</td>
      <td style="padding:6px 12px;color:#2a9d2a;font-size:1.2em;">${current_price:.2f}</td></tr>
  <tr><td style="padding:6px 12px;font-weight:bold;">7-day average</td>
      <td style="padding:6px 12px;">${avg_price:.2f}</td></tr>
  <tr><td style="padding:6px 12px;font-weight:bold;">You save</td>
      <td style="padding:6px 12px;">${savings:.2f} ({drop_pct_display}%)</td></tr>
  {'<tr><td style="padding:6px 12px;font-weight:bold;">Price / oz</td><td style="padding:6px 12px;">$' + f'{price_per_oz:.3f}' + '</td></tr>' if price_per_oz else ''}
</table>
<br>
<a href="{affiliate_url}" style="
  background:#c0392b;color:#fff;padding:12px 24px;
  text-decoration:none;border-radius:4px;font-weight:bold;
">Shop Now →</a>
<br><br>
<small style="color:#999;">
  You're receiving this because you subscribed to price alerts on CoffeeBeans.
  <a href="{{{{ unsubscribe_url }}}}">Unsubscribe</a>
</small>
"""

    text_body = (
        f"Price Drop: {name}\n\n"
        f"Current price: ${current_price:.2f}\n"
        f"7-day average: ${avg_price:.2f}\n"
        f"You save: ${savings:.2f} ({drop_pct_display}%)\n"
        + (f"Price/oz: ${price_per_oz:.3f}\n" if price_per_oz else "")
        + f"\nShop now: {affiliate_url}\n"
    )

    # Beehiiv send email via API (broadcasts)
    url = f"https://api.beehiiv.com/v2/publications/{pub_id}/broadcasts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "subject": subject,
        "content": {
            "html": html_body,
            "text": text_body,
        },
        "send_at": None,  # send immediately
        "audience": {
            "segment_filters": [
                {
                    "field": "custom_fields.price_alerts",
                    "value": "true",
                    "operator": "is",
                }
            ]
        },
        "platform": "email",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        log.info("Beehiiv broadcast created for %s (%.1f%% drop)", name, drop_pct_display)
        return True
    except requests.HTTPError as exc:
        log.error("Beehiiv API error: %s — %s", exc, exc.response.text if exc.response else "")
        return False
    except Exception as exc:
        log.error("Beehiiv send failed: %s", exc)
        return False


def run() -> None:
    env = load_env()

    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)

    with open(PRODUCTS_FILE) as f:
        products = json.load(f)
    products_by_id = {p["id"]: p for p in products}

    alerts_sent = 0
    checked = 0

    with get_connection() as conn:
        for product_id, product in products_by_id.items():
            current = get_current_price(conn, product_id)
            if current is None:
                log.debug("No price data for %s — skipping", product_id)
                continue

            current_price, price_per_oz = current
            avg = get_seven_day_avg(conn, product_id)

            if avg is None:
                log.debug("Not enough history for %s — skipping", product_id)
                continue

            checked += 1
            drop_pct = (avg - current_price) / avg

            if drop_pct < DROP_THRESHOLD:
                log.debug(
                    "%s: price $%.2f vs avg $%.2f (%.1f%% — below threshold)",
                    product["name"],
                    current_price,
                    avg,
                    drop_pct * 100,
                )
                continue

            if already_alerted(conn, product_id, current_price):
                log.info("%s: already alerted at this price today — skipping", product["name"])
                continue

            log.info(
                "ALERT: %s dropped %.1f%% ($%.2f → $%.2f)",
                product["name"],
                drop_pct * 100,
                avg,
                current_price,
            )

            sent = send_beehiiv_alert(product, current_price, avg, drop_pct, price_per_oz, env)
            if sent:
                record_alert(conn, product_id, current_price, avg, drop_pct)
                alerts_sent += 1

    log.info("Done. Checked %d products, sent %d alerts.", checked, alerts_sent)


if __name__ == "__main__":
    run()
