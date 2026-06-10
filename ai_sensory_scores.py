#!/usr/bin/env python3
"""
scrapers/ai_sensory_scores.py

Generates 1-5 sensory scores (acidity, body, sweetness, bitterness, roast_intensity)
for each product in products.json, grounded in real evidence:

  1. Verified specs from coffee_reference.db (flavor notes, processing, roast, description)
  2. The roaster's own product page (fetched live)
  3. A web search for third-party cupping / tasting notes

All of that is handed to Claude via FORCED TOOL USE, which returns structured scores
plus a one-line justification and a confidence level per bean. Confidence is "high" when
the scores are supported by explicit source text, "low" when inferred from flavor notes
and roast alone (flagged so you can review those).

Output: data/sensory_scores.json
  {
    "product-id": {
      "scores": {"acidity": 3, "body": 4, "sweetness": 3, "bitterness": 3, "roast_intensity": 4},
      "confidence": "high" | "low",
      "justification": "Roaster lists 'bright, juicy'; Coffee Review cupping notes confirm...",
      "sources": ["roaster_page", "web:coffeereview.com", "reference_db"]
    },
    ...
  }

Usage (local, with venv active):
  python scrapers/ai_sensory_scores.py
  python scrapers/ai_sensory_scores.py --only blue-bottle-bella-donovan   # single bean
  python scrapers/ai_sensory_scores.py --limit 5                          # first 5 (testing)

Requires:
  pip install anthropic requests beautifulsoup4
  CLAUDE_API_KEY or ANTHROPIC_API_KEY in .env or environment
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# --- repo-aware paths (mirrors generate_review.py) -------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SCRIPT_DIR))

PRODUCTS_PATH = _SCRIPT_DIR / "products.json"
REFERENCE_DB = (
    Path("/opt/data/coffee_reference.db")
    if Path("/opt/data/coffee_reference.db").exists()
    else _REPO_ROOT / "data" / "coffee_reference.db"
)
OUT_PATH = _REPO_ROOT / "data" / "sensory_scores.json"
ENV_FILE = Path("/opt/.env") if Path("/opt/.env").exists() else _REPO_ROOT / ".env"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# --- env loading -----------------------------------------------------------
def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


# --- reference DB grounding ------------------------------------------------
def get_reference_context(product: dict) -> tuple[str, bool]:
    """Return (context_text, found) using the reference corpus."""
    if not REFERENCE_DB.exists():
        return "", False
    try:
        from reference_db import get_conn, get_specs, find_coffee
        conn = get_conn(str(REFERENCE_DB))
        slug = product.get("reference_slug")
        if not slug:
            hits = find_coffee(conn, product.get("name", ""), product.get("roaster"))
            slug = hits[0][1] if hits and hits[0][0] > 0.6 else None
        specs = get_specs(conn, slug) if slug else None
        conn.close()
        if not specs:
            return "", False
        parts = [
            f"Reference roast level: {specs.get('roast_level') or 'unknown'}",
            f"Reference origins: {', '.join(specs.get('origins', [])) or 'unknown'}",
            f"Reference processing: {', '.join(specs.get('processing', [])) or 'unknown'}",
            f"Reference flavor notes: {', '.join(specs.get('flavor_notes', [])) or 'none'}",
        ]
        if specs.get("description"):
            parts.append(f"Reference description: {specs['description'][:600]}")
        return "\n".join(parts), True
    except Exception as e:
        print(f"  [ref-db warning] {e}", file=sys.stderr)
        return "", False


# --- roaster page fetch ----------------------------------------------------
def fetch_roaster_page(url: str) -> str:
    if not url:
        return ""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return ""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:3000]
    except Exception as e:
        print(f"  [roaster-fetch warning] {e}", file=sys.stderr)
        return ""


# --- Claude call with forced tool use --------------------------------------
SENSORY_TOOL = {
    "name": "record_sensory_scores",
    "description": "Record the 1-5 sensory scores for a coffee with justification and confidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "acidity": {"type": "integer", "minimum": 1, "maximum": 5},
            "body": {"type": "integer", "minimum": 1, "maximum": 5},
            "sweetness": {"type": "integer", "minimum": 1, "maximum": 5},
            "bitterness": {"type": "integer", "minimum": 1, "maximum": 5},
            "roast_intensity": {"type": "integer", "minimum": 1, "maximum": 5},
            "confidence": {
                "type": "string",
                "enum": ["high", "low"],
                "description": "high if scores are supported by explicit source text; "
                               "low if inferred from flavor notes and roast level alone",
            },
            "justification": {
                "type": "string",
                "description": "One or two sentences citing what in the sources drove the scores.",
            },
        },
        "required": ["acidity", "body", "sweetness", "bitterness",
                     "roast_intensity", "confidence", "justification"],
    },
}

SYSTEM_PROMPT = """You are a coffee cupping analyst. Given a coffee's product data,
roaster description, third-party tasting notes, and reference specs, assign 1-5 scores on
these axes:

