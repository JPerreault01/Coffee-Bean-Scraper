#!/usr/bin/env python3
"""Upsert verified bean entries into scrapers/products.json.

Reads a JSON array of bean dicts from a path given as argv[1] and merges each
into products.json by `id`:

  - New id  -> appended as a full entry in canonical field order.
  - Existing id -> merged WITHOUT clobbering curated data:
        * factual fields (name, brand, roast_level, origin, process_method,
          weight_oz, roaster_url, affiliate_tag, profile_source, price_*)
          are overwritten from the incoming (verified) data;
        * amazon_asin is only overwritten when the incoming value is a real
          ASIN (a non-null, non-"BACKFILL" string) -- a real existing ASIN is
          never replaced by null/BACKFILL;
        * editorial fields (flavor_notes, comparison_anchors, best_brew_methods,
          sensory 1-5 scores, review_framing) are only filled when the existing
          value is null/empty, so hand-curated entries keep their curation.

Round-trips byte-for-byte with the existing 2-space, ensure_ascii=False format.
Run from repo root:  python scripts/upsert_products.py drafts/_batchN_beans.json
"""
import json
import sys
from pathlib import Path

PRODUCTS = Path(__file__).resolve().parents[1] / "scrapers" / "products.json"

ORDER = [
    "id", "name", "brand", "roast_level", "origin", "process_method",
    "weight_oz", "amazon_asin", "roaster_url", "affiliate_tag",
    "best_brew_methods", "flavor_notes", "acidity", "body", "sweetness",
    "bitterness", "roast_intensity", "review_framing", "comparison_anchors",
    "reference_slug", "profile_source", "price_per_oz", "price_status",
]
FACTUAL = {
    "name", "brand", "roast_level", "origin", "process_method", "weight_oz",
    "roaster_url", "affiliate_tag", "profile_source", "price_per_oz",
    "price_status",
}
EDITORIAL_SCORES = {"acidity", "body", "sweetness", "bitterness",
                    "roast_intensity", "review_framing"}
EDITORIAL_LISTS = {"flavor_notes", "comparison_anchors", "best_brew_methods"}


def canonical(entry):
    out = {}
    for k in ORDER:
        if k in entry:
            out[k] = entry[k]
    # keep any extra keys at the end (defensive)
    for k, v in entry.items():
        if k not in out:
            out[k] = v
    return out


def is_real_asin(v):
    return isinstance(v, str) and v.strip() and v.strip().upper() != "BACKFILL"


def merge(existing, incoming):
    for k, v in incoming.items():
        if k == "id":
            continue
        if k == "amazon_asin":
            if is_real_asin(v):
                existing[k] = v
            elif k not in existing:
                existing[k] = v
        elif k in FACTUAL:
            existing[k] = v
        elif k in EDITORIAL_SCORES:
            if existing.get(k) is None:
                existing[k] = v
        elif k in EDITORIAL_LISTS:
            if not existing.get(k):
                existing[k] = v
        else:
            existing.setdefault(k, v)
    return existing


def main():
    incoming = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    data = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    idx = {e["id"]: i for i, e in enumerate(data)}
    added, updated = [], []
    for raw in incoming:
        bean = canonical(raw)
        bid = bean["id"]
        if bid in idx:
            merge(data[idx[bid]], bean)
            updated.append(bid)
        else:
            data.append(bean)
            idx[bid] = len(data) - 1
            added.append(bid)
    PRODUCTS.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"entries now: {len(data)}")
    print(f"added ({len(added)}): {added}")
    print(f"updated ({len(updated)}): {updated}")


if __name__ == "__main__":
    main()
