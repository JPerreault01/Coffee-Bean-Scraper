# scrapers/generate_review.py
"""
AI review draft generator for Coffee Beans site.
Loads product data + price history, builds a prompt, and sends to Claude or MiniMax API.
Saves the draft to /opt/drafts/[product-id]-[date].md and prints to stdout.

Usage:
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --api minimax
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --api claude
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --personal

  --personal flag: unlocks first-person "I" language for products you have personally tried.
                   Default (no flag): analytical voice — same confidence, no personal
                   consumption claims for the specific product.

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

# ---------------------------------------------------------------------------
# Fallback style guide — used if style_guide.txt does not exist on disk.
# Keep in sync with scrapers/style_guide.txt.
# ---------------------------------------------------------------------------

FALLBACK_STYLE_GUIDE = """
SITE VOICE & ESTABLISHED PREFERENCES
======================================

This site has a palate and a point of view. Every review reflects it. The voice is
direct, confident, and specific. It does not hedge. It does not flatter. It calls a
mediocre coffee mediocre and an overpriced one overpriced.

Standing preferences (apply to all reviews regardless of personal flag):
- Clean finishes over lingering bitterness
- Forgiving brew profiles over finicky ones
- Value-driven pricing over brand premiums
- Bright, defined flavors over muddy complexity
- Not a fan of aggressive, high-intensity roasts as early morning coffees
- Espresso that works without a $2,000 machine is worth more than espresso that doesn't

These preferences are the reviewer's known voice. Applying them to a product's
documented characteristics is legitimate critical judgment — not a consumption claim.


ANALYTICAL VOICE (default — no --personal flag)
================================================

The coffee is the grammatical subject. State product truth declaratively.
Specificity is the only citation needed.

Rules:
- Never write "I tried", "I brewed", "I tasted", or any first-person consumption
  claim for this specific product
- Never write "buyers say", "reviewers report", "customers note" or any crowd-sourcing
  attribution
- State what the coffee IS and DOES, not what someone experienced
- Use second person ("you get", "you'll find") to put the reader in the cup without
  claiming the writer was there
- Use the site's standing preferences as the critical lens — they are established voice,
  not personal consumption claims
- Confidence level: absolute. No hedging. No "may", "might", "could", "tends to".

Good analytical voice:
  "The finish is clean. No linger."
  "This roast turns acrid past 205°F."
  "Too aggressive for an early cup — this is an afternoon or post-meal coffee."
  "Pull this short. Long extractions go muddy."
  "The crema holds. Dense, not thin."
  "At this price per oz, there are better options in the same roast profile."
  "This blend was built for milk drinks. Black, it's one-dimensional."
  "The grind clumps at fine settings — worth noting for single-dose grinders."
  "You get dark chocolate up front, then a clean caramel fade."
  "Brew it long and it gets muddy. Keep it short."

Bad (hedging, fake humility, vague):
  "Some may find this too intense."
  "It could potentially work well for espresso."
  "Many coffee drinkers enjoy this roast."
  "It's worth noting that the finish is relatively clean."


PERSONAL VOICE (--personal flag only)
======================================

Identical confidence level to analytical. The only difference: first-person language
is available for specific consumption claims about THIS product.

What the personal flag unlocks:
  "I've pushed this past 205°F — it turns acrid every time."
  "Too aggressive for my first cup."
  "I've pulled this short and long. Short wins."
  "My go-to for moka pot mornings."

What it does NOT change:
  - Confidence level (still absolute)
  - Sentence structure (still short, declarative)
  - The site's standing preferences
  - The analytical framing of price, value, and specs

The reader should not be able to tell which mode they're reading based on confidence.
Only the presence or absence of "I" language should differ.


UNIVERSAL RULES (both voices)
==============================

