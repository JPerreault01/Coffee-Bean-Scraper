# scrapers/add_manual_bean_data.py
"""
Manual bean data entry tool — record hand-pulled Amazon ASINs and product
images for beans the automated pipeline could not resolve.

Two modes:

  Single (default):
    python add_manual_bean_data.py
      -> prompts for one bean id, an optional ASIN, and an optional local
         image file path.

  Batch:
    python add_manual_bean_data.py --csv path.csv
      -> reads rows of  id,asin,image_path  (header row optional). Blank
         fields per row are skipped.

What it writes:

  ASIN  -> the matching bean object in scrapers/products.json (amazon_asin).
           Key order and the rest of the file are preserved; only the one
           bean you name is touched.

  Image -> copied to scrapers/.image-cache/{id}.jpg, and the bean is upserted
           into scrapers/.image-cache/manifest.json with the VPS path the
           file will live at after you scp it up. set_featured_images.php
           reads that manifest on the VPS.

This script never runs git and never touches a bean you did not name. If
products.json cannot be parsed it stops before writing anything.

Run locally on Windows:
  python scrapers/add_manual_bean_data.py
  python scrapers/add_manual_bean_data.py --csv new_asins.csv
"""

import argparse
import csv
import difflib
import json
import shutil
import sys
from pathlib import Path

_SCRAPERS_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = _SCRAPERS_DIR / "products.json"
CACHE_DIR = _SCRAPERS_DIR / ".image-cache"
MANIFEST_FILE = CACHE_DIR / "manifest.json"

MIN_IMAGE_BYTES = 10 * 1024  # 10 KB

# Where the cached images live ON THE VPS after you scp them up. This is the
# path that gets written into the manifest, because set_featured_images.php
# calls file_exists() on these values when it runs on the server. It must
# match the scp destination documented in MANUAL_BEAN_DATA.md.
VPS_IMAGE_CACHE = "/opt/scrapers/scrapers/.image-cache"

# JPEG / PNG / GIF / WEBP magic bytes (same check fetch_bean_images.py uses).
_IMAGE_SIGS = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"RIFF")


# ---------------------------------------------------------------------------
# products.json load / save (formatting-preserving)
# ---------------------------------------------------------------------------

