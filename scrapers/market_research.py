#!/usr/bin/env python3
"""
market_research.py — Build a source-attributed price analysis section using the ECC
market-research skill.

Queries the local SQLite price history database, computes statistics, then calls
claude-haiku to generate a 2–3 paragraph price analysis ready to embed in a review.

Fetches the ECC market-research SKILL.md at runtime and caches it locally.
Falls back to a built-in prompt if the fetch fails.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

ECC_SKILL_URL = (
    "https://raw.githubusercontent.com/affaan-m/ECC/main/skills/market-research/SKILL.md"
)
SKILL_CACHE_PATH = (
    Path(__file__).parent.parent / ".cache" / "ecc_market_research_skill.md"
)

FALLBACK_SKILL = """\
You are a market research analyst specializing in consumer product pricing and value
assessment.

Your methodology:
1. DATA: Ground every claim in the provided price history data — no invented sources.
2. CONTEXT: Compare the current price to the historical average and range.
3. TREND: Identify whether prices are rising, falling, or stable based on recent vs.
   prior data.
4. RECOMMENDATION: Give a clear, actionable buy/wait assessment with reasoning.
5. ATTRIBUTION: Always attribute factual claims to "price history data".

Output format: 2–3 focused paragraphs covering:
- Current price vs. historical average (state both figures explicitly).
- Best price seen in the window and whether now is a good time to buy.
- Buy/wait recommendation with a clear reason.

No hedging. No invented data. If data is insufficient, state that explicitly."""


def load_skill(url: str, cache_path: Path) -> str:
    """
    Fetch ECC skill instructions from GitHub, caching locally.

    Returns the cached or freshly fetched content. Falls back to FALLBACK_SKILL
    if the network request fails.
    """
    if cache_path.exists():
        logger.info(f"Using cached skill from {cache_path}")
        return cache_path.read_text()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            content = resp.read().decode()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(content)
        logger.info(f"Fetched and cached skill to {cache_path}")
        return content
    except Exception as exc:
        logger.warning(f"Could not fetch skill from {url}: {exc}. Using built-in fallback.")
        return FALLBACK_SKILL


def load_product(products_path: Path, product_id: str) -> dict[str, Any]:
    """Load a product record from products.json by ID."""
    with open(products_path) as f:
        products = json.load(f)
    for product in products:
        if product.get("id") == product_id:
            return product
    raise ValueError(f"Product '{product_id}' not found in {products_path}")


def fetch_price_history(db_path: Path, product_id: str) -> list[dict[str, Any]]:
    """
    Query price history from the SQLite database.

    Returns rows ordered by checked_at descending (most recent first).
    Returns an empty list if the database does not exist or a query error occurs.
    """
    if not db_path.exists():
        logger.info(f"Database not found at {db_path}.")
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT price, checked_at FROM price_history "
            "WHERE product_id = ? ORDER BY checked_at DESC LIMIT 200",
            (product_id,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as exc:
        logger.warning(f"Database error: {exc}")
        return []


def _parse_timestamp(ts_str: str) -> datetime | None:
    """Parse an ISO 8601 timestamp string into a UTC-aware datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str.rstrip("Z").split("+")[0], fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    return None


def compute_price_stats(rows: list[dict[str, Any]], days: int) -> dict[str, Any] | None:
    """
    Compute price statistics for the given time window.

    Returns None if there are no valid rows within the window.
    """
    if not rows:
        return None

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)

    valid: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_timestamp(str(row.get("checked_at", "")))
        if ts is None:
            continue
        try:
            price = float(row["price"])
        except (TypeError, ValueError):
            continue
        if ts >= cutoff:
            valid.append({"price": price, "ts": ts})

    if not valid:
        return None

    prices = [r["price"] for r in valid]
    current_price = valid[0]["price"]
    avg_price = sum(prices) / len(prices)
    low_price = min(prices)
    high_price = max(prices)

    # Trend: last 7 days vs prior 7 days
    last_7_cutoff = now - timedelta(days=7)
    prior_7_cutoff = now - timedelta(days=14)

    last_7 = [r["price"] for r in valid if r["ts"] >= last_7_cutoff]
    prior_7 = [
        r["price"] for r in valid if prior_7_cutoff <= r["ts"] < last_7_cutoff
    ]

    trend = "flat"
    if last_7 and prior_7:
        last_avg = sum(last_7) / len(last_7)
        prior_avg = sum(prior_7) / len(prior_7)
        diff_pct = (last_avg - prior_avg) / prior_avg * 100
        if diff_pct > 2:
            trend = "rising"
        elif diff_pct < -2:
            trend = "falling"

    return {
        "current": current_price,
        "average": avg_price,
        "low": low_price,
        "high": high_price,
        "trend": trend,
        "data_points": len(prices),
    }


