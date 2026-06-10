# scrapers/score_ledger.py
"""
Scoring rubric + comparative rationale ledger for Coffee Bean Index reviews.
=============================================================================
Single source of truth for HOW a bean is scored. Imported by:
  - generate_review.py  (injects the rubric + comparative context into the
                         review prompt; parses + records the score afterward)
  - backfill_scores.py  (re-scores existing drafts through the new system and
                         populates the ledger; prints a before/after histogram)

Why this exists
---------------
AI scores were clustering at 6-7/10 because the prompt said only "Rating: X/10"
with no anchored rubric, so the model regressed to a safe middle. This module
fixes that with four levers:

  (a) An ANCHORED RUBRIC with explicit score bands and an anti-clustering rule.
  (b) Full DECIMAL range (1.0-10.0 in 0.1 steps); the justification must name the
      specific thing that set the exact decimal.
  (c) The score is decided LAST, after the honest "who should skip it" critique
      (enforced in the prompt ordering + a machine-readable SCORE trailer that
      the model must emit at the very end).
  (d) COMPARATIVE ANCHORING: each scored bean's {score, ~15-25 word rationale}
      is stored in a token-light ledger. When scoring a new bean we inject the
      closest comparables (same roast / sensory / price tier) plus a compressed
      view of the whole-catalog distribution, so the model ranks RELATIVE to
      real prior beans, not in a vacuum.

      IMPORTANT: the rubric (a) is the ABSOLUTE authority on the number; the
      comparables are for ORDERING ONLY and must never act as a ceiling. If the
      ledger is bootstrapped from a biased baseline (e.g. the old 6-7 cluster),
      anchoring to its range would reinforce the bias. The injected context
      therefore tells the model to distrust the catalog's current range and take
      the magnitude from the rubric. For the same reason, backfill_scores.py
      re-scores from a COLD ledger by default (it does not seed the old scores
      as anchors).

External critic scores (CoffeeReview etc., scraped into data/coffeereview.db)
are a SANITY CHECK, not an anchor. They never enter the scoring prompt. After
our score exists, a separate lightweight step compares the two and only FLAGS
large divergences for manual review (see divergence_check). Governed by
critic_weight in scoring_config.json (default: advisory-only).

Ledger location
---------------
data/score_rationales.json (or /opt/data on the VPS). This is a DERIVED artifact
and is gitignored (.gitignore: data/*.json), exactly like sensory_scores.json and
coffeereview.json. It is rebuilt from drafts by backfill_scores.py, so it never
needs to be committed. Our score and any external score are kept as SEPARATE
fields; the external number never overwrites ours.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- repo-aware paths (mirror generate_review.py) --------------------------
_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


DATA_DIR = Path("/opt/data") if Path("/opt/data").exists() else (_REPO_ROOT / "data")
LEDGER_PATH = DATA_DIR / "score_rationales.json"
PRICES_DB = _resolve("/opt/data/prices.db", _REPO_ROOT / "data" / "prices.db")
COFFEEREVIEW_DB = _resolve("/opt/data/coffeereview.db", _REPO_ROOT / "data" / "coffeereview.db")
CONFIG_PATH = _SCRAPERS_DIR / "scoring_config.json"

SENSORY_AXES = ["acidity", "body", "sweetness", "bitterness", "roast_intensity"]

DEFAULT_CONFIG = {
    "critic_weight": "advisory",
    "agreement_threshold": 1.0,
    "divergence_threshold": 1.5,
    "max_nudge": 0.3,
    "comparable_k": 18,
    "critic_scale": {"offset": 50.0, "divisor": 5.0, "min": 1.0, "max": 10.0},
    "web_calibrate": {"model": "claude-sonnet-4-6", "max_searches": 3, "timeout_seconds": 40},
}


def load_config() -> dict:
    """Load scoring_config.json, falling back to DEFAULT_CONFIG for any missing key."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k, v in user.items():
                if k.startswith("_"):
                    continue
                cfg[k] = v
    except Exception as e:  # never let bad config break scoring
        print(f"[score_ledger] config warning: {e}", file=sys.stderr)
    return cfg