def load_products() -> list[dict]:
    """Load products.json. Fail loudly and stop if it cannot be parsed."""
    if not PRODUCTS_FILE.exists():
        sys.exit(f"ERROR: products.json not found at {PRODUCTS_FILE}")
    try:
        with open(PRODUCTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: products.json is not valid JSON ({exc}). Nothing written.")
    if not isinstance(data, list):
        sys.exit("ERROR: products.json is not a JSON array. Nothing written.")
    return data


def save_products(products: list[dict]) -> None:
    """Write products.json back with indent=2, UTF-8, raw non-ASCII, CRLF
    line endings and no trailing newline, matching the committed file so the
    diff stays limited to the values that actually changed."""
    text = json.dumps(products, ensure_ascii=False, indent=2)
    with open(PRODUCTS_FILE, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


def find_bean(products: list[dict], bean_id: str) -> dict | None:
    for p in products:
        if p.get("id") == bean_id:
            return p
    return None


def closest_ids(products: list[dict], bean_id: str, n: int = 5) -> list[str]:
    all_ids = [p.get("id", "") for p in products]
    return difflib.get_close_matches(bean_id, all_ids, n=n, cutoff=0.3)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def valid_asin(asin: str) -> bool:
    return len(asin) == 10 and asin.isalnum()


def is_real_image(path: Path) -> tuple[bool, str]:
    """Return (ok, reason). An image must exist, be >10 KB, and start with a
    known image signature."""
    if not path.exists():
        return False, f"file not found: {path}"
    if not path.is_file():
        return False, f"not a file: {path}"
    size = path.stat().st_size
    if size < MIN_IMAGE_BYTES:
        return False, f"too small ({size} bytes, need >{MIN_IMAGE_BYTES})"
    with open(path, "rb") as f:
        head = f.read(16)
    if head[:4] == b"RIFF" and head[8:12] != b"WEBP":
        return False, "RIFF container is not WEBP"
    if not any(head.startswith(sig) for sig in _IMAGE_SIGS):
        return False, "not a JPEG/PNG/GIF/WEBP file"
    return True, ""


# ---------------------------------------------------------------------------
# Manifest upsert
# ---------------------------------------------------------------------------

def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def save_manifest(manifest: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-bean processing
# ---------------------------------------------------------------------------

class Tally:
    def __init__(self):
        self.asins = 0
        self.images = 0
        self.skipped: list[str] = []  # human-readable reasons


def process_bean(
    products: list[dict],
    manifest: dict,
    bean_id: str,
    asin: str,
    image_path: str,
    tally: Tally,
) -> bool:
    """Apply ASIN and/or image for one bean. Returns True if anything changed.
    Mutates products, manifest, and tally in place."""
    bean = find_bean(products, bean_id)
    if bean is None:
        matches = closest_ids(products, bean_id)
        hint = ("  Closest ids: " + ", ".join(matches)) if matches else "  No similar ids found."
        print(f"SKIP  {bean_id} — not found in products.json")
        print(hint)
        tally.skipped.append(f"{bean_id}: id not in products.json")
        return False

    changed = False
    changes: list[str] = []

    # --- ASIN ---
    asin = (asin or "").strip()
    if asin:
        if valid_asin(asin):
            old = bean.get("amazon_asin")
            bean["amazon_asin"] = asin
            tally.asins += 1
            changed = True
            if old and old != asin:
                changes.append(f"ASIN {old} -> {asin}")
            else:
                changes.append(f"ASIN set to {asin}")
        else:
            print(f"SKIP ASIN for {bean_id} — '{asin}' is not a 10-char alphanumeric ASIN")
            tally.skipped.append(f"{bean_id}: bad ASIN '{asin}'")

    # --- Image ---
    image_path = (image_path or "").strip().strip('"')
    if image_path:
        src = Path(image_path)
        ok, reason = is_real_image(src)
        if ok:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            dest = CACHE_DIR / f"{bean_id}.jpg"
            shutil.copyfile(src, dest)
            manifest[bean_id] = f"{VPS_IMAGE_CACHE}/{bean_id}.jpg"
            tally.images += 1
            changed = True
            changes.append(f"image cached -> {dest.name} (manifest: {manifest[bean_id]})")
        else:
            print(f"SKIP image for {bean_id} — {reason}")
            tally.skipped.append(f"{bean_id}: image rejected ({reason})")

    if changed:
        print(f"OK    {bean_id}")
        for c in changes:
            print(f"        {c}")
    elif not asin and not image_path:
        print(f"SKIP  {bean_id} — nothing to do (no ASIN, no image)")

    return changed


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_single(products: list[dict], manifest: dict, tally: Tally) -> bool:
    print("Manual bean data entry — single bean.")
    print("Leave a field blank to skip it.\n")

    bean_id = input("Bean id: ").strip()
    if not bean_id:
        sys.exit("No bean id entered. Nothing changed.")

    if find_bean(products, bean_id) is None:
        matches = closest_ids(products, bean_id)
        if matches:
            print(f"\nNo bean with id '{bean_id}'. Closest matches:")
            for m in matches:
                print(f"  {m}")
        else:
            print(f"\nNo bean with id '{bean_id}', and no similar ids found.")
        sys.exit(1)

    asin = input("Amazon ASIN (10-char, optional): ").strip()
    image_path = input("Local image file path (optional): ").strip()
    print()

    return process_bean(products, manifest, bean_id, asin, image_path, tally)


def run_csv(csv_path: str, products: list[dict], manifest: dict, tally: Tally) -> bool:
    path = Path(csv_path)
    if not path.exists():
        sys.exit(f"ERROR: CSV not found at {path}")

    any_change = False
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for lineno, row in enumerate(reader, start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            cells = [c.strip() for c in row]
            # Skip an optional header row.
            if lineno == 1 and cells[0].lower() == "id":
                continue
            bean_id = cells[0] if len(cells) > 0 else ""
            asin = cells[1] if len(cells) > 1 else ""
            image_path = cells[2] if len(cells) > 2 else ""
            if not bean_id:
                print(f"SKIP  row {lineno} — no id")
                tally.skipped.append(f"row {lineno}: no id")
                continue
            if process_bean(products, manifest, bean_id, asin, image_path, tally):
                any_change = True
    return any_change


# ---------------------------------------------------------------------------
# Next-steps / summary output
# ---------------------------------------------------------------------------

def print_summary(tally: Tally, wrote_products: bool, wrote_images: bool) -> None:
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  ASINs written:  {tally.asins}")
    print(f"  Images cached:  {tally.images}")
    print(f"  Skipped:        {len(tally.skipped)}")
    for reason in tally.skipped:
        print(f"    - {reason}")

    if not wrote_products and not wrote_images:
        print("\nNothing changed. No next steps.")
        return

    print("\n" + "=" * 60)
    print("NEXT STEPS — get this live (run these yourself)")
    print("=" * 60)

    step = 1
    if wrote_products:
        print(f"\n{step}. Commit and push the products.json change:")
        print("     git add scrapers/products.json")
        print('     git commit -m "data: add manual Amazon ASINs for unresolved beans"')
        print("     git push")
        step += 1

        print(f"\n{step}. On the VPS, pull the updated products.json:")
        print("     ssh cbi-prod")
        print("     cd /opt/scrapers/scrapers")
        print("     wget -O products.json \\")
        print("       https://raw.githubusercontent.com/JPerreault01/Coffee-Bean-Scraper/main/scrapers/products.json")
        step += 1

    if wrote_images:
        print(f"\n{step}. From Windows, scp the new image(s) AND the manifest to the VPS")
        print("   (.image-cache is gitignored, so images do NOT travel via git):")
        print("     scp scrapers/.image-cache/manifest.json \\")
        print("       cbi-prod:/opt/scrapers/scrapers/.image-cache/manifest.json")
        print("     scp scrapers/.image-cache/<id>.jpg \\")
        print("       cbi-prod:/opt/scrapers/scrapers/.image-cache/<id>.jpg")
        step += 1

    if wrote_products:
        print(f"\n{step}. On the VPS, populate the ACF ASIN + affiliate URL on the")
        print("   already-created beans (create_beans.php SKIPS existing beans, so it")
        print("   will NOT do this for you):")
        print("     cd /var/www/coffeebeans")
        print("     wp eval-file /opt/scrapers/scrapers/update_bean_asins.php --allow-root")
        step += 1

    if wrote_images:
        print(f"\n{step}. On the VPS, set the featured images from the manifest:")
        print("     cd /var/www/coffeebeans")
        print("     wp eval-file /opt/scrapers/scrapers/set_featured_images.php \\")
        print("       /opt/scrapers/scrapers/.image-cache/manifest.json --allow-root")
        step += 1

    print(f"\n{step}. Flush the cache and review the draft beans before publishing:")
    print("     wp cache flush --allow-root")
    print("\nFull walkthrough: scrapers/MANUAL_BEAN_DATA.md")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record manual Amazon ASINs and images for unresolved beans."
    )
    parser.add_argument("--csv", help="Batch mode: CSV file with rows id,asin,image_path")
    args = parser.parse_args()

    products = load_products()
    manifest = load_manifest()
    tally = Tally()

    if args.csv:
        changed = run_csv(args.csv, products, manifest, tally)
    else:
        changed = run_single(products, manifest, tally)

    wrote_products = tally.asins > 0
    wrote_images = tally.images > 0

    if wrote_products:
        save_products(products)
    if wrote_images:
        save_manifest(manifest)

    print_summary(tally, wrote_products, wrote_images)


if __name__ == "__main__":
    main()
