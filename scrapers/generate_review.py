# scrapers/generate_review.py
"""
AI review draft generator for Coffee Beans site.
Loads product data + price history, builds a prompt, and sends to Claude or MiniMax API.
Saves the draft to /opt/drafts/[product-id]-[date].md and prints to stdout.

Usage:
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --api minimax
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --api claude
  python scrapers/generate_review.py lavazza-super-crema --api claude-code
  /opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema --personal

  --api claude-code: LOCAL ONLY. Shells out to the locally authenticated Claude Code
                     CLI (Pro subscription tokens) instead of the pay-per-token
                     Anthropic API. Must be passed explicitly — never auto-detected.
                     Refuses to run on the VPS (/opt) cron path.

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
from pathlib import Path as _Path
from reference_db import get_conn, get_specs, find_coffee
import score_ledger


def reference_block(product: dict) -> str:
    """Return a verified-specs context block for the review prompt, or '' if unavailable."""
    db = "data/coffee_reference.db"
    if not _Path(db).exists():
        return ""
    try:
        conn = get_conn(db)
        slug = product.get("reference_slug")
        if not slug:
            hits = find_coffee(conn, product.get("name", ""), product.get("roaster"))
            slug = hits[0][1] if hits and hits[0][0] > 0.6 else None
        specs = get_specs(conn, slug) if slug else None
        conn.close()
        if not specs:
            return ""
        return (
            "VERIFIED SPECS (populate spec table from these; do not invent):\n"
            f"  Roast: {specs['roast_level'].title() if specs['roast_level'] else 'unknown'}\n"
            f"  Origin: {', '.join(s.title() for s in specs['origins']) or 'unknown'}\n"
            f"  Process: {', '.join(s.title() for s in specs['processing']) or 'unknown'}\n"
            f"  Varietals: {', '.join(s.title() for s in specs['varietals']) or 'unknown'}\n"
            "  Community flavor notes (candidates only, do not copy verbatim into tasting notes):\n"
            f"    {', '.join(specs['flavor_notes'])}\n"
        )
    except Exception:
        return ""


# Paths prefer the live VPS layout (/opt/...) but fall back to the repo so the
# generator can be run and tested locally (e.g. `python scrapers/generate_review.py
# <id> --mock`). Server behaviour is unchanged: on the VPS the /opt paths exist.
_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


ENV_FILE = _resolve("/opt/.env", _REPO_ROOT / ".env")
DB_PATH = _resolve("/opt/data/prices.db", _REPO_ROOT / "data" / "prices.db")
PRODUCTS_FILE = _resolve("/opt/scrapers/products.json", _SCRAPERS_DIR / "products.json")
STYLE_GUIDE_FILE = _resolve("/opt/scrapers/style_guide.txt", _SCRAPERS_DIR / "style_guide.txt")
DRAFTS_DIR = Path("/opt/drafts") if Path("/opt").exists() else (_REPO_ROOT / "drafts")

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
documented characteristics is legitimate critical judgment. Not a consumption claim.


ANALYTICAL VOICE (default, no --personal flag)
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
- Use the site's standing preferences as the critical lens. They are established voice,
  not personal consumption claims
- Confidence level: absolute. No hedging. No "may", "might", "could", "tends to".

Good analytical voice:
  "The finish is clean. No linger."
  "This roast turns acrid past 205°F."
  "Too aggressive for an early cup. This is an afternoon or post-meal coffee."
  "Pull this short. Long extractions go muddy."
  "The crema holds. Dense, not thin."
  "At this price per oz, there are better options in the same roast profile."
  "This blend was built for milk drinks. Black, it's one-dimensional."
  "The grind clumps at fine settings (worth noting for single-dose grinders)."
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
  "I've pushed this past 205°F. It turns acrid every time."
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
- The rating must be justified in one sentence. No vague praise.
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


def slugify(value: str) -> str:
    """Approximate WordPress sanitize_title() so internal links match the real
    taxonomy term slugs created by create_beans (which uses sanitize_title)."""
    import re
    import unicodedata

    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


# Real taxonomy rewrite slugs (see functions.php cbi_register_taxonomies):
#   origin -> /origin/   roast-level -> /roast/   roaster -> /roaster/
def build_internal_links(product: dict) -> list[dict]:
    """Deterministic internal links to this bean's origin guide, roast-level
    guide, and roaster archive. Built from product data so the model never has
    to invent a slug. Returns an ordered list of {label, url} dicts."""
    links = []
    roast = (product.get("roast_level") or "").strip()
    origin = (product.get("origin") or "").strip()
    brand = (product.get("brand") or "").strip()
    if roast:
        links.append({"label": f"{roast} roast guide", "url": f"/roast/{slugify(roast)}/"})
    if origin:
        links.append({"label": f"{origin} origin guide", "url": f"/origin/{slugify(origin)}/"})
    if brand:
        links.append({"label": f"more from {brand}", "url": f"/roaster/{slugify(brand)}/"})
    return links


def internal_links_section(product: dict) -> str:
    """Markdown '### Explore further' block with ≥1 link each to origin, roast,
    and roaster archives. push_drafts.php converts these into the post body."""
    links = build_internal_links(product)
    if not links:
        return ""
    phrases = [f"[{l['label']}]({l['url']})" for l in links]
    if len(phrases) > 1:
        joined = ", ".join(phrases[:-1]) + ", and " + phrases[-1]
    else:
        joined = phrases[0]
    return f"### Explore further\nKeep pulling the thread: {joined}.\n"


def meta_title(product: dict) -> str:
    """SEO title in the required format: '[Product] Review — [Roaster] | Coffee Bean Index'."""
    brand = (product.get("brand") or "").strip()
    if brand:
        return f"{product['name']} Review — {brand} | Coffee Bean Index"
    return f"{product['name']} Review | Coffee Bean Index"


def meta_description_mock(product: dict) -> str:
    """Deterministic ≤155-char meta description for --mock (the live API writes its own)."""
    roast = (product.get("roast_level") or "").strip().lower()
    brand = (product.get("brand") or "").strip()
    brews = ", ".join(product.get("best_brew_methods", [])[:2]) or "everyday brewing"
    desc = (
        f"{product['name']}: a {roast} roast from {brand} built for {brews}. "
        f"Tasting notes, sensory profile, daily price tracking, and our verdict."
    )
    if len(desc) <= 155:
        return desc
    return desc[:152].rsplit(" ", 1)[0] + "…"


def meta_header(product: dict, description: str) -> str:
    """HTML-comment metadata block parsed by push_drafts.php into RankMath fields.
    Invisible in rendered markdown; sits above the H1."""
    return (
        "<!--META\n"
        f"meta_title: {meta_title(product)}\n"
        f"meta_description: {description}\n"
        "-->\n\n"
    )


# FTC affiliate disclosure — rendered near the top of the draft (the live page
# also shows one via the template; this keeps the draft itself compliant).
DISCLOSURE_TOP = (
    "*This page contains affiliate links. We may earn commissions from "
    "qualifying purchases at no extra cost to you.*"
)


def build_prompt(product: dict, price_summary: str, style_guide: str, personal: bool,
                 scoring_context: str = "") -> str:
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
        f"COMPARISON ANCHORS: use these specific comparisons, not generic alternatives:\n"
        f"{anchors_lines}\n\n"
        f"The review must reference both comparison products at least once, using the specified logic type as the lens."
        if comparison_anchors else ""
    )

    review_framing = product.get("review_framing", "")
    framing_section = (
        f"\n## Review framing\n"
        f"REVIEW FRAMING: {review_framing}\n"
        f"Open the review from this angle. The framing must be evident in the first two sections (not just the intro sentence)."
        if review_framing else ""
    )

    if personal:
        voice_instruction = """VOICE MODE: PERSONAL