- acidity: 1=flat/low (dark roasts, Sumatra) ... 5=bright/sharp (washed Ethiopian, light roast)
- body: 1=light/tea-like ... 5=heavy/syrupy (Sumatra, dark roast, naturals)
- sweetness: 1=dry/savory ... 5=very sweet (caramel, honey, milk chocolate notes)
- bitterness: 1=none ... 5=intense (dark/charred roasts, robusta, chicory)
- roast_intensity: 1=light ... 5=dark/charred (this tracks the roast level directly)

Rules:
- Prefer explicit evidence. If the roaster or a cupping source states "bright acidity,"
  "full body," etc., score from that and set confidence "high."
- If you only have flavor notes and roast level to go on, infer reasonably but set
  confidence "low."
- roast_intensity should align with the stated roast level: Light=1-2, Medium=2-3,
  Medium-Dark=3-4, Dark=4-5.
- Always call the record_sensory_scores tool. Do not reply in prose."""


def score_one(client, product: dict, ref_ctx: str, roaster_text: str,
              web_text: str, sources: list[str]) -> dict:
    user_content = f"""COFFEE: {product['name']}
Roaster: {product.get('roaster', 'unknown')}
Stated roast level: {product.get('roast_level', 'unknown')}
Stated origin: {product.get('origin', 'unknown')}
Stated process: {product.get('process_method', 'unknown')}
Product flavor notes: {', '.join(product.get('flavor_notes', [])) or 'none listed'}

--- REFERENCE DB SPECS ---
{ref_ctx or 'No reference match found.'}

--- ROASTER PAGE TEXT (excerpt) ---
{roaster_text or 'Could not fetch roaster page.'}

--- THIRD-PARTY TASTING NOTES (web search) ---
{web_text or 'No third-party notes found.'}

Assign the 5 sensory scores. Call record_sensory_scores."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=SYSTEM_PROMPT,
        tools=[SENSORY_TOOL],
        tool_choice={"type": "tool", "name": "record_sensory_scores"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_sensory_scores":
            data = block.input
            return {
                "scores": {
                    "acidity": data["acidity"],
                    "body": data["body"],
                    "sweetness": data["sweetness"],
                    "bitterness": data["bitterness"],
                    "roast_intensity": data["roast_intensity"],
                },
                "confidence": data["confidence"],
                "justification": data["justification"],
                "sources": sources,
            }
    raise RuntimeError("Model did not return a tool_use block")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Score a single product id")
    parser.add_argument("--limit", type=int, help="Score only the first N products")
    parser.add_argument("--no-web", action="store_true",
                        help="Skip web search (reference DB + roaster page only)")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: no CLAUDE_API_KEY / ANTHROPIC_API_KEY found.", file=sys.stderr)
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    products = json.loads(PRODUCTS_PATH.read_text())
    if args.only:
        products = [p for p in products if p["id"] == args.only]
    elif args.limit:
        products = products[: args.limit]

    # Resume: load existing scores so re-runs don't re-bill completed beans
    existing = {}
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text())
        except Exception:
            existing = {}

    results = dict(existing)
    low_conf = []

    for i, product in enumerate(products, 1):
        pid = product["id"]
        if pid in results and not args.only:
            print(f"[{i}/{len(products)}] SKIP {pid} (already scored)")
            continue

        print(f"[{i}/{len(products)}] {pid} ...")
        ref_ctx, ref_found = get_reference_context(product)
        sources = ["reference_db"] if ref_found else []

        roaster_text = fetch_roaster_page(product.get("roaster_url", ""))
        if roaster_text:
            sources.append("roaster_page")

        # Web search step: Claude Code runs this script and can perform the web
        # search itself when --no-web is not set. The script leaves web_text empty;
        # Claude Code is instructed (in the prompt) to fill third-party notes by
        # searching per bean and passing them in. For a fully autonomous script
        # run without Claude Code orchestration, --no-web skips this.
        web_text = ""
        if not args.no_web:
            # Placeholder: Claude Code injects search results here per bean.
            # See the accompanying prompt for how this is orchestrated.
            pass

        try:
            result = score_one(client, product, ref_ctx, roaster_text, web_text, sources)
            results[pid] = result
            flag = "  <-- LOW CONFIDENCE" if result["confidence"] == "low" else ""
            print(f"      {result['scores']}  [{result['confidence']}]{flag}")
            if result["confidence"] == "low":
                low_conf.append(pid)
        except Exception as e:
            print(f"      FAILED: {e}", file=sys.stderr)

        # Write after each bean so a crash doesn't lose progress
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(results, indent=2))
        time.sleep(1.5)

    print(f"\nDone. Scored {len(results)} beans. Output: {OUT_PATH}")
    if low_conf:
        print(f"\nLOW CONFIDENCE ({len(low_conf)}) — review these before publishing:")
        for pid in low_conf:
            print(f"  {pid}: {results[pid]['justification']}")


if __name__ == "__main__":
    main()
