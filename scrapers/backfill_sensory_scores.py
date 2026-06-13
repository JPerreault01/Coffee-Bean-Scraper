#!/usr/bin/env python3
"""
scrapers/backfill_sensory_scores.py
===================================
Give EVERY bean a complete 5-axis sensory profile (acidity, body, sweetness,
bitterness, roast_intensity on a 1-5 scale) so the flavor radar renders on every
page. Fills two files from one pass:

  1. scrapers/products.json   — consumed by create_beans.php at draft creation
                                (so future/new beans get a radar automatically).
  2. data/sensory_scores.json — consumed by populate_sensory_scores.php, the
                                overlay that updates beans ALREADY created on the
                                server (create_beans.php skips existing posts).

Score provenance, in priority order, recorded in the `confidence` field of
sensory_scores.json (reusing the existing high/low tag) so the data layer always
knows which axes were sourced vs inferred:

  * "high"/"low"  — pre-existing AI scores (ai_sensory_scores.py). Preserved
                    VERBATIM; never recomputed.
  * "high"        — curated values already present in products.json.
  * "derived"     — inferred here from the bean's own roast level, origin,
                    process method and flavor notes (the same rubric the AI
                    scorer uses), with coffeereview.db as a body/roast
                    corroborator where a confident name match exists. Derived
                    beans also carry an `axis_sources` map noting per-axis origin.

The provenance tag is data-only. It is NOT surfaced on the chart.

Usage (local, no API calls, no network):
  python scrapers/backfill_sensory_scores.py            # dry run: report only
  python scrapers/backfill_sensory_scores.py --write    # write both files
"""

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
PRODUCTS_PATH = _SCRIPT_DIR / "products.json"
SCORES_PATH = _REPO_ROOT / "data" / "sensory_scores.json"

AXES = ["acidity", "body", "sweetness", "bitterness", "roast_intensity"]

# coffeereview.db is deliberately NOT used here. Its component scores (acidity,
# body) are 1-10 QUALITY ratings, not intensity, and compressed near 8-9 — so a
# delicate, high-quality Yirgacheffe scores "body 8" and would wrongly read as a
# heavy body on the radar. coffeereview is wired into ai_sensory_scores.py
# instead, where the model interprets those scores in context. This backfill
# derives purely from each bean's own attributes for a self-consistent result.


# --------------------------------------------------------------------------
# Attribute vocabulary (lowercase substring matching keeps this resilient to
# the long tail of process strings like "200 Hour Anaerobic Natural").
# --------------------------------------------------------------------------

ROAST_INTENSITY = {
    "light": 2,
    "light-medium": 2,
    "medium": 3,
    "medium-dark": 4,
    "dark": 5,
}

# Acidity base from roast intensity (darker roast -> flatter acidity).
ACIDITY_FROM_RI = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1}
# Body base from roast intensity (darker roast -> fuller body).
BODY_FROM_RI = {1: 2, 2: 2, 3: 3, 4: 4, 5: 4}
# Bitterness base from roast intensity (roast is the dominant driver).
BITTER_FROM_RI = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}

BRIGHT_ORIGINS = (
    "ethiopia", "yirgacheffe", "guji", "sidama", "kenya", "kirinyaga", "nyeri",
    "embu", "rwanda", "burundi", "colombia", "nariño", "narino", "huila",
    "costa rica", "tarrazu", "tarrazú", "guatemala", "huehuetenango", "panama",
    "el salvador", "ecuador", "tanzania", "bolivia",
)
HEAVY_ORIGINS = (
    "sumatra", "indonesia", "mandheling", "aceh", "java", "india", "monsoon",
    "malabar", "brazil", "hawaii", "kona", "malaysia", "vietnam",
)
# Delicate, tea-like to silky bodies (washed high-grown Africans / Central
# washed). Pulls body DOWN unless a fuller process (natural/honey) offsets it.
LIGHT_BODY_ORIGINS = (
    "ethiopia", "yirgacheffe", "guji", "sidama", "kenya", "kirinyaga", "nyeri",
    "embu", "rwanda", "burundi",
)