# ---------------------------------------------------------------------------
# THE ANCHORED RUBRIC - the single source of truth, injected into every
# scoring prompt. Keep in sync with CLAUDE_content_standards_section.md.
# ---------------------------------------------------------------------------

RATING_RUBRIC = """SCORING RUBRIC (anchored - use the full 1.0-10.0 range in 0.1 steps):

  9.0-10.0  EXCEPTIONAL. Rare. A bench-defining coffee with no real fault. Reserve
            this. Most catalogs have a tiny handful. Do not hand it out.
  8.0-8.9   EXCELLENT. A standout in its category. Clearly better than the field.
  7.0-7.9   GOOD, AND IT MUST BE EARNED. A 7 is not the default. Name the specific
            thing that lifts it above average, or it is not a 7.
  5.0-6.9   AVERAGE. This is where MOST beans land. Competent, does its job, nothing
            that distinguishes it. The honest middle for a solid-but-ordinary coffee.
  3.0-4.9   A NAMABLE FLAW. Something concrete drags it down: muddy finish, brand
            premium, one-dimensional, finicky, over-roasted, poor value.
  1.0-2.9   AVOID. Actively bad or a clear rip-off.

HARD ANTI-CLUSTERING RULES:
  - DO NOT default to 6-7. That cluster is the exact bias we are correcting.
  - Most beans are AVERAGE: score them 5.0-6.9, not 7.
  - A 7.0+ requires a specific, stated reason it beats the field. No reason -> below 7.
  - Use decimals to place the bean PRECISELY. 7.3 not 7.0; 5.8 not 6.0. The
    justification must name the exact thing that set that decimal (e.g. why 7.3 and
    not 7.0: "the clean, fast finish edges it above the 7.0 tier, but a generic
    blend origin keeps it short of 7.5").
  - Decide the number AFTER you have written the honest "who should skip it"
    critique. Let the criticism pull the score down. Do not let the positive
    tasting notes inflate it.
"""

# Machine-readable trailer the model must emit at the very end of a review (or as
# the sole output when scoring standalone). Invisible in rendered markdown (HTML
# comment) and ignored by push_drafts.php, which parses only <!--META and the
# section headings. This is the robust parse target for the ledger.
SCORE_TRAILER_TEMPLATE = """<!--SCORE
score: {score}
rationale: {rationale}
-->"""

SCORE_TRAILER_INSTRUCTION = """At the VERY END of your output, after everything else,
emit this machine-readable block EXACTLY in this shape (it is an HTML comment and stays
invisible on the page). The score here MUST equal the "### Rating" number above, to one
decimal. The rationale is 15-25 words naming the specific thing that set that exact
decimal, written in our voice:

<!--SCORE
score: 7.3
rationale: Clean, fast chocolate finish lifts it past 7.0, but a generic blend origin and brand-premium price keep it short of 7.5.
-->"""


def rating_section_instruction() -> str:
    """The '### Rating' block instructions for the review output format - replaces the
    bare 'Rating: X/10. [justify]'. Decimal-aware and rubric-aware."""
    return (
        "### Rating: [X.X]/10\n"
        "[One sentence. Use a DECIMAL (e.g. 7.3, 5.8) chosen with the rubric above. "
        "Name the specific thing that set that exact decimal. No vague praise. The "
        "number must reflect the honest critique you just wrote, not the tasting notes.]"
    )


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