- Short sentences. One idea per sentence.
- No filler: "in conclusion", "it's worth noting", "at the end of the day", "overall"
- No fake hedging: "some may find", "could potentially", "tends to"
- Specific over vague: "turns acrid past 205°F" beats "can be harsh if over-extracted"
- No producer puffery: never repeat marketing language uncritically
- Price analysis must be specific: reference the actual 30-day data
- The rating must be justified in one sentence — no vague praise
- British or American spelling, consistent within a piece
"""


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
    return FALLBACK_STYLE_GUIDE.strip()


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


def build_prompt(product: dict, price_summary: str, style_guide: str, personal: bool) -> str:
    best_brew = ", ".join(product.get("best_brew_methods", []))
    flavor_notes = ", ".join(product.get("flavor_notes", []))
    affiliate_tag = product.get("affiliate_tag", "")
    asin = product.get("amazon_asin", "")
    affiliate_url = (
        f"https://www.amazon.com/dp/{asin}?tag={affiliate_tag}"
        if asin and affiliate_tag
        else product.get("roaster_url", "")
    )

    comparison_anchors = product.get("comparison_anchors", [])
    anchors_lines = "\n".join(
        f"- {a['product']} (logic: {a['logic']})" for a in comparison_anchors
    )
    comparison_section = (
        f"\n## Comparison anchors\n"
        f"COMPARISON ANCHORS — use these specific comparisons, not generic alternatives:\n"
        f"{anchors_lines}\n\n"
        f"The review must reference both comparison products at least once, using the specified logic type as the lens."
        if comparison_anchors else ""
    )

    review_framing = product.get("review_framing", "")
    framing_section = (
        f"\n## Review framing\n"
        f"REVIEW FRAMING: {review_framing}\n"
        f"Open the review from this angle. The framing must be evident in the first two sections — not just the intro sentence."
        if review_framing else ""
    )

    if personal:
        voice_instruction = """VOICE MODE: PERSONAL
You have personally tried this specific coffee. First-person language ("I", "my", "I've")
is available for direct consumption claims about this product. Use it where it adds
specificity — not for every sentence. The confidence level is absolute either way.
Do not claim to have tried it more than the content warrants. Short, declarative sentences.
No hedging. No filler."""
    else:
        voice_instruction = """VOICE MODE: ANALYTICAL
You have not personally tried this specific coffee. Do not claim to have done so.
Do not write "I tried", "I brewed", "I tasted", or any first-person consumption claim
for this product. Do not write "buyers say", "reviewers report", or attribute claims
to any group.

State product truth declaratively. The coffee is the subject. Use the site's established
preferences as the critical lens. Use second person ("you get", "you'll find") to put
the reader in the experience. Confidence level is absolute — identical to personal voice.
Specificity is the only citation you need. "This roast turns acrid past 205°F" needs
no source — the specificity is the credibility."""

    return f"""You are writing a coffee bean product review for a niche affiliate website.
The review will be edited by a human before publication.

## Style guide
{style_guide}

## Voice instruction for this review
{voice_instruction}

## Content diversity requirements
CONTENT DIVERSITY RULES — HARD REQUIREMENTS
Every review must include all three of the following:

1. CONSENSUS claim: One observation that is broadly agreed upon across sources — the baseline expectation for this product. State it plainly without hedging.

2. VARIANCE claim: One observation that is contested, context-dependent, or represents a minority but valid signal. This must reflect a genuine edge case or conflicting data point — not just a caveat. Do not soften it.

3. INFERRED claim: One conclusion that is not explicitly stated in the source data but is logically derivable from the specs, price history, or known roast/origin behaviour. Label nothing — weave all three in naturally. The reader should not be able to tell which is which.
{comparison_section}
{framing_section}

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

Write the review exactly in this structure. No preamble. No additional sections.

## {product['name']} Review

**One-line verdict**: [One declarative sentence. No hedge words. States exactly what this coffee is.]

| Spec | Detail |
|---|---|
| Roast | {product.get('roast_level', '')} |
| Origin | {product.get('origin', '')} |
| Process | {product.get('process_method', '')} |
| Best for | {best_brew} |
| Price/oz | $X.XX |

### Tasting notes
- [Specific, declarative. What the coffee does — not what someone experienced.]
- [3–5 bullets. No vague descriptors without context. No "hints of" or "notes of" without specificity.]

### Who it's for
[1–2 sentences. Name the specific drinker and use case — not "coffee lovers".]

