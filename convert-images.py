#!/usr/bin/env python3
"""
convert-images.py — homepage image optimiser for Coffee Bean Index.

Reads every .jpg/.jpeg/.png in ./homepage-images/, resizes (hero -> max
1920px wide, cards -> max 600px wide, aspect ratio preserved), and writes
WebP (quality 82, method 6) to ./homepage-images/web/.

The "hero" image is detected by the substring "hero" in its filename.
Prints each output filename and its size in KB, and flags any hero over
200 KB or card over 80 KB so they can be re-sourced.

Usage (from repo root, venv active):
    python convert-images.py
"""

import re
from pathlib import Path

from PIL import Image

SRC_DIR  = Path(__file__).parent / "homepage-images"
OUT_DIR  = SRC_DIR / "web"
HERO_MAX = 1920
CARD_MAX = 600
QUALITY  = 82
METHOD   = 6
HERO_KB_LIMIT = 200
CARD_KB_LIMIT = 80
EXTS = {".jpg", ".jpeg", ".png"}
# Skip retired hero variants (hero_2.jpg, hero_3.jpg, ...) so we never ship a
# stale hero. The active hero is "hero.jpg"; numbered variants are archives.
SKIP_RE = re.compile(r"^hero_\d", re.IGNORECASE)


def resize_to_max_width(img: Image.Image, max_w: int) -> Image.Image:
    """Downscale to max_w wide, preserving aspect ratio. Never upscale."""
    if img.width <= max_w:
        return img
    new_h = round(img.height * (max_w / img.width))
    return img.resize((max_w, new_h), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sources = sorted(
        p for p in SRC_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in EXTS
    )
    skipped = [p for p in sources if SKIP_RE.match(p.stem)]
    sources = [p for p in sources if not SKIP_RE.match(p.stem)]
    for p in skipped:
        print(f"skip {p.name:<19} (retired hero variant, not converted)")
    if not sources:
        print(f"No .jpg/.jpeg/.png files found in {SRC_DIR}")
        return

    flagged = []

    for src in sources:
        is_hero = "hero" in src.stem.lower()
        max_w = HERO_MAX if is_hero else CARD_MAX
        limit = HERO_KB_LIMIT if is_hero else CARD_KB_LIMIT
        kind = "hero" if is_hero else "card"

        with Image.open(src) as img:
            # Flatten palette / odd modes so WebP saves predictably.
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img = resize_to_max_width(img, max_w)

            out_path = OUT_DIR / (src.stem + ".webp")
            img.save(out_path, "WEBP", quality=QUALITY, method=METHOD)

        kb = out_path.stat().st_size / 1024
        over = kb > limit
        marker = "  <-- OVER LIMIT, re-source" if over else ""
        print(f"{out_path.name:<24} {kb:7.1f} KB  ({kind}, max {max_w}px){marker}")
        if over:
            flagged.append((out_path.name, kb, kind, limit))

    print()
    if flagged:
        print("FLAGGED (exceeds size budget):")
        for name, kb, kind, limit in flagged:
            print(f"  {name}: {kb:.1f} KB > {limit} KB ({kind} limit)")
    else:
        print("All images within budget (hero <= 200 KB, cards <= 80 KB).")


if __name__ == "__main__":
    main()