def load_ledger() -> dict:
    """Return the ledger as {product_id: entry}. Empty dict if none yet."""
    if not LEDGER_PATH.exists():
        return {}
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as e:
        print(f"[score_ledger] ledger unreadable, starting fresh: {e}", file=sys.stderr)
    return {}


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def make_entry(
    product: dict,
    score: float,
    rationale: str,
    method: str,
    external: dict | None = None,
    divergence: str | None = None,
) -> dict:
    """Build a token-light ledger entry. Our score and any external score are
    kept in SEPARATE fields; the external number never overwrites ours."""
    entry = {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "roast_level": product.get("roast_level"),
        "score": round(float(score), 1),
        "rationale": (rationale or "").strip(),
        "method": method,
        "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if external:
        entry["external"] = external
    if divergence:
        entry["score_divergence"] = divergence
    return entry


def upsert_entry(ledger: dict, entry: dict) -> dict:
    ledger[entry["product_id"]] = entry
    return ledger


# ---------------------------------------------------------------------------
# Score parsing - read the score + rationale back out of model output
# ---------------------------------------------------------------------------

_TRAILER_RE = re.compile(r"<!--SCORE\s*(.*?)-->", re.S | re.I)
_HEADING_RE = re.compile(r"###\s*Rating:\s*([\d.]+)\s*/\s*10", re.I)


def _clamp_score(val: float) -> float | None:
    try:
        f = round(float(val), 1)
    except (TypeError, ValueError):
        return None
    if 1.0 <= f <= 10.0:
        return f
    return None


def parse_score_from_text(text: str) -> tuple[float | None, str | None]:
    """Extract (score, rationale) from model output. Prefers the machine-readable
    <!--SCORE--> trailer; falls back to the '### Rating: X.X/10' heading (rationale
    then taken from the sentence beneath the heading)."""
    if not text:
        return None, None

    m = _TRAILER_RE.search(text)
    if m:
        block = m.group(1)
        sc = re.search(r"score:\s*([\d.]+)", block, re.I)
        ra = re.search(r"rationale:\s*(.+)", block, re.I | re.S)
        score = _clamp_score(sc.group(1)) if sc else None
        rationale = ra.group(1).strip() if ra else None
        if rationale:
            rationale = re.sub(r"\s+", " ", rationale).strip()
        if score is not None:
            return score, rationale

    m = _HEADING_RE.search(text)
    if m:
        score = _clamp_score(m.group(1))
        rationale = None
        tail = text[m.end():].lstrip("\n")
        first = tail.split("\n", 1)[0].strip()
        if first and not first.startswith("#"):
            rationale = re.sub(r"\s+", " ", first).strip()
        return score, rationale

    return None, None


# ---------------------------------------------------------------------------
# Comparative anchoring - select the closest prior beans + catalog distribution
# ---------------------------------------------------------------------------

_ROAST_ORDINAL = {
    "light": 1, "blonde": 1, "light-medium": 2, "medium-light": 2,
    "medium": 3, "medium-dark": 4, "medium dark": 4,
    "dark": 5, "extra dark": 5, "french": 5, "italian": 5,
}


def _roast_ordinal(roast: str | None) -> int:
    if not roast:
        return 3
    key = roast.strip().lower()
    if key in _ROAST_ORDINAL:
        return _ROAST_ORDINAL[key]
    for token, val in _ROAST_ORDINAL.items():
        if token in key:
            return val
    return 3


def _sensory_vec(product: dict) -> list[float | None]:
    out = []
    for axis in SENSORY_AXES:
        v = product.get(axis)
        out.append(float(v) if isinstance(v, (int, float)) else None)
    return out


def _sensory_distance(a: list[float | None], b: list[float | None]) -> float:
    """Euclidean distance over the axes both beans define; scaled so missing data
    neither helps nor unfairly penalizes."""
    sq = 0.0
    n = 0
    for x, y in zip(a, b):
        if x is None or y is None:
            continue
        sq += (x - y) ** 2
        n += 1
    if n == 0:
        return 3.0  # no sensory overlap -> neutral-ish distance
    return math.sqrt(sq / n) * math.sqrt(len(SENSORY_AXES))


def _price_per_oz(product_id: str) -> float | None:
    """Latest price/oz from prices.db, or None (prices.db holds mostly seed data)."""
    if not PRICES_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(PRICES_DB))
        row = conn.execute(
            "SELECT price_per_oz FROM price_history "
            "WHERE product_id = ? AND price_per_oz IS NOT NULL "
            "ORDER BY checked_at DESC LIMIT 1",
            (product_id,),
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] else None
    except Exception:
        return None


