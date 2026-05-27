# scrapers/generate_review.py
"""
AI review draft generator. Loads product data and price history, builds a
structured prompt, and streams a review draft via Claude or MiniMax API.

Usage:
    python3 generate_review.py <product-id> [--api claude|minimax]

Examples:
    python3 generate_review.py lavazza-super-crema
    python3 generate_review.py stumptown-hair-bender --api claude
"""

import argparse
import json
import os
import sqlite3
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
DRAFTS_DIR = BASE_DIR / "drafts"
ENV_FILE = BASE_DIR / ".env"
PRODUCTS_FILE = SCRAPERS_DIR / "products.json"
STYLE_GUIDE_FILE = SCRAPERS_DIR / "style_guide.txt"
DB_FILE = DATA_DIR / "prices.db"

DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

PRICE_HISTORY_DAYS = 30

DEFAULT_STYLE_GUIDE = """
Writing style: Direct, opinionated, specific. Written as someone who has actually tasted the coffee.
- No filler: no "in conclusion", "it's worth noting", "at the end of the day"
- No hedging: no "some may find", "could potentially", "might"
- Specific over vague: "tastes like burnt rubber at 205°F" beats "can be harsh if over-extracted"
- Short sentences preferred. No compound clause stacking.
- Tasting notes must be earned — no "hints of chocolate" without context about roast level and brew method
""".strip()


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
# Data loading
# ---------------------------------------------------------------------------

