# scrapers/preflight.py
"""
Phase 0 pre-flight gate for the review-generation pipeline (see
REVIEW_GENERATION_RUNBOOK.md). Validate products.json against the importers BEFORE
generating a single draft. Generation is the expensive step; every defect found
after it costs a regenerate or a manual server-side fix.

The June 2026 batch lost time to three classes of defect, all knowable from
products.json alone:
  1. Encoding   - accented names crashing cp1252 I/O.
  2. Taxonomy-map gaps - origins / flavor strings missing from create_beans.php.
  3. Bad source URLs - affiliate redirects and shared placeholder roaster_urls.

All three are static checks. This script runs them and exits non-zero on any hard
failure, printing `PREFLIGHT CLEAN` only when the batch is safe to generate.

Usage:
    python scrapers/preflight.py                 # check the whole catalog
    python scrapers/preflight.py --since 171     # only check records from index 171 on
    python scrapers/preflight.py --ids a,b,c      # only check these product ids
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from url_filters import is_skippable_url, build_placeholder_urls  # noqa: E402

# Names legitimately carry accents/macrons (Quindío, Tarrazú, Ka'ū). Never strip
# them — make the reader UTF-8 clean instead (RUNBOOK Phase 0.5 / Phase 2 Encoding).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = REPO_ROOT / "scrapers" / "products.json"
CREATE_BEANS = REPO_ROOT / "scrapers" / "create_beans.php"

REQUIRED = ("id", "name", "brand", "origin", "roast_level", "process_method", "weight_oz")
# Grade codes / acronyms that must stay upper-case through name normalization.
GRADE_CODES = {"AA", "AB", "PB", "WBC", "NX", "WX", "G1", "G2", "SL28", "SL34", "USDA", "SHB", "SHG", "GMCR"}

_PHP_KEY = re.compile(r"""(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*=>""")


def _block(text: str, marker: str) -> str:
    """Return the text inside `$marker = [ ... ];`."""
    start = text.index(marker)
    depth = 0
    i = text.index("[", start)
    j = i
    for j in range(i, len(text)):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                break
    return text[i : j + 1]


def _unescape(s: str) -> str:
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def load_php_maps() -> tuple[set[str], set[str], set[str]]:
    """Extract origin-map keys, flavor-canonical-map keys, and structural-drop
    strings from create_beans.php."""
    text = CREATE_BEANS.read_text(encoding="utf-8")
    origin_block = _block(text, "$origin_map")
    flavor_block = _block(text, "$flavor_canonical_map")
    drops_block = _block(text, "$flavor_structural_drops")

    origin_keys = {_unescape(m.group(1) if m.group(1) is not None else m.group(2))
                   for m in _PHP_KEY.finditer(origin_block)}
    flavor_keys = {_unescape(m.group(1) if m.group(1) is not None else m.group(2))
                   for m in _PHP_KEY.finditer(flavor_block)}
    drops = {_unescape(m.group(1) if m.group(1) is not None else m.group(2))
             for m in re.finditer(r"'((?:[^'\\]|\\.)*)'", drops_block)}
    return origin_keys, flavor_keys, drops


def caps_issue(name: str) -> bool:
    """A word in ALL CAPS that is not a known grade code signals un-normalized casing."""
    for w in re.findall(r"[A-Za-z][A-Za-z']+", name or ""):
        if w.isupper() and w not in GRADE_CODES and len(w) > 1:
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 0 pre-flight gate")
    p.add_argument("--since", type=int, default=None,
                   help="Only check records from this index onward (the new batch)")
    p.add_argument("--ids", default=None, help="Comma-separated product ids to check")
    args = p.parse_args()

    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    origin_keys, flavor_keys, drops = load_php_maps()

    scope = products
    if args.since is not None:
        scope = products[args.since:]
    if args.ids:
        want = {i.strip() for i in args.ids.split(",") if i.strip()}
        scope = [p for p in products if p["id"] in want]

    print(f"Pre-flight: checking {len(scope)} of {len(products)} products "
          f"against {len(origin_keys)} origin keys / {len(flavor_keys)} flavor keys")

    hard = 0
    warn = 0

    # 0.1 Required-field completeness
    for prod in scope:
        for f in REQUIRED:
            v = prod.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                print(f"  HARD [missing {f}] {prod.get('id')}")
                hard += 1
        # A bean needs at least one resolvable image/purchase source. amazon_asin or
        # roaster_url give both; a reference_slug gives a per-bean image fallback
        # (fetch_bean_images source 4) and a valid review page — the affiliate "Buy"
        # link is then a tracked backfill (data/affiliate_link_pending.json), which
        # the pipeline tolerates (RUNBOOK Phase 4 image-residue note).
        if not prod.get("amazon_asin") and not prod.get("roaster_url") \
                and (not prod.get("reference_slug") or prod.get("reference_slug") == "_skip"):
            print(f"  HARD [no asin, no roaster_url, no reference_slug] {prod.get('id')}")
            hard += 1

    # 0.2 Origin-map coverage
    for prod in scope:
        o = prod.get("origin")
        if o is not None and o not in origin_keys:
            print(f"  HARD [unmapped origin] {prod['id']}: {o!r}")
            hard += 1

    # 0.3 Flavor-map coverage
    for prod in scope:
        for fn in prod.get("flavor_notes", []):
            key = (fn or "").lower()
            if key not in flavor_keys and key not in drops:
                print(f"  HARD [unmapped flavor] {prod['id']}: {fn!r}")
                hard += 1

    # 0.4 URL hygiene
    placeholders = build_placeholder_urls(products)  # cluster detection across full catalog
    for prod in scope:
        url = prod.get("roaster_url")
        if url and is_skippable_url(url) and not prod.get("amazon_asin"):
            print(f"  HARD [affiliate/social roaster_url, no asin fallback] {prod['id']}: {url}")
            hard += 1
        if url and (prod.get("brand", ""), url) in placeholders:
            print(f"  HARD [placeholder cluster url] {prod['id']}: {url}")
            hard += 1

    # 0.5 Encoding + name casing
    for prod in scope:
        for f in ("name", "brand"):
            v = prod.get(f) or ""
            if "�" in v or "Ã" in v or "â€" in v:
                print(f"  HARD [mojibake in {f}] {prod['id']}: {v!r}")
                hard += 1
            if caps_issue(v):
                print(f"  WARN [ALL-CAPS word in {f}] {prod['id']}: {v!r}")
                warn += 1

    # 0.6 reference_slug presence (warn-only; image fallback of last resort)
    for prod in scope:
        if not prod.get("reference_slug"):
            print(f"  WARN [no reference_slug] {prod['id']}")
            warn += 1

    print(f"\n{hard} hard failure(s), {warn} warning(s).")
    if hard == 0:
        print("PREFLIGHT CLEAN")
        return 0
    print("PREFLIGHT FAILED — fix hard failures before generating.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