def _price_tier(ppo: float | None) -> int | None:
    if ppo is None:
        return None
    if ppo < 0.55:
        return 0   # budget
    if ppo < 1.10:
        return 1   # mid
    if ppo < 1.75:
        return 2   # premium
    return 3       # ultra-premium


def select_comparables(
    product: dict, ledger: dict, products_by_id: dict, k: int = 18
) -> list[dict]:
    """Return up to k ledger entries closest to `product` by roast level, sensory
    profile, and price tier - the comparative anchors for scoring."""
    self_id = product.get("id")
    pv = _sensory_vec(product)
    pr = _roast_ordinal(product.get("roast_level"))
    pt = _price_tier(_price_per_oz(self_id))

    scored: list[tuple[float, dict]] = []
    for pid, entry in ledger.items():
        if pid == self_id or entry.get("score") is None:
            continue
        op = products_by_id.get(pid, {})
        dist = _sensory_distance(pv, _sensory_vec(op))
        dist += abs(pr - _roast_ordinal(op.get("roast_level") or entry.get("roast_level"))) * 1.2
        ot = _price_tier(_price_per_oz(pid))
        if pt is not None and ot is not None:
            dist += abs(pt - ot) * 0.8
        scored.append((dist, entry))

    scored.sort(key=lambda t: t[0])
    return [e for _, e in scored[:k]]


def distribution_stats(ledger: dict) -> dict:
    """Compressed whole-catalog view for broad calibration."""
    scores = [e["score"] for e in ledger.values() if isinstance(e.get("score"), (int, float))]
    n = len(scores)
    if n == 0:
        return {"n": 0}
    bands = {
        "9.0-10": sum(1 for s in scores if s >= 9.0),
        "8.0-8.9": sum(1 for s in scores if 8.0 <= s < 9.0),
        "7.0-7.9": sum(1 for s in scores if 7.0 <= s < 8.0),
        "6.0-6.9": sum(1 for s in scores if 6.0 <= s < 7.0),
        "5.0-5.9": sum(1 for s in scores if 5.0 <= s < 6.0),
        "3.0-4.9": sum(1 for s in scores if 3.0 <= s < 5.0),
        "1.0-2.9": sum(1 for s in scores if s < 3.0),
    }
    return {
        "n": n,
        "median": round(statistics.median(scores), 1),
        "mean": round(statistics.fmean(scores), 1),
        "above_8": sum(1 for s in scores if s >= 8.0),
        "below_5": sum(1 for s in scores if s < 5.0),
        "bands": bands,
    }


