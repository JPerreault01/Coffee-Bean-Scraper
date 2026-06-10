# scrapers/select_products.py
"""
Selects beans from coffee_reference.db worth promoting to full reviews, enriches
each with an independent professional-critic signal from coffeereview.db, ranks
them by a tunable composite, and writes the shortlist to
data/promotion_candidates.json.

The reference DB has ~14k beans, but you only want full review pages for the
small subset you can actually monetize and that someone might search for. This
script filters, enriches, ranks, and writes the chosen beans to
data/promotion_candidates.json.

WHAT HAPPENS NEXT (the real downstream step)
--------------------------------------------
promotion_candidates.json is a SHORTLIST FOR HUMAN CURATION, not an automated
feed. The reference detail pages are already fully scraped into coffee_reference.db
(origin, flavor notes, roast, processing, varietals), so there is no further
scrape to run. The pipeline is:

    1. python scrapers/select_products.py --limit 50          # build the shortlist
    2. (you) read data/promotion_candidates.json, pick winners
    3. add each winner to scrapers/products.json (keyed by `id`/product_id)
    4. python scrapers/generate_review.py <product_id>        # write the draft

(The old in-code docs here cited `waytocoffee_scraper.py --details-for/--tag` and
`batch_build_products.py`. Those flags/scripts do not exist - see AUDIT_FINDINGS.md
D8. This docstring is the corrected version.)

CROSS-DATABASE ENRICHMENT
-------------------------
For each candidate we attempt a strong-match lookup in coffeereview.db
(coffeereview_db.find_review, threshold STRONG_MATCH). On a hit we attach the pro
0-100 rating, the five component scores (aroma/acidity/body/flavor/aftertaste),
the blind-assessment text, and the match confidence. A bean that exists in BOTH
databases is a higher-quality candidate (verified specs AND an independent quality
signal) and is ranked up via the `critic_data` weight.

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ SCORING FIREWALL - READ BEFORE TOUCHING THE ENRICHMENT CODE              │
  │                                                                          │
  │ The coffeereview critic data attached here is for SELECTION / RANKING    │
  │ and downstream FACTUAL CROSS-CHECKING ONLY. It must NEVER enter the      │
  │ review SCORING prompt. Our score is formed independently first (see      │
  │ score_ledger.py); the critic number is advisory and only flags large     │
  │ divergences for manual review AFTER our score exists.                    │
  │                                                                          │
  │ This firewall holds structurally: generate_review.py builds its scoring  │
  │ prompt from products.json fields, never from promotion_candidates.json,  │
  │ so `coffeereview_match` here cannot leak into the score. KEEP IT THAT    │
  │ WAY: do not copy `coffeereview_match` into a product record, and do not  │
  │ teach generate_review.py to read this file.                              │
  └─────────────────────────────────────────────────────────────────────────┘

RANKING
-------
Composite of four components, each 0-10, combined with the explicit WEIGHTS
constants below (easy to tune):
    monetizable   - direct-affiliate roaster > known-retail roaster > generic
    critic_data   - present in coffeereview.db (and how well it scored)
    searchable    - well-known roaster/bean -> more commercial search demand
    completeness  - flavor notes, origin, process, varietal, roaster present

Filters (all optional, combine freely):
    --roaster-allowlist FILE   only beans from these roasters (one per line)
    --origin TEXT              only beans whose origin contains TEXT (repeatable)
    --roast TEXT               only beans whose roast level contains TEXT
    --flavor TEXT              only beans with this flavor note (repeatable)
    --min-flavor-notes N       require at least N flavor notes (default 3)
    --require-roaster          only beans that already have a roaster recorded
    --min-critic-score N       only beans with a coffeereview rating >= N (0-100)
    --limit N                  cap output (default 100)

Optional enrichment:
    --enrich-web               best-effort web check (roaster alive? bean sold?
                               approx price? affiliate program?). Gated behind a
                               CLAUDE_API_KEY, capped by --web-limit, degrades to
                               None on any failure, never blocks the run. Mirrors
                               the gated pattern score_ledger uses for
                               --web-calibrate.
    --web-limit N              cap web lookups to the top-N ranked (default 15)

Usage:
    python scrapers/select_products.py --limit 50
    python scrapers/select_products.py --origin Ethiopia --roast light --limit 30
    python scrapers/select_products.py --roaster-allowlist roasters.txt
    python scrapers/select_products.py --min-critic-score 90 --limit 25
    python scrapers/select_products.py --limit 25 --enrich-web --web-limit 10
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from reference_db import get_conn, get_specs
except ImportError as e:
    print(f"Error: could not import reference_db: {e}", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    """Prefer the live VPS layout (/opt/...) but fall back to the repo for local runs."""
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


DEFAULT_DB = _resolve("/opt/data/coffee_reference.db", REPO_ROOT / "data" / "coffee_reference.db")
COFFEEREVIEW_DB = _resolve("/opt/data/coffeereview.db", REPO_ROOT / "data" / "coffeereview.db")
ENV_FILE = _resolve("/opt/.env", REPO_ROOT / ".env")
OUTPUT = REPO_ROOT / "data" / "promotion_candidates.json"

# --- ranking knobs (tune freely) -------------------------------------------
# Each component below returns 0-10; rank_score = sum(WEIGHTS[c]*comp[c]) / sum(WEIGHTS).
# Monetizability is the strongest signal (it is the whole point of the site);
# the independent critic signal is next; search demand and data completeness follow.
WEIGHTS = {
    "monetizable":  1.5,
    "critic_data":  1.2,
    "searchable":   1.0,
    "completeness": 0.8,
}

# Strong-match threshold for accepting a coffeereview.db row as THIS bean's critic
# verdict. Mirrors score_ledger.find_external_critic_db (0.78) so the two agree on
# what counts as the same coffee.
STRONG_MATCH = 0.78

# We only spend the (cheap) critic lookup on the top of the filtered pool, sized so
# any realistic winner is covered while a huge unfiltered run stays fast.
ENRICH_POOL_MULTIPLIER = 5
MIN_ENRICH_POOL = 800

WEB_LIMIT_DEFAULT = 15

# Roasters with their own direct affiliate program (best margin, 10-15%). Matched
# loosely as lowercase substrings. Keep in sync with CLAUDE.md "Affiliate programs".
DIRECT_AFFILIATE_ROASTERS = {
    "stumptown", "blue bottle", "death wish", "trade coffee",
}

# Well-known roasters with strong Amazon presence (4% grocery, but high search
# demand and conversion). Drives both monetizability (via Amazon) and searchability.
KNOWN_RETAIL_ROASTERS = {
    "lavazza", "illy", "peet", "starbucks", "dunkin", "kicking horse",
    "caribou", "gevalia", "eight o'clock", "folgers", "maxwell house",
    "cafe bustelo", "café bustelo", "bustelo", "community coffee", "koa",
    "intelligentsia", "counter culture", "la colombe", "verve", "onyx",
    "equator", "philz", "mccafe", "tim hortons", "coffee bros", "volcanica",
    "new england coffee", "the coffee bean", "san francisco bay", "ucc",
    "wide awake", "amazon fresh", "cameron's", "don pablo", "koffee kult",
    "fire department coffee", "black rifle", "bones coffee", "tiny footprint",
}


def load_allowlist(path: str | None) -> list[str] | None:
    if not path:
        return None
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip().lower() for l in lines if l.strip() and not l.startswith("#")]


def load_env() -> dict:
    """Read /opt/.env (or repo .env), then overlay os.environ. Mirrors generate_review."""
    import os
    env: dict = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


# ---------------------------------------------------------------------------
# Ranking components - each returns 0.0-10.0
# ---------------------------------------------------------------------------

def completeness_component(specs: dict) -> float:
    """Richer records score higher so you review the most complete beans first.
    Raw points (max 20) normalized to 0-10."""
    raw = 0
    raw += min(len(specs.get("flavor_notes", [])), 5) * 2  # up to 10
    raw += 3 if specs.get("roaster") else 0
    raw += 2 if specs.get("processing") else 0
    raw += 2 if specs.get("varietals") else 0
    raw += 2 if specs.get("origins") else 0
    raw += 1 if specs.get("roast_level") else 0
    return round(raw / 20 * 10, 2)


def monetizable_component(roaster: str, allowlist: list[str] | None) -> float:
    """Strongest manual signal. An owner-supplied allowlist match pins to 10.
    Otherwise: direct-affiliate roaster > known-retail (Amazon) > generic."""
    r = (roaster or "").lower()
    if allowlist and any(a in r for a in allowlist):
        return 10.0  # explicit owner signal: you said you can monetize this roaster
    if any(a in r for a in DIRECT_AFFILIATE_ROASTERS):
        return 10.0  # 10-15% direct program
    if any(a in r for a in KNOWN_RETAIL_ROASTERS):
        return 7.0   # Amazon 4%, but reliable availability + conversion
    if r:
        return 4.0   # has a roaster -> probably Amazon-listable
    return 1.0       # no roaster -> hard to place an affiliate link


def searchable_component(roaster: str, name: str) -> float:
    """Commercial search demand proxy. Known brands pull real query volume; an
    unknown roaster with a specific product name still beats a bare entry."""
    r = (roaster or "").lower()
    if any(a in r for a in DIRECT_AFFILIATE_ROASTERS) or any(a in r for a in KNOWN_RETAIL_ROASTERS):
        return 9.0
    has_roaster = bool(r)
    descriptive = len((name or "").split()) >= 2
    if has_roaster and descriptive:
        return 5.0
    if has_roaster or descriptive:
        return 4.0
    return 2.0


def critic_component(match: dict | None) -> float:
    """Independent quality signal. No critic data -> 0 (most beans). A strong match
    is rewarded for BOTH existing and how well it scored. coffeereview ratings cluster
    ~85-97, so we anchor the curve there: 88->7, 91->8, 94->9, 97->10."""
    if not match:
        return 0.0
    rating = match.get("rating")
    if not rating:
        return 6.0  # matched but unrated: presence alone is still a positive signal
    return round(min(10.0, 7.0 + (rating - 88) / 3.0), 2)


def composite(comp: dict) -> float:
    total_w = sum(WEIGHTS.values())
    return round(sum(WEIGHTS[k] * comp[k] for k in WEIGHTS) / total_w, 3)


# ---------------------------------------------------------------------------
# Cross-DB enrichment (coffeereview.db) - SELECTION/RANKING ONLY (see firewall)
# ---------------------------------------------------------------------------

def critic_lookup(cr_conn, name: str, roaster: str) -> dict | None:
    """Strong-match this bean against coffeereview.db. Returns a token-light record
    {slug, rating, component_scores, blind_assessment, match_confidence} or None.

    NOTE: advisory data for ranking/cross-check only. It must never reach the
    scoring prompt (see the firewall banner at the top of this file)."""
    if cr_conn is None:
        return None
    try:
        from coffeereview_db import find_review, get_specs as cr_get_specs

        hits = find_review(cr_conn, name or "", roaster or None)
        if not hits:
            return None
        conf, slug, _hit_name, _hit_roaster, rating = hits[0]
        if conf < STRONG_MATCH:
            return None  # loose collision: do not let it masquerade as a verdict
        specs = cr_get_specs(cr_conn, slug) or {}
        return {
            "slug": slug,
            "rating": rating,
            "component_scores": {
                "aroma":      specs.get("aroma"),
                "acidity":    specs.get("acidity"),
                "body":       specs.get("body"),
                "flavor":     specs.get("flavor"),
                "aftertaste": specs.get("aftertaste"),
            },
            "blind_assessment": specs.get("blind_assessment"),
            "match_confidence": round(float(conf), 3),
        }
    except Exception as e:
        print(f"[select_products] critic lookup warning: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Optional web verification - gated, best-effort, degrades to None
# ---------------------------------------------------------------------------

def web_verify(candidate: dict, env: dict) -> dict | None:
    """Best-effort web check of a candidate. Confirms the roaster is still trading,
    the bean is still sold, an approximate current price, and whether a direct
    affiliate program exists. Gated behind a CLAUDE_API_KEY; degrades to None on any
    error or when offline; NEVER blocks the run. Mirrors score_ledger's
    find_external_critic_web pattern (Anthropic web_search server tool)."""
    api_key = env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    record_tool = {
        "name": "record_web_verification",
        "description": "Record what was verified about this coffee from the live web.",
        "input_schema": {
            "type": "object",
            "properties": {
                "roaster_in_business": {"type": "boolean"},
                "bean_still_sold":     {"type": "boolean"},
                "approx_price_usd":    {"type": ["number", "null"],
                                        "description": "Current approx retail price for a standard bag, USD."},
                "affiliate_program":   {"type": ["string", "null"],
                                        "description": "Network/program if one exists (e.g. 'ShareASale', 'Amazon'), else null."},
                "source":              {"type": ["string", "null"],
                                        "description": "Primary URL or publication the answer came from."},
                "notes":               {"type": ["string", "null"]},
            },
            "required": ["roaster_in_business", "bean_still_sold"],
        },
    }
    prompt = (
        "Verify the current commercial status of this coffee using web search. Report only "
        "what you can confirm; do not guess. Then call record_web_verification.\n"
        f"  Bean:    {candidate.get('name')}\n"
        f"  Roaster: {candidate.get('roaster') or 'unknown'}\n"
        "Check: (1) is the roaster still in business, (2) is THIS bean still sold, "
        "(3) approximate current retail price in USD for a standard bag, "
        "(4) does the roaster run a direct affiliate program (and on what network)."
    )
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=45.0)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            tools=[
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
                record_tool,
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use" and block.name == "record_web_verification":
                data = dict(block.input)
                data["checked"] = True
                return data
    except Exception as e:
        print(f"[select_products] web verify unavailable ({e}); continuing offline.",
              file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Summary reporting
# ---------------------------------------------------------------------------

def rank_distribution(candidates: list[dict]) -> str:
    """ASCII band counts of rank_score for the run summary."""
    bands = [
        ("8.0-10 ", lambda s: s >= 8.0),
        ("6.0-7.9", lambda s: 6.0 <= s < 8.0),
        ("4.0-5.9", lambda s: 4.0 <= s < 6.0),
        ("2.0-3.9", lambda s: 2.0 <= s < 4.0),
        ("0.0-1.9", lambda s: s < 2.0),
    ]
    scores = [c.get("rank_score", 0.0) for c in candidates]
    if not scores:
        return "  (none)"
    peak = max(sum(1 for s in scores if pred(s)) for _, pred in bands) or 1
    lines = []
    for label, pred in bands:
        cnt = sum(1 for s in scores if pred(s))
        bar = "#" * round(cnt / peak * 30) if cnt else ""
        lines.append(f"  {label} | {cnt:>4} {bar}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Select beans to promote to full reviews")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--coffeereview-db", default=str(COFFEEREVIEW_DB),
                   help="coffeereview.db path for the cross-DB critic signal")
    p.add_argument("--roaster-allowlist", default=None, help="File of roaster names, one per line")
    p.add_argument("--origin", action="append", default=[], help="Filter: origin contains (repeatable)")
    p.add_argument("--roast", default=None, help="Filter: roast level contains")
    p.add_argument("--flavor", action="append", default=[], help="Filter: has flavor note (repeatable)")
    p.add_argument("--min-flavor-notes", type=int, default=3)
    p.add_argument("--require-roaster", action="store_true")
    p.add_argument("--min-critic-score", type=float, default=None,
                   help="Require a coffeereview rating >= this (0-100). Drops beans with no strong critic match.")
    p.add_argument("--enrich-web", action="store_true",
                   help="Best-effort web verification of the top candidates (gated by CLAUDE_API_KEY)")
    p.add_argument("--web-limit", type=int, default=WEB_LIMIT_DEFAULT,
                   help=f"Cap web lookups to the top-N ranked (default {WEB_LIMIT_DEFAULT})")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--output", default=str(OUTPUT))
    args = p.parse_args()

    if not Path(args.db).exists():
        print(f"Error: {args.db} not found. Run the scraper + reference_db.py load first.", file=sys.stderr)
        sys.exit(1)

    allowlist = load_allowlist(args.roaster_allowlist)
    origin_filters = [o.lower() for o in args.origin]
    flavor_filters = [f.lower() for f in args.flavor]
    roast_filter = args.roast.lower() if args.roast else None

    conn = get_conn(args.db)
    slugs = [row["slug"] for row in conn.execute("SELECT slug FROM coffees").fetchall()]
    print(f"Scanning {len(slugs)} beans...", file=sys.stderr)

    # --- Pass 1: filter + provisional score (no critic lookup yet) -----------
    candidates: list[dict] = []
    for slug in slugs:
        specs = get_specs(conn, slug)
        if not specs:
            continue

        notes = [n.lower() for n in specs.get("flavor_notes", [])]
        origins = [o.lower() for o in specs.get("origins", [])]
        roaster = (specs.get("roaster") or "")
        roaster_l = roaster.lower()
        roast = (specs.get("roast_level") or "").lower()

        if len(notes) < args.min_flavor_notes:
            continue
        if args.require_roaster and not roaster_l:
            continue
        if allowlist is not None and not any(a in roaster_l for a in allowlist):
            continue
        if origin_filters and not any(f in " ".join(origins) for f in origin_filters):
            continue
        if roast_filter and roast_filter not in roast:
            continue
        if flavor_filters and not all(any(f in n for n in notes) for f in flavor_filters):
            continue

        comp = {
            "completeness": completeness_component(specs),
            "monetizable":  monetizable_component(roaster, allowlist),
            "searchable":   searchable_component(roaster, specs["name"]),
            "critic_data":  0.0,  # filled in pass 2 for the enrichment pool
        }
        candidates.append({
            "url": specs.get("url", ""),
            "name": specs["name"],
            "roaster": roaster,
            "roaster_url": specs.get("roaster_url", ""),
            "roast_level": specs.get("roast_level", ""),
            "origins": specs.get("origins", []),
            "flavor_notes": specs.get("flavor_notes", []),
            "processing": specs.get("processing", []),
            "typology": specs.get("varietals", []),
            "coffeereview_match": None,
            "_comp": comp,
        })

    conn.close()

    # Provisional ordering (critic still 0) so we enrich the most promising first.
    for c in candidates:
        c["rank_score"] = composite(c["_comp"])
    candidates.sort(key=lambda c: c["rank_score"], reverse=True)

    # --- Pass 2: cross-DB critic enrichment on the top pool ------------------
    cr_conn = None
    if Path(args.coffeereview_db).exists():
        try:
            from coffeereview_db import get_conn as cr_get_conn
            cr_conn = cr_get_conn(args.coffeereview_db)
        except Exception as e:
            print(f"[select_products] coffeereview.db unavailable: {e}", file=sys.stderr)
    else:
        print(f"[select_products] note: {args.coffeereview_db} not found; "
              "skipping critic enrichment.", file=sys.stderr)

    pool_size = max(args.limit * ENRICH_POOL_MULTIPLIER, MIN_ENRICH_POOL)
    pool = candidates[:pool_size]
    matched = 0
    if cr_conn is not None:
        for c in pool:
            match = critic_lookup(cr_conn, c["name"], c["roaster"])
            if match:
                c["coffeereview_match"] = match
                c["_comp"]["critic_data"] = critic_component(match)
                c["rank_score"] = composite(c["_comp"])
                matched += 1
        cr_conn.close()

    # --min-critic-score: keep only beans whose strong critic match clears the bar.
    if args.min_critic_score is not None:
        before = len(candidates)
        candidates = [
            c for c in candidates
            if c.get("coffeereview_match")
            and (c["coffeereview_match"].get("rating") or 0) >= args.min_critic_score
        ]
        print(f"--min-critic-score {args.min_critic_score}: kept {len(candidates)} of "
              f"{before} (require coffeereview rating >= {args.min_critic_score})",
              file=sys.stderr)

    # Final ranking after critic data is in.
    candidates.sort(key=lambda c: c["rank_score"], reverse=True)
    selected = candidates[:args.limit]

    # --- Pass 3: optional web verification of the top selected ---------------
    web_enriched = 0
    if args.enrich_web:
        env = load_env()
        if not (env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY")):
            print("[select_products] --enrich-web set but no CLAUDE_API_KEY found; "
                  "skipping web verification.", file=sys.stderr)
        else:
            web_n = min(args.web_limit, len(selected))
            print(f"Web-verifying top {web_n} candidates...", file=sys.stderr)
            for c in selected[:web_n]:
                info = web_verify(c, env)
                if info:
                    c["web_enrichment"] = info
                    web_enriched += 1

    # --- Finalize output -----------------------------------------------------
    for c in selected:
        c["rank_breakdown"] = {
            **{k: round(v, 2) for k, v in c["_comp"].items()},
            "weights": WEIGHTS,
            "weighted_total": c["rank_score"],
        }
        c.pop("_comp", None)
        c.setdefault("web_enrichment", None)

    Path(args.output).write_text(
        json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # --- Summary -------------------------------------------------------------
    print("", file=sys.stderr)
    print(f"Selected {len(selected)} of {len(candidates)} matching beans -> {args.output}",
          file=sys.stderr)
    print(f"  coffeereview matches (strong, >= {STRONG_MATCH}): {matched} in the "
          f"top {len(pool)} enrichment pool", file=sys.stderr)
    sel_matched = sum(1 for c in selected if c.get("coffeereview_match"))
    print(f"  of the {len(selected)} selected, {sel_matched} carry verified critic data",
          file=sys.stderr)
    if args.enrich_web:
        print(f"  web-enriched: {web_enriched}", file=sys.stderr)
    print("  rank_score distribution (selected):", file=sys.stderr)
    print(rank_distribution(selected), file=sys.stderr)
    print("", file=sys.stderr)
    print("Next: review data/promotion_candidates.json, add winners to "
          "scrapers/products.json, then run", file=sys.stderr)
    print("      python scrapers/generate_review.py <product_id>", file=sys.stderr)


if __name__ == "__main__":
    main()
