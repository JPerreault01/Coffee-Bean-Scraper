# scrapers/generate_review.py
"""
AI review draft generator for Coffee Beans site.
Loads product data + price history, builds a prompt, and sends to Claude or MiniMax API.
Saves the draft to /opt/drafts/[product-id]-[date].md and prints to stdout.

Usage:
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --api minimax
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --api claude

Dependencies:
  pip install requests anthropic
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENV_FILE = Path("/opt/.env")
DB_PATH = Path("/opt/data/prices.db")
PRODUCTS_FILE = Path("/opt/scrapers/products.json")
STYLE_GUIDE_FILE = Path("/opt/scrapers/style_guide.txt")
DRAFTS_DIR = Path("/opt/drafts")


def load_env() -> dict:
    import os
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


def load_products() -> dict:
    if not PRODUCTS_FILE.exists():
        print(f"ERROR: products.json not found at {PRODUCTS_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(PRODUCTS_FILE) as f:
        products = json.load(f)
    return {p["id"]: p for p in products}


def load_style_guide() -> str:
    if STYLE_GUIDE_FILE.exists():
        return STYLE_GUIDE_FILE.read_text().strip()
    return (
        "Write in a direct, slightly opinionated voice — as if you've actually tasted this coffee. "
        "No filler phrases ('in conclusion', 'it's worth noting'). No fake hedging ('some may find', 'could potentially'). "
        "Specific over vague: 'tastes like burnt rubber at 205°F' beats 'can be harsh'. "
        "Short sentences preferred. British or American spelling, consistent throughout."
    )


def get_price_history(product_id: str) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """
        SELECT price, price_per_oz, source, checked_at
        FROM price_history
        WHERE product_id = ?
          AND checked_at >= ?
        ORDER BY checked_at DESC
        """,
        (product_id, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_price_summary(history: list[dict]) -> str:
    if not history:
        return "No price history available."

    prices = [r["price"] for r in history]
    current = prices[0]
    low = min(prices)
    high = max(prices)
    avg = sum(prices) / len(prices)

    per_oz_values = [r["price_per_oz"] for r in history if r["price_per_oz"]]
    per_oz_str = f"${per_oz_values[0]:.3f}/oz" if per_oz_values else "N/A"

    vs_avg = ((current - avg) / avg) * 100
    trend = "above" if vs_avg > 0 else "below"

    return (
        f"Current price: ${current:.2f}\n"
        f"30-day low: ${low:.2f} | 30-day high: ${high:.2f} | 30-day avg: ${avg:.2f}\n"
        f"Current price is {abs(vs_avg):.1f}% {trend} the 30-day average.\n"
        f"Price per oz: {per_oz_str}\n"
        f"Data points: {len(history)} checks over the last 30 days."
    )


def build_prompt(product: dict, price_summary: str, style_guide: str) -> str:
    best_brew = ", ".join(product.get("best_brew_methods", []))
    flavor_notes = ", ".join(product.get("flavor_notes", []))
    affiliate_tag = product.get("affiliate_tag", "")
    asin = product.get("amazon_asin", "")
    affiliate_url = (
        f"https://www.amazon.com/dp/{asin}?tag={affiliate_tag}"
        if asin and affiliate_tag
        else product.get("roaster_url", "")
    )

    return f"""You are writing a coffee bean product review for a niche affiliate website. The review will be edited by a human before publication.

## Writing style instructions
{style_guide}

## Product specifications
- Name: {product['name']}
- Brand: {product.get('brand', 'N/A')}
- Roast level: {product.get('roast_level', 'N/A')}
- Origin: {product.get('origin', 'N/A')}
- Process method: {product.get('process_method', 'N/A')}
- Weight: {product.get('weight_oz', 'N/A')} oz
- Best brew methods: {best_brew or 'N/A'}
- Flavor notes (from producer): {flavor_notes or 'N/A'}
- Affiliate link: {affiliate_url}

## Price history (last 30 days)
{price_summary}

## Required output format

Write the review exactly in this structure — no additional sections, no preamble:

## {product['name']} Review

**One-line verdict**: [Direct, specific, one sentence — no hedge words]

| Spec | Detail |
|---|---|
| Roast | {product.get('roast_level', '')} |
| Origin | {product.get('origin', '')} |
| Process | {product.get('process_method', '')} |
| Best for | {best_brew} |
| Price/oz | $X.XX |

### Tasting notes
- [Specific note with context — e.g. "Dark chocolate bitterness that fades clean, not lingering"]
- [3–5 bullets total. No vague descriptors without explanation.]

### Who it's for
[1–2 sentences. Be specific — "espresso drinkers who want low acidity" not "coffee lovers"]

### Who should skip it
[1–2 sentences. Be honest.]

### Price analysis
[Is it good value right now based on the 30-day price history? When is the right time to buy?]

### Rating: X/10
[One sentence explaining the score.]

---
*[Affiliate disclosure: links in this review are affiliate links. Prices accurate at time of writing.]*
"""


def stream_claude(prompt: str, env: dict) -> str:
    import anthropic

    api_key = env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY not set in /opt/.env")

    client = anthropic.Anthropic(api_key=api_key)
    full_text = []

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_text.append(text)

    print()
    return "".join(full_text)


def stream_minimax(prompt: str, env: dict) -> str:
    import requests

    api_key = env.get("MINIMAX_API_KEY", "")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY not set in /opt/.env")

    url = "https://api.minimaxi.chat/v1/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "MiniMax-Text-01",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.7,
        "stream": True,
    }

    full_text = []
    with requests.post(url, json=payload, headers=headers, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            print(content, end="", flush=True)
                            full_text.append(content)
                except json.JSONDecodeError:
                    continue

    print()
    return "".join(full_text)


def save_draft(product_id: str, content: str) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = DRAFTS_DIR / f"{product_id}-{date_str}.md"
    path.write_text(content)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AI coffee bean review draft")
    parser.add_argument("product_id", help="Product ID from products.json")
    parser.add_argument(
        "--api",
        choices=["claude", "minimax"],
        default=None,
        help="Which API to use (default: use whichever key is available)",
    )
    args = parser.parse_args()

    env = load_env()
    products = load_products()

    if args.product_id not in products:
        print(f"ERROR: Product '{args.product_id}' not found in products.json", file=sys.stderr)
        print(f"Available IDs: {', '.join(products.keys())}", file=sys.stderr)
        sys.exit(1)

    product = products[args.product_id]
    history = get_price_history(args.product_id)
    price_summary = build_price_summary(history)
    style_guide = load_style_guide()
    prompt = build_prompt(product, price_summary, style_guide)

    # Determine which API to use
    api = args.api
    if api is None:
        if env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY"):
            api = "claude"
        elif env.get("MINIMAX_API_KEY"):
            api = "minimax"
        else:
            print("ERROR: No API key found. Set CLAUDE_API_KEY or MINIMAX_API_KEY in /opt/.env", file=sys.stderr)
            sys.exit(1)

    print(f"Generating review for: {product['name']} (API: {api})\n", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    if api == "claude":
        draft = stream_claude(prompt, env)
    else:
        draft = stream_minimax(prompt, env)

    path = save_draft(args.product_id, draft)
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"Draft saved to: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