def load_product(product_id: str) -> dict:
    if not PRODUCTS_FILE.exists():
        print(f"Error: products.json not found at {PRODUCTS_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(PRODUCTS_FILE) as f:
        products = json.load(f)
    for p in products:
        if p["id"] == product_id:
            return p
    print(f"Error: product '{product_id}' not found in products.json", file=sys.stderr)
    sys.exit(1)


def load_price_history(product_id: str) -> list[dict]:
    if not DB_FILE.exists():
        return []
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.utcnow() - timedelta(days=PRICE_HISTORY_DAYS)).isoformat()
    rows = conn.execute(
        """
        SELECT price, price_per_oz, source, checked_at
        FROM price_history
        WHERE product_id = ? AND checked_at >= ?
        ORDER BY checked_at ASC
        """,
        (product_id, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def summarise_price_history(rows: list[dict]) -> dict:
    if not rows:
        return {}
    prices = [r["price"] for r in rows]
    ppo_values = [r["price_per_oz"] for r in rows if r.get("price_per_oz")]
    return {
        "current_price": prices[-1],
        "30d_low": min(prices),
        "30d_high": max(prices),
        "30d_avg": round(sum(prices) / len(prices), 2),
        "price_per_oz": round(sum(ppo_values) / len(ppo_values), 3) if ppo_values else None,
        "data_points": len(prices),
    }


def load_style_guide() -> str:
    if STYLE_GUIDE_FILE.exists():
        return STYLE_GUIDE_FILE.read_text().strip()
    return DEFAULT_STYLE_GUIDE


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

REVIEW_TEMPLATE = """
## {name} Review

**One-line verdict**: [Direct, specific, no hedge words]

| Spec | Detail |
|---|---|
| Roast | {roast_level} |
| Origin | {origin} |
| Process | {process_method} |
| Best for | {best_brew_methods} |
| Price/oz | ${price_per_oz} |

### Tasting notes
- [Specific note]
- [3–5 bullets total, no vague descriptors without context]

### Who it's for
[1–2 sentences. Specific — "espresso drinkers who want low acidity" not "coffee lovers"]

### Who should skip it
[1–2 sentences. Honest.]

### Price analysis
[Current price vs 30-day average, value judgment, when to buy]

### Rating: X/10
[One sentence explaining the score]
""".strip()


def build_prompt(product: dict, price_summary: dict, style_guide: str) -> str:
    best_brew = ", ".join(product.get("best_brew_methods", []))
    flavor_notes = ", ".join(product.get("flavor_notes", []))
    price_per_oz = price_summary.get("price_per_oz", "unknown")
    if isinstance(price_per_oz, float):
        price_per_oz = f"{price_per_oz:.3f}"

    price_section = ""
    if price_summary:
        price_section = f"""
## Price Data (last 30 days)
- Current price: ${price_summary.get('current_price', 'N/A'):.2f}
- 30-day low: ${price_summary.get('30d_low', 'N/A'):.2f}
- 30-day high: ${price_summary.get('30d_high', 'N/A'):.2f}
- 30-day average: ${price_summary.get('30d_avg', 'N/A'):.2f}
- Price per oz: ${price_per_oz}
- Data points: {price_summary.get('data_points', 0)}
""".strip()
    else:
        price_section = "## Price Data\nNo price history available yet."

    product_section = f"""
## Product Specs
- Name: {product.get('name')}
- Brand: {product.get('brand')}
- Roast level: {product.get('roast_level')}
- Origin: {product.get('origin')}
- Process method: {product.get('process_method')}
- Weight: {product.get('weight_oz')} oz
- Best brew methods: {best_brew}
- Known flavor notes: {flavor_notes}
""".strip()

    review_format = f"""
## Output format (use this exact structure)
{REVIEW_TEMPLATE}
""".strip()

    return f"""You are writing a coffee product review for a niche affiliate site. Write as someone who has actually tasted this coffee and has a clear opinion.

## Writing style guide
{style_guide}

{product_section}

{price_section}

{review_format}

Write the complete review now. Do not add commentary before or after. Start directly with the "## {product.get('name')} Review" header."""


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

def generate_with_claude(prompt: str, api_key: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    full_response = []

    print("Generating with Claude...\n", file=sys.stderr)

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_response.append(text)

    print("\n", file=sys.stderr)
    return "".join(full_response)


# ---------------------------------------------------------------------------
# MiniMax API
# ---------------------------------------------------------------------------

def generate_with_minimax(prompt: str, api_key: str) -> str:
    url = "https://api.minimax.chat/v1/text/chatcompletion_pro"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "abab6.5s-chat",
        "stream": True,
        "messages": [
            {
                "sender_type": "USER",
                "sender_name": "User",
                "text": prompt,
            }
        ],
        "bot_setting": [
            {
                "bot_name": "MM_Assist",
                "content": (
                    "You are a coffee reviewer. You write direct, opinionated, specific "
                    "reviews for a niche affiliate site. You never hedge, never use filler."
                ),
            }
        ],
        "reply_constraints": {"sender_type": "BOT", "sender_name": "MM_Assist"},
        "tokens_to_generate": 2048,
        "temperature": 0.7,
    }

    print("Generating with MiniMax...\n", file=sys.stderr)
    full_response = []

    try:
        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                line_str = line_str[6:]
            if line_str == "[DONE]":
                break
            try:
                chunk = json.loads(line_str)
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        print(text, end="", flush=True)
                        full_response.append(text)
            except json.JSONDecodeError:
                continue

    except requests.RequestException as e:
        print(f"\nMiniMax API error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n", file=sys.stderr)
    return "".join(full_response)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a coffee review draft")
    parser.add_argument("product_id", help="Product ID from products.json")
    parser.add_argument(
        "--api",
        choices=["claude", "minimax", "auto"],
        default="auto",
        help="Which LLM API to use (default: auto-detect from available keys)",
    )
    args = parser.parse_args()

    load_env(ENV_FILE)

    claude_key = os.environ.get("CLAUDE_API_KEY", "")
    minimax_key = os.environ.get("MINIMAX_API_KEY", "")

    # Resolve API selection
    api = args.api
    if api == "auto":
        if claude_key:
            api = "claude"
        elif minimax_key:
            api = "minimax"
        else:
            print("Error: no API keys found. Set CLAUDE_API_KEY or MINIMAX_API_KEY in /opt/.env", file=sys.stderr)
            sys.exit(1)

    if api == "claude" and not claude_key:
        print("Error: CLAUDE_API_KEY not set in /opt/.env", file=sys.stderr)
        sys.exit(1)
    if api == "minimax" and not minimax_key:
        print("Error: MINIMAX_API_KEY not set in /opt/.env", file=sys.stderr)
        sys.exit(1)

    product = load_product(args.product_id)
    price_rows = load_price_history(args.product_id)
    price_summary = summarise_price_history(price_rows)
    style_guide = load_style_guide()

    prompt = build_prompt(product, price_summary, style_guide)

    if api == "claude":
        draft = generate_with_claude(prompt, claude_key)
    else:
        draft = generate_with_minimax(prompt, minimax_key)

    # Save draft
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    draft_file = DRAFTS_DIR / f"{args.product_id}-{date_str}.md"
    draft_file.write_text(draft)
    print(f"\nDraft saved to {draft_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