### Who should skip it
[1–2 sentences. Honest. Use the site's standing preferences where relevant.]

### Price analysis
[Is it good value right now? Reference the actual 30-day data. State a clear buy/wait judgment.]

### Rating: X/10
[One sentence. Justify the number specifically.]

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
        model="claude-sonnet-4-20250514",
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


def generate_mock(product: dict, price_summary: str, personal: bool) -> str:
    """Generate a mock review draft without an API call — for local testing."""
    mode = "PERSONAL" if personal else "ANALYTICAL"
    best_brew = ", ".join(product.get("best_brew_methods", []))
    flavor_notes = ", ".join(product.get("flavor_notes", []))

    if personal:
        verdict = f"The real deal — {product['name']} does exactly what it promises and I keep coming back to it."
        tasting = (
            f"- {flavor_notes.split(',')[0].strip().capitalize()} up front, clean through the finish.\n"
            f"- I've pushed this past ideal temp — it turns harsh. Stay in range.\n"
            f"- Works best on {best_brew.split(',')[0].strip()} — that's where it lands right."
        )
        skip = "Skip it if you want something adventurous. This is a workhorse, not a showpiece. I reach for it when I want consistency, not complexity."
    else:
        verdict = f"{product['name']} is a straightforward {product.get('roast_level', '').lower()} roast that delivers on its profile without complications."
        tasting = (
            f"- {flavor_notes.split(',')[0].strip().capitalize()} dominates — clean, not muddled.\n"
            f"- This roast has a ceiling on extraction temp. Push past it and the profile collapses.\n"
            f"- Built for {best_brew.split(',')[0].strip()}. Other methods get less out of it."
        )
        skip = "Skip it if the profile sounds one-dimensional — it is. That's not a flaw, it's the design."

    return f"""## {product['name']} Review

**One-line verdict**: {verdict}

| Spec | Detail |
|---|---|
| Roast | {product.get('roast_level', 'N/A')} |
| Origin | {product.get('origin', 'N/A')} |
| Process | {product.get('process_method', 'N/A')} |
| Best for | {best_brew} |
| Price/oz | $X.XX (mock — run scraper for real data) |

### Tasting notes
{tasting}

### Who it's for
Drip and french press drinkers who want a reliable daily driver. Not a special occasion coffee.

### Who should skip it
{skip}

### Price analysis
{price_summary}

### Rating: X/10
[Mock draft — edit rating and justification before publishing.]

---
*[Affiliate disclosure: links in this review are affiliate links. Prices accurate at time of writing.]*

---
[MOCK DRAFT — voice mode: {mode} — replace with real API output before publishing]
"""


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
    parser.add_argument(
        "--personal",
        action="store_true",
        default=False,
        help=(
            "Use personal voice — unlocks first-person 'I' language. "
            "Only use for products you have personally tried."
        ),
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Generate a mock draft locally without an API call (for testing)",
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

    voice_label = "PERSONAL" if args.personal else "ANALYTICAL"
    print(f"Generating review for: {product['name']}", file=sys.stderr)
    print(f"Voice mode: {voice_label}", file=sys.stderr)

    if args.mock:
        print("Mode: MOCK (no API call)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        prompt = build_prompt(product, price_summary, style_guide, args.personal)
        print("\n=== CONSTRUCTED PROMPT ===", file=sys.stderr)
        print(prompt, file=sys.stderr)
        print("=== END PROMPT ===\n", file=sys.stderr)
        draft = generate_mock(product, price_summary, args.personal)
        print(draft)
        path = save_draft(args.product_id, draft)
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"Mock draft saved to: {path}", file=sys.stderr)
        return

    prompt = build_prompt(product, price_summary, style_guide, args.personal)

    api = args.api
    if api is None:
        if env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY"):
            api = "claude"
        elif env.get("MINIMAX_API_KEY"):
            api = "minimax"
        else:
            print("ERROR: No API key found. Set CLAUDE_API_KEY or MINIMAX_API_KEY in /opt/.env", file=sys.stderr)
            sys.exit(1)

    print(f"API: {api}", file=sys.stderr)
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
