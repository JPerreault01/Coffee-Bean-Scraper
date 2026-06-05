# scrapers/select_products.py
"""
Selects beans from coffee_reference.db worth promoting to full reviews.

The reference DB has ~17k beans, but you only want full review pages for the
small subset you can actually monetize and that someone might search for. This
script filters + ranks and writes the chosen beans to data/promotion_candidates.json,
which then feeds the detail-page scrape:

    python scrapers/select_products.py --roaster-allowlist roasters.txt --limit 100
    python scrapers/waytocoffee_scraper.py --details-for data/promotion_candidates.json --tag your-tag-20
    python scrapers/batch_build_products.py

Selection is deliberately conservative. The strongest monetization signal is
"is this roaster one I'm an affiliate of" — supply that via --roaster-allowlist
(one roaster name per line, matched loosely). Everything else is a filter you
control; this script does not pretend an algorithm can pick winners for you.

Filters (all optional, combine freely):
    --roaster-allowlist FILE   only beans from these roasters (one per line)
    --origin TEXT              only beans whose origin contains TEXT (repeatable)
    --roast TEXT               only beans whose roast level contains TEXT
    --flavor TEXT              only beans with this flavor note (repeatable)
    --min-flavor-notes N       require at least N flavor notes (default 3 — filters thin records)
    --limit N                  cap output (default 100)
    --require-roaster          only beans that already have a roaster recorded

Ranking: beans with more complete data (more flavor notes, has roaster, has
processing + typology) rank first, so you review the richest entries.

Usage:
    python scrapers/select_products.py --limit 50
    python scrapers/select_products.py --origin Ethiopia --roast light --limit 30
    python scrapers/select_products.py --roaster-allowlist roasters.txt
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
DEFAULT_DB = REPO_ROOT / "data" / "coffee_reference.db"
OUTPUT = REPO_ROOT / "data" / "promotion_candidates.json"


def load_allowlist(path: str | None) -> list[str] | None:
    if not path:
        return None
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip().lower() for l in lines if l.strip() and not l.startswith("#")]


def completeness_score(specs: dict) -> int:
    """More-complete records score higher so you review the richest beans first."""
    score = 0
    score += min(len(specs.get("flavor_notes", [])), 5) * 2  # up to 10
    score += 3 if specs.get("roaster") else 0
    score += 2 if specs.get("processing") else 0
    score += 2 if specs.get("varietals") else 0
    score += 2 if specs.get("origins") else 0
    score += 1 if specs.get("roast_level") else 0
    return score


def main() -> None:
    p = argparse.ArgumentParser(description="Select beans to promote to full reviews")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--roaster-allowlist", default=None, help="File of roaster names, one per line")
    p.add_argument("--origin", action="append", default=[], help="Filter: origin contains (repeatable)")
    p.add_argument("--roast", default=None, help="Filter: roast level contains")
    p.add_argument("--flavor", action="append", default=[], help="Filter: has flavor note (repeatable)")
    p.add_argument("--min-flavor-notes", type=int, default=3)
    p.add_argument("--require-roaster", action="store_true")
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

    candidates = []
    for slug in slugs:
        specs = get_specs(conn, slug)
        if not specs:
            continue

        notes = [n.lower() for n in specs.get("flavor_notes", [])]
        origins = [o.lower() for o in specs.get("origins", [])]
        roaster = (specs.get("roaster") or "").lower()
        roast = (specs.get("roast_level") or "").lower()

        if len(notes) < args.min_flavor_notes:
            continue
        if args.require_roaster and not roaster:
            continue
        if allowlist is not None and not any(a in roaster for a in allowlist):
            continue
        if origin_filters and not any(f in " ".join(origins) for f in origin_filters):
            continue
        if roast_filter and roast_filter not in roast:
            continue
        if flavor_filters and not all(any(f in n for n in notes) for f in flavor_filters):
            continue

        candidates.append({
            "url": specs.get("url", ""),
            "name": specs["name"],
            "roaster": specs.get("roaster", ""),
            "roaster_url": specs.get("roaster_url", ""),
            "roast_level": specs.get("roast_level", ""),
            "origins": specs.get("origins", []),
            "flavor_notes": specs.get("flavor_notes", []),
            "processing": specs.get("processing", []),
            "typology": specs.get("varietals", []),
            "_score": completeness_score(specs),
        })

    conn.close()

    candidates.sort(key=lambda c: c["_score"], reverse=True)
    selected = candidates[:args.limit]
    for c in selected:
        c.pop("_score", None)

    Path(args.output).write_text(json.dumps(selected, indent=2, ensure_ascii=False))
    print(f"Selected {len(selected)} of {len(candidates)} matching beans -> {args.output}", file=sys.stderr)
    print("Next: python scrapers/waytocoffee_scraper.py --details-for "
          f"{args.output} --tag your-tag-20", file=sys.stderr)


if __name__ == "__main__":
    main()