def product_url(product: dict[str, Any]) -> str:
    """Return the best available URL for a product (roaster URL preferred over Amazon)."""
    if product.get("roaster_url"):
        return product["roaster_url"]
    if product.get("amazon_asin"):
        tag = product.get("affiliate_tag", "")
        base = f"https://www.amazon.com/dp/{product['amazon_asin']}"
        return f"{base}?tag={tag}" if tag else base
    return "N/A"


def generate_price_analysis(
    client: anthropic.Anthropic,
    skill_content: str,
    product: dict[str, Any],
    stats: dict[str, Any] | None,
    days: int,
) -> str:
    """
    Call claude-haiku to generate a 2–3 paragraph price analysis section.

    If stats is None, generates a placeholder noting that price tracking is not active.
    """
    system = (
        f"{skill_content}\n\n"
        "---\n\n"
        "You are writing a price analysis section for a coffee product review page.\n"
        "Write 2–3 paragraphs. Attribute all factual claims to \"price history data\".\n"
        "No invented sources. No hedging language. Reference the product URL provided."
    )

    url = product_url(product)

    if stats is None:
        user = (
            f"Product: {product['name']}\n"
            f"Product URL: {url}\n\n"
            "Price tracking data is not yet available for this product. Write a placeholder "
            "price analysis section (2–3 paragraphs) noting that price tracking has not yet "
            "started for this product, and advising the reader to check the product page "
            "directly for current pricing."
        )
    else:
        user = (
            f"Product: {product['name']}\n"
            f"Analysis window: {days} days\n"
            f"Product URL: {url}\n\n"
            f"Price history data:\n"
            f"- Current price: ${stats['current']:.2f}\n"
            f"- {days}-day average: ${stats['average']:.2f}\n"
            f"- {days}-day low: ${stats['low']:.2f}\n"
            f"- {days}-day high: ${stats['high']:.2f}\n"
            f"- Price trend (last 7 days vs prior 7 days): {stats['trend']}\n"
            f"- Data points in window: {stats['data_points']}\n\n"
            "Write a 2–3 paragraph price analysis section. Include:\n"
            "1. The current price and how it compares to the average.\n"
            "2. The best price seen in the window and whether now is a good time to buy.\n"
            "3. A clear buy/wait recommendation referencing the product URL above."
        )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def main() -> None:
    """Parse arguments and generate a price analysis draft."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    parser = argparse.ArgumentParser(
        description="Generate a price analysis section using the ECC market-research skill."
    )
    parser.add_argument(
        "--product",
        required=True,
        help="Product ID from scrapers/products.json",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        metavar="N",
        help="Days of price history to consider (default: 30)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print(
            "Error: CLAUDE_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = Path(__file__).parent.parent
    products_path = repo_root / "scrapers" / "products.json"
    db_path = repo_root / "data" / "prices.db"
    drafts_dir = repo_root / "drafts"

    try:
        product = load_product(products_path, args.product)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = fetch_price_history(db_path, args.product)
    stats = compute_price_stats(rows, args.days)

    if not rows:
        logger.info(
            f"No price data found for '{args.product}' — generating placeholder section."
        )

    skill_content = load_skill(ECC_SKILL_URL, SKILL_CACHE_PATH)

    client = anthropic.Anthropic(api_key=api_key)
    analysis_text = generate_price_analysis(client, skill_content, product, stats, args.days)

    drafts_dir.mkdir(parents=True, exist_ok=True)
    output_path = drafts_dir / f"{args.product}-price-analysis.md"
    output_path.write_text(analysis_text + "\n")

    print(str(output_path))


if __name__ == "__main__":
    main()