You have personally tried this specific coffee. First-person language ("I", "my", "I've")
is available for direct consumption claims about this product. Use it where it adds
specificity. Not for every sentence. The confidence level is absolute either way.
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
the reader in the experience. Confidence level is absolute. Identical to personal voice.
Specificity is the only citation you need. "This roast turns acrid past 205°F" needs
no source. The specificity is the credibility."""

    # Shared safeguard appended to both voice modes — addresses PREPUBLISH_CHECKLIST §A.4.
    voice_instruction += """

HALLUCINATION SAFEGUARD (applies in both voice modes):
- Spec table fields (Roast, Origin, Process, Weight) must exactly match the product data
  provided below. Do not alter, combine, or invent these values.
- Price analysis must reference the actual 30-day figures supplied. Do not invent prices.
- Technical specifics in prose (temperatures, times, ratios) are only acceptable when
  they are industry-standard for the given roast level and brew method combination.
  If the product data does not support a specific number, use directional language:
  "pull short" not "pull to 25 seconds"; "keep water off the boil" not "brew at 94°C".
- Leave any spec table cell blank (write only the label) rather than guessing.

PUNCTUATION RULE: ABSOLUTE: Never use em-dashes (—) or en-dashes (–) anywhere in the output. Use a period, comma, colon, or parentheses instead. This applies to prose, the spec table, tasting notes, and every section. An em-dash in the output is a failure."""

    # Deterministic SEO scaffolding — the model must reproduce these verbatim,
    # not invent slugs or a different title.
    mtitle = meta_title(product)
    links_md = internal_links_section(product)

    # Anchored rubric + comparative calibration. The rubric is always present;
    # the comparative context is empty on a cold-start ledger. This block is what
    # breaks the 6-7 clustering: explicit bands, an anti-default rule, the decimal
    # mandate, and real prior beans to score against.
    scoring_block = (
        "## Scoring\n"
        f"{score_ledger.RATING_RUBRIC}\n"
        f"{scoring_context}"
    )

    return f"""You are writing a coffee bean product review for a niche affiliate website.