BRIGHT_NOTES = (
    "citrus", "lemon", "lime", "orange", "grapefruit", "bergamot", "berry",
    "blueberry", "strawberry", "raspberry", "cherry", "floral", "jasmine",
    "hibiscus", "rose", "wine", "winey", "tart", "apple", "stone fruit",
    "apricot", "peach", "tropical", "pineapple", "mango", "bright", "juicy",
    "malic", "lemongrass", "yuzu",
)
RICH_NOTES = (
    "chocolate", "cocoa", "caramel", "brown sugar", "molasses", "toffee",
    "nutty", "hazelnut", "walnut", "almond", "earthy", "smoky", "tobacco",
    "cedar", "malt", "butterscotch", "dark", "bold", "woody",
)
SWEET_NOTES = (
    "caramel", "honey", "brown sugar", "toffee", "molasses", "chocolate",
    "milk chocolate", "cocoa", "vanilla", "maple", "butterscotch", "dulce",
    "fruit", "berry", "cherry", "stone fruit", "dried fruit", "syrup",
    "marshmallow", "graham", "cookie", "panela", "shortbread", "sugar",
)
SAVORY_NOTES = (
    "earthy", "woody", "tobacco", "smoky", "charred", "spice", "spicy",
    "herbal", "cedar", "chicory", "pipe", "savory",
)
BITTER_NOTES = (
    "dark chocolate", "bittersweet", "bitter", "smoky", "charred", "bold",
    "intense", "chicory", "tobacco", "dark roast",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def _clamp(v: float) -> int:
    # round half up (Python's round() uses banker's rounding: 2.5 -> 2)
    return max(1, min(5, int(v + 0.5) if v >= 0 else int(v - 0.5)))


def _has_any(haystack: str, needles) -> int:
    """Count how many distinct needles appear in haystack."""
    return sum(1 for n in needles if n in haystack)


def roast_intensity(roast_level: str) -> int:
    key = (roast_level or "").strip().lower()
    if key in ROAST_INTENSITY:
        return ROAST_INTENSITY[key]
    # substring fallback for anything off-vocabulary
    if "medium-dark" in key or "medium dark" in key:
        return 4
    if "dark" in key or "french" in key or "italian" in key:
        return 5
    if "light-medium" in key or "medium-light" in key or "light medium" in key:
        return 2
    if "light" in key or "blonde" in key:
        return 2
    if "medium" in key:
        return 3
    return 3  # unknown -> assume medium


# --------------------------------------------------------------------------
# The rubric — derive a full 5-axis profile from a bean's own attributes.
# --------------------------------------------------------------------------

def derive_scores(product):
    roast = product.get("roast_level") or ""
    origin = _norm(product.get("origin") or "")
    process = (product.get("process_method") or "").lower()
    notes = " ".join(product.get("flavor_notes") or []).lower()

    ri = roast_intensity(roast)

    is_washed = "wash" in process
    is_natural = ("natural" in process or "honey" in process
                  or "anaerobic" in process or "macer" in process)
    bright_origin = any(o in origin for o in BRIGHT_ORIGINS)
    heavy_origin = any(o in origin for o in HEAVY_ORIGINS)
    robusta_ish = any(k in (product.get("name", "") + notes).lower()
                      for k in ("crema", "espresso", "robusta"))

    axis_src = {}

    # --- acidity ---
    a = ACIDITY_FROM_RI[ri]
    if bright_origin:
        a += 1
    if heavy_origin:
        a -= 1
    if is_washed:
        a += 0.5
    if is_natural:
        a -= 0.5
    a += 0.5 * min(_has_any(notes, BRIGHT_NOTES), 2)
    a -= 0.5 * min(_has_any(notes, RICH_NOTES), 2)
    acidity = _clamp(a)
    axis_src["acidity"] = "inferred:roast+origin+process+notes"

    # --- body ---
    b = BODY_FROM_RI[ri]
    if heavy_origin:
        b += 1
    if any(o in origin for o in LIGHT_BODY_ORIGINS) and not heavy_origin:
        b -= 1
    if is_natural:
        b += 0.5
    if robusta_ish:
        b += 1
    if any(k in notes for k in ("full body", "syrup", "creamy", "round body",
                                "heavy", "thick", "molasses", "dark chocolate")):
        b += 0.5
    if any(k in notes for k in ("tea-like", "delicate", "light body", "silky", "juicy")):
        b -= 0.5
    body = _clamp(b)
    axis_src["body"] = "inferred:roast+origin+process+notes"

    # --- sweetness ---
    sw = 3 + 0.5 * min(_has_any(notes, SWEET_NOTES), 3)
    sw -= 0.5 * min(_has_any(notes, SAVORY_NOTES), 2)
    if is_natural:
        sw += 0.5
    if ri == 5:
        sw -= 1  # heavy roast bitterness masks sweetness
    sweetness = _clamp(sw)
    axis_src["sweetness"] = "inferred:notes+process+roast"

    # --- bitterness ---
    bi = BITTER_FROM_RI[ri]
    if robusta_ish or "chicory" in notes:
        bi += 1
    bi += 0.5 * min(_has_any(notes, BITTER_NOTES), 2)
    if any(k in notes for k in BRIGHT_NOTES) and ri <= 3:
        bi -= 0.5
    bitterness = _clamp(bi)
    axis_src["bitterness"] = "inferred:roast+notes"

    # --- roast_intensity ---
    axis_src["roast_intensity"] = "sourced:roast_level"

    scores = {
        "acidity": acidity,
        "body": body,
        "sweetness": sweetness,
        "bitterness": bitterness,
        "roast_intensity": ri,
    }
    bits = []
    if roast:
        bits.append(f"roast {roast.lower()}")
    if product.get("origin"):
        bits.append(f"origin {product['origin']}")
    if product.get("process_method"):
        bits.append(f"process {product['process_method']}")
    if product.get("flavor_notes"):
        bits.append("notes " + ", ".join(product["flavor_notes"]))
    just = "Derived from " + "; ".join(bits) + "." if bits else \
        "Derived from roast level; no other attributes available."
    sources = ["derived:attributes"]
    return scores, just, sources, axis_src


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="Write products.json and data/sensory_scores.json "
                         "(default: dry run, report only)")
    args = ap.parse_args()

    products = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    scores = json.loads(SCORES_PATH.read_text(encoding="utf-8")) if SCORES_PATH.exists() else {}
    print(f"Loaded {len(products)} products, {len(scores)} existing scored beans.")

    n_existing = n_ai = n_derived = n_curated = 0
    unfilled = []

    for p in products:
        pid = p["id"]
        present = all(isinstance(p.get(a), (int, float)) for a in AXES)

        if present:
            # Curated values already in products.json. Ensure the overlay file
            # has an entry so existing posts get these too.
            n_existing += 1
            if pid not in scores:
                scores[pid] = {
                    "scores": {a: int(p[a]) for a in AXES},
                    "confidence": "high",
                    "justification": "Curated values from products.json.",
                    "sources": ["products_json"],
                }
                n_curated += 1
            continue

        if pid in scores and all(
            isinstance(scores[pid].get("scores", {}).get(a), (int, float)) for a in AXES
        ):
            # Pre-existing AI score — authoritative. Backfill products.json from it.
            s = scores[pid]["scores"]
            for a in AXES:
                if p.get(a) is None:
                    p[a] = int(s[a])
            n_ai += 1
            continue

        # Derive from attributes.
        s, just, sources, axis_src = derive_scores(p)
        for a in AXES:
            if p.get(a) is None:
                p[a] = s[a]
        scores[pid] = {
            "scores": s,
            "confidence": "derived",
            "justification": just,
            "sources": sources,
            "axis_sources": axis_src,
        }
        n_derived += 1

    # Final integrity check.
    for p in products:
        miss = [a for a in AXES if not isinstance(p.get(a), (int, float))]
        if miss:
            unfilled.append((p["id"], miss))

    print("\n--- BACKFILL SUMMARY ---")
    print(f"  already curated in products.json : {n_existing}")
    print(f"  filled from existing AI scores   : {n_ai}")
    print(f"  derived from attributes          : {n_derived}")
    print(f"  curated entries added to overlay : {n_curated}")
    print(f"  unified sensory_scores.json beans: {len(scores)}")
    if unfilled:
        print(f"  STILL UNFILLED ({len(unfilled)}): {unfilled}")
    else:
        print("  every bean now has all 5 axes. No nulls remain.")

    # Confidence distribution in the overlay file.
    from collections import Counter
    conf = Counter(v.get("confidence") for v in scores.values())
    print(f"  overlay confidence breakdown     : {dict(conf)}")

    if not args.write:
        print("\nDry run. Re-run with --write to save both files.")
        return

    PRODUCTS_PATH.write_text(
        json.dumps(products, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    SCORES_PATH.write_text(
        json.dumps(scores, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {PRODUCTS_PATH}")
    print(f"Wrote {SCORES_PATH}")


if __name__ == "__main__":
    main()