def format_scoring_context(
    product: dict, ledger: dict, products_by_id: dict, config: dict | None = None
) -> str:
    """Build the comparative-anchoring block injected into the scoring prompt.
    Returns '' when there is nothing to anchor against (cold-start)."""
    config = config or load_config()
    stats = distribution_stats(ledger)
    if stats.get("n", 0) < 2:
        return ""

    k = int(config.get("comparable_k", 18))
    comps = select_comparables(product, ledger, products_by_id, k=k)

    bands = stats["bands"]
    band_str = "  ".join(f"{label}:{cnt}" for label, cnt in bands.items())
    lines = [
        "## Comparative context (for RELATIVE ordering only)",
        "The rubric bands above are the ABSOLUTE authority on the number. The beans below show",
        "how prior beans were ranked against each other. Use them to place THIS bean in the",
        "ranking, NOT as a ceiling or a target. Do not compress this bean toward the catalog's",
        "current range.",
        "",
        f"Current catalog distribution ({stats['n']} beans scored so far). This set was largely",
        "scored by the OLD biased model that clustered everything at 6-7, so treat its range as",
        "suspect, not as truth. A genuinely excellent bean still scores 8+ even if nothing here",
        "has reached 8 yet; a genuinely poor one still scores below 5 even if nothing here has:",
        f"  median {stats['median']} | mean {stats['mean']} | "
        f"{stats['above_8']} scored >= 8.0 | {stats['below_5']} scored < 5.0",
        f"  bands: {band_str}",
        "",
    ]
    if comps:
        lines.append(
            "CLOSEST COMPARABLES (same roast / sensory / price tier), shown as <score>  <bean>  <why>:"
        )
        for e in comps:
            roast = (e.get("roast_level") or "?")
            lines.append(f"  {e['score']:>4}  {e.get('name', e['product_id'])} ({roast}) - {e.get('rationale', '')}")
        lines.append("")
        lines.append(
            "Rank THIS bean against these by quality: clearly better than a neighbour means a higher "
            "number, clearly worse means a lower one. But take the actual NUMBER from the absolute "
            "rubric bands, not from this set's range. Use the full scale where the bean earns it."
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# External critic - SANITY CHECK ONLY (never an anchor; never in the score prompt)
# ---------------------------------------------------------------------------

def normalize_critic(raw: float, scale_max: float, config: dict) -> float:
    """Map an external critic score to our 1-10 scale FOR COMPARISON ONLY.

    A 100-pt score uses the configured offset/divisor map. Any other scale_max is
    treated proportionally (raw/scale_max*10). Result is clamped to [min, max]."""
    cs = config.get("critic_scale", DEFAULT_CONFIG["critic_scale"])
    if scale_max and abs(scale_max - 100.0) > 1e-6:
        norm = (raw / scale_max) * 10.0
    else:
        norm = (raw - cs["offset"]) / cs["divisor"]
    return round(max(cs["min"], min(cs["max"], norm)), 1)


def find_external_critic_db(product: dict, min_match: float = 0.78) -> dict | None:
    """Look up a matching review in the scraped CoffeeReview corpus. Returns
    {raw, scale_max, source, name} or None. Strong-match only - we never want a
    loose name collision to masquerade as a critic verdict."""
    if not COFFEEREVIEW_DB.exists():
        return None
    try:
        sys.path.insert(0, str(_SCRAPERS_DIR))
        from coffeereview_db import get_conn, find_review  # type: ignore

        conn = get_conn(str(COFFEEREVIEW_DB))
        hits = find_review(conn, product.get("name", ""), product.get("brand"))
        conn.close()
        if not hits:
            return None
        score, slug, name, _roaster, rating = hits[0]
        if score < min_match or not rating:
            return None
        return {
            "raw": float(rating),
            "scale_max": 100.0,
            "source": f"coffeereview:{slug}",
            "name": name,
            "match": round(float(score), 3),
        }
    except Exception as e:
        print(f"[score_ledger] critic-db warning: {e}", file=sys.stderr)
        return None


def find_external_critic_web(product: dict, env: dict, config: dict) -> dict | None:
    """OPTIONAL best-effort web lookup of an external critic score, used only when
    --web-calibrate is set and the bean is not in the local corpus. Uses the
    Anthropic web_search server tool. Returns {raw, scale_max, source} or None.
    Degrades to None on any error or when offline - never blocks generation."""
    api_key = env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    wc = config.get("web_calibrate", DEFAULT_CONFIG["web_calibrate"])
    record_tool = {
        "name": "record_external_critic",
        "description": "Record a single external professional critic score for this coffee, if one was found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "found": {"type": "boolean"},
                "score": {"type": "number", "description": "The critic's numeric score, in its own scale."},
                "scale_max": {"type": "number", "description": "Max of that scale, e.g. 100 for CoffeeReview."},
                "source": {"type": "string", "description": "Publication + identifier, e.g. 'coffeereview.com 93'."},
            },
            "required": ["found"],
        },
    }
    prompt = (
        f"Find a single PROFESSIONAL critic score (e.g. CoffeeReview's 100-point rating, "
        f"or a notable award) for this exact coffee:\n"
        f"  Name: {product.get('name')}\n  Roaster: {product.get('brand')}\n"
        f"Only report a score you can attribute to a named professional publication for "
        f"THIS specific coffee. If you cannot find one with confidence, set found=false. "
        f"Do not guess. Then call record_external_critic."
    )
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=float(wc.get("timeout_seconds", 40)))
        resp = client.messages.create(
            model=wc.get("model", "claude-sonnet-4-6"),
            max_tokens=700,
            tools=[
                {"type": "web_search_20250305", "name": "web_search",
                 "max_uses": int(wc.get("max_searches", 3))},
                record_tool,
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use" and block.name == "record_external_critic":
                data = block.input
                if not data.get("found") or data.get("score") is None:
                    return None
                return {
                    "raw": float(data["score"]),
                    "scale_max": float(data.get("scale_max") or 100.0),
                    "source": f"web:{data.get('source', 'unknown')}",
                }
    except Exception as e:
        print(f"[score_ledger] web-calibrate unavailable ({e}); continuing offline.", file=sys.stderr)
    return None


def divergence_check(
    our_score: float, product: dict, config: dict,
    web_calibrate: bool = False, env: dict | None = None,
) -> tuple[dict | None, str | None]:
    """Compare OUR score against an external critic score (scraped, or web if asked).
    Returns (external_field, divergence_note). Never changes our_score.

    - within agreement_threshold  -> status 'agree', no note.
    - beyond divergence_threshold  -> status 'divergent' + a note flagging it for
      manual review. A big gap may mean we are wrong OR that we caught something the
      critic missed: that is the owner's call, not the model's.
    - critic_weight 'low' additionally records a bounded suggested nudge (never applied
      automatically). Default 'advisory' records nothing actionable, only the flag.
    """
    critic = find_external_critic_db(product)
    if critic is None and web_calibrate:
        critic = find_external_critic_web(product, env or {}, config)
    if critic is None:
        return None, None

    norm = normalize_critic(critic["raw"], critic.get("scale_max", 100.0), config)
    delta = round(our_score - norm, 1)
    agree = abs(delta) <= float(config.get("agreement_threshold", 1.0))
    divergent = abs(delta) > float(config.get("divergence_threshold", 1.5))

    external = {
        "raw": critic["raw"],
        "scale_max": critic.get("scale_max", 100.0),
        "normalized": norm,
        "source": critic["source"],
        "delta": delta,
        "status": "agree" if agree else ("divergent" if divergent else "near"),
    }

    if config.get("critic_weight") == "low" and divergent:
        max_nudge = float(config.get("max_nudge", 0.3))
        nudge = max(-max_nudge, min(max_nudge, delta * -1))  # toward critic, capped
        external["suggested_nudge"] = round(nudge, 1)  # advisory; human applies it

    note = None
    if divergent:
        note = (
            f"ours {our_score} vs critic ~{norm} (raw {critic['raw']}/"
            f"{int(critic.get('scale_max', 100))}, Δ{delta}) - manual review"
        )
    return external, note


# ---------------------------------------------------------------------------
# Histogram helper (used by backfill for the before/after report)
# ---------------------------------------------------------------------------

def histogram(scores: list[float], width: int = 40) -> str:
    """ASCII histogram of scores bucketed into 0.5-wide bins from 1.0 to 10.0."""
    if not scores:
        return "  (no scores)"
    bins: dict[float, int] = {}
    for s in scores:
        b = math.floor(s * 2) / 2  # 0.5 buckets
        bins[b] = bins.get(b, 0) + 1
    peak = max(bins.values())
    lines = []
    b = 1.0
    while b <= 10.0:
        cnt = bins.get(b, 0)
        bar = "#" * round((cnt / peak) * width) if cnt else ""
        lines.append(f"  {b:>4.1f}-{b + 0.49:>4.1f} | {cnt:>3} {bar}")
        b += 0.5
    n = len(scores)
    lines.append(
        f"  n={n}  min={min(scores):.1f}  median={statistics.median(scores):.1f}  "
        f"mean={statistics.fmean(scores):.1f}  max={max(scores):.1f}  "
        f"stdev={statistics.pstdev(scores):.2f}"
    )
    return "\n".join(lines)