The review will be edited by a human before publication.

## Style guide
{style_guide}

## Voice instruction for this review
{voice_instruction}

## Content diversity requirements
CONTENT DIVERSITY RULES: HARD REQUIREMENTS
Every review must include all three of the following:

1. CONSENSUS claim: One observation that is broadly agreed upon across sources. The baseline expectation for this product. State it plainly without hedging.

2. VARIANCE claim: One observation that is contested, context-dependent, or represents a minority but valid signal. This must reflect a genuine edge case or conflicting data point (not just a caveat). Do not soften it.

3. INFERRED claim: One conclusion that is not explicitly stated in the source data but is logically derivable from the specs, price history, or known roast/origin behaviour. Label nothing. Weave all three in naturally. The reader should not be able to tell which is which.
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

{scoring_block}
## Required output format

Write the review exactly in this structure. No preamble. No additional sections.
Reproduce the META block, the disclosure line, and the "Explore further" block
EXACTLY as given. Do not change the title, the URLs, or the link text. Replace
only the bracketed placeholders (including the meta_description) with your copy.

<!--META
meta_title: {mtitle}
meta_description: [One sentence, 120-155 characters. Plain, specific, no hedging. Describe what this coffee is and who it's for. No quotation marks.]
-->

## {product['name']} Review

{DISCLOSURE_TOP}

**One-line verdict**: [One declarative sentence. No hedge words. States exactly what this coffee is.]

| Spec | Detail |
|---|---|
| Roast | {product.get('roast_level', '')} |
| Origin | {product.get('origin', '')} |
| Process | {product.get('process_method', '')} |
| Best for | {best_brew} |
| Price/oz | $X.XX |

### Tasting notes
- [Specific, declarative. What the coffee does. Not what someone experienced.]
- [3-5 bullets. No vague descriptors without context. No "hints of" or "notes of" without specificity.]

### Who it's for
[1-2 sentences. Name the specific drinker and use case. Not "coffee lovers".]

### Who should skip it
[1-2 sentences. Honest. Use the site's standing preferences where relevant.]

### Price analysis
[Is it good value right now? Reference the actual 30-day data. State a clear buy/wait judgment.]

{score_ledger.rating_section_instruction()}

{links_md}
---
*[Affiliate disclosure: links in this review are affiliate links. Prices accurate at time of writing.]*

{score_ledger.SCORE_TRAILER_INSTRUCTION}
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


def stream_claude_code(prompt: str) -> str:
    """Generate a review by shelling out to the locally authenticated Claude Code
    CLI (`claude -p`). Uses Pro subscription tokens instead of pay-per-token API
    credits. LOCAL ONLY — the caller must keep this off the VPS cron path."""
    import os
    import shutil
    import subprocess

    exe = shutil.which("claude")
    if exe is None:
        print(
            "ERROR: claude CLI not found. Install Claude Code and sign in, "
            "or use --api claude or --api minimax instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Prompt via stdin (no arg-length limit); route Windows .cmd launchers through
    # cmd.exe so CreateProcess can execute them.
    args = ["cmd", "/c", exe, "-p"] if os.name == "nt" else [exe, "-p"]
    result = subprocess.run(
        args,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    draft = result.stdout

    if result.returncode != 0 or not draft.strip():
        print(
            "ERROR: claude CLI returned no output "
            f"(exit code {result.returncode}).",
            file=sys.stderr,
        )
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)

    print(draft)
    return draft


def generate_mock(product: dict, price_summary: str, personal: bool) -> str:
    """Generate a mock review draft without an API call — for local testing."""
    mode = "PERSONAL" if personal else "ANALYTICAL"
    best_brew = ", ".join(product.get("best_brew_methods", []))
    flavor_notes = ", ".join(product.get("flavor_notes", []))

    if personal:
        verdict = f"The real deal. {product['name']} does exactly what it promises and I keep coming back to it."
        tasting = (
            f"- {flavor_notes.split(',')[0].strip().capitalize()} up front, clean through the finish.\n"
            f"- I've pushed this past ideal temp. It turns harsh. Stay in range.\n"
            f"- Works best on {best_brew.split(',')[0].strip()}. That's where it lands right."
        )
        skip = "Skip it if you want something adventurous. This is a workhorse, not a showpiece. I reach for it when I want consistency, not complexity."
    else:
        verdict = f"{product['name']} is a straightforward {product.get('roast_level', '').lower()} roast that delivers on its profile without complications."
        tasting = (
            f"- {flavor_notes.split(',')[0].strip().capitalize()} dominates. Clean, not muddled.\n"
            f"- This roast has a ceiling on extraction temp. Push past it and the profile collapses.\n"
            f"- Built for {best_brew.split(',')[0].strip()}. Other methods get less out of it."
        )
        skip = "Skip it if the profile sounds one-dimensional. It is. That's not a flaw, it's the design."

    meta_desc = meta_description_mock(product)
    links_md = internal_links_section(product)

    # Deterministic decimal mock score so --mock exercises the parse/ledger path
    # offline. Varies a little by sensory profile; clamped to the rubric range.
    body = product.get("body") or 3
    bitterness = product.get("bitterness") or 3
    sweetness = product.get("sweetness") or 3
    mock_score = max(1.0, min(10.0, round(5.0 + 0.4 * (body - bitterness) + 0.2 * (sweetness - 3), 1)))

    return f"""{meta_header(product, meta_desc)}## {product['name']} Review

{DISCLOSURE_TOP}

**One-line verdict**: {verdict}

| Spec | Detail |
|---|---|
| Roast | {product.get('roast_level', 'N/A')} |
| Origin | {product.get('origin', 'N/A')} |
| Process | {product.get('process_method', 'N/A')} |
| Best for | {best_brew} |
| Price/oz | $X.XX (mock, run scraper for real data) |

### Tasting notes
{tasting}

### Who it's for
Drip and french press drinkers who want a reliable daily driver. Not a special occasion coffee.

### Who should skip it
{skip}

### Price analysis
{price_summary}

### Rating: {mock_score}/10
[Mock draft. Edit rating and justification before publishing.]

{links_md}
---
*[Affiliate disclosure: links in this review are affiliate links. Prices accurate at time of writing.]*

<!--SCORE
score: {mock_score}
rationale: Mock draft, deterministic placeholder score derived from sensory profile. Replace with real model output before publishing.
-->

---
[MOCK DRAFT, voice mode: {mode}. Replace with real API output before publishing.]
"""


def strip_dashes(text: str) -> str:
    return (
        text
        .replace(" — ", ". ")
        .replace(" – ", ", ")
        .replace("—", ", ")
        .replace("–", "-")
    )


def save_draft(product_id: str, content: str) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = DRAFTS_DIR / f"{product_id}-{date_str}.md"
    path.write_text(content, encoding="utf-8")
    return path


def record_score(product: dict, draft_text: str, config: dict, ledger: dict,
                 web_calibrate: bool, env: dict) -> None:
    """Parse the score the model just wrote, run the external-critic divergence
    check (sanity check only — never changes our score), and write the ledger
    entry. Wrapped so a ledger failure can never break review generation."""
    try:
        score, rationale = score_ledger.parse_score_from_text(draft_text)
        if score is None:
            print("Ledger: no parseable score in draft — not recorded.", file=sys.stderr)
            return
        external, divergence = score_ledger.divergence_check(
            score, product, config, web_calibrate=web_calibrate, env=env
        )
        entry = score_ledger.make_entry(
            product, score, rationale or "", "generate",
            external=external, divergence=divergence,
        )
        score_ledger.upsert_entry(ledger, entry)
        score_ledger.save_ledger(ledger)

        msg = f"Ledger: {product['id']} scored {score}"
        if external:
            msg += (f" | critic {external['raw']}->{external['normalized']} "
                    f"({external['status']})")
        print(msg, file=sys.stderr)
        if divergence:
            print(f"  ** SCORE DIVERGENCE flagged for your review: {divergence}",
                  file=sys.stderr)
    except Exception as e:
        print(f"Ledger: write skipped ({e}).", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AI coffee bean review draft")
    parser.add_argument("product_id", help="Product ID from products.json")
    parser.add_argument(
        "--api",
        choices=["claude", "minimax", "claude-code"],
        default=None,
        help=(
            "Which backend to use (default: use whichever API key is available). "
            "'claude-code' shells out to the local Claude Code CLI (Pro tokens); "
            "it must be passed explicitly, is never auto-detected, and is local-only."
        ),
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
    parser.add_argument(
        "--web-calibrate",
        action="store_true",
        default=False,
        help=(
            "Optional: when the bean is not in the local CoffeeReview corpus, do a "
            "best-effort web lookup of an external critic score for the divergence "
            "check only. Advisory; degrades to nothing offline; never blocks or "
            "changes our score."
        ),
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        default=False,
        help="Skip writing this bean's score to the comparative rationale ledger.",
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

    ref_context = reference_block(product)

    # Comparative scoring calibration: the anchored rubric is always injected; the
    # comparable-bean context is built from the ledger (empty on a cold start).
    config = score_ledger.load_config()
    ledger = score_ledger.load_ledger()
    scoring_context = score_ledger.format_scoring_context(product, ledger, products, config)
    if scoring_context:
        print(f"Scoring: anchoring against {score_ledger.distribution_stats(ledger)['n']} "
              f"prior beans in the ledger.", file=sys.stderr)
    else:
        print("Scoring: cold-start ledger — rubric only, no comparables yet.", file=sys.stderr)

    if args.mock:
        print("Mode: MOCK (no API call)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        prompt = ref_context + build_prompt(product, price_summary, style_guide,
                                            args.personal, scoring_context)
        print("\n=== CONSTRUCTED PROMPT ===", file=sys.stderr)
        print(prompt, file=sys.stderr)
        print("=== END PROMPT ===\n", file=sys.stderr)
        draft = strip_dashes(generate_mock(product, price_summary, args.personal))
        print(draft)
        path = save_draft(args.product_id, draft)
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"Mock draft saved to: {path}", file=sys.stderr)
        print("Ledger: not written in mock mode (mock score is a placeholder).",
              file=sys.stderr)
        return

    prompt = ref_context + build_prompt(product, price_summary, style_guide,
                                        args.personal, scoring_context)

    api = args.api
    if api is None:
        # Auto-detection: CLAUDE_API_KEY first, then MINIMAX_API_KEY.
        # claude-code is intentionally never auto-detected — it must be passed explicitly.
        if env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY"):
            api = "claude"
        elif env.get("MINIMAX_API_KEY"):
            api = "minimax"
        else:
            print("ERROR: No API key found. Set CLAUDE_API_KEY or MINIMAX_API_KEY in /opt/.env", file=sys.stderr)
            sys.exit(1)

    # claude-code is local-only. Refuse to run it on the VPS (/opt) cron path.
    if api == "claude-code" and Path("/opt").exists():
        print(
            "ERROR: --api claude-code is local-only and cannot run on the VPS. "
            "Use --api claude or --api minimax on the server.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"API: {api}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    if api == "claude":
        draft = stream_claude(prompt, env)
    elif api == "claude-code":
        draft = stream_claude_code(prompt)
    else:
        draft = stream_minimax(prompt, env)

    draft = strip_dashes(draft)
    path = save_draft(args.product_id, draft)
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"Draft saved to: {path}", file=sys.stderr)

    if not args.no_ledger:
        record_score(product, draft, config, ledger, args.web_calibrate, env)


if __name__ == "__main__":
    main()
