# scrapers/image_utils.py
"""
Shared helpers for the taxonomy-image pipeline (fetch + upload).

Two responsibilities, kept in one place so the fetch and upload scripts share
exactly one implementation:

  1. optimize_to_webp() - bake every staged image to the same rules: correct
     EXIF orientation, downscale to <= MAX_WIDTH px wide, convert to WebP, and
     step the quality down until the file is under TARGET_KB (or the quality
     floor). Returns the final byte size.

  2. Attribution - Openverse and Wikimedia images are reusable only WITH
     credit, so every staged image carries its photographer + source URL +
     license in a JSON sidecar written right next to the .webp, and the same
     fields land in the manifest. ImageMeta is the single shape for both.

Pillow is the only third-party dependency here (in requirements.txt).
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

# Optimization budget (matches the task spec: max 1600px wide, WebP, <150 KB).
MAX_WIDTH = 1600
TARGET_KB = 150
TARGET_BYTES = TARGET_KB * 1024
QUALITY_START = 82
QUALITY_FLOOR = 45
QUALITY_STEP = 6

# Licenses we accept from Wikimedia extmetadata (Openverse pre-filters via the
# API's license_type=commercial,modification, so this gate is mainly for the
# Commons fallback). Substring match, case-insensitive, against LicenseShortName.
REUSABLE_LICENSE_HINTS = (
    "cc0", "public domain", "pdm", "cc by", "cc-by",
)
# Reject share-alike-free-but-restrictive or non-derivative variants outright.
BLOCKED_LICENSE_HINTS = ("nd", "no derivative", "nc", "noncommercial", "non-commercial")


@dataclass
class ImageMeta:
    """One staged image's provenance. Required manifest fields per the spec:
    local_path, source_url, author, license, alt_text, search_query. The rest
    (title, provider, license_url, image_url, dimensions, WP ids) are extra
    context for rendering credits and for the idempotent upload step."""

    taxonomy: str = ""
    term: str = ""
    local_path: str = ""
    source_url: str = ""          # human landing page (foreign_landing_url / File: page)
    author: str = ""
    license: str = ""
    alt_text: str = ""
    search_query: str = ""
    title: str = ""
    provider: str = ""            # e.g. "Openverse (flickr)" or "Wikimedia Commons"
    license_url: str = ""
    image_url: str = ""           # the original remote file the bytes came from
    width: int = 0
    height: int = 0
    bytes: int = 0
    wp_media_id: int = 0          # filled by upload_taxonomy_images.py
    wp_term_id: int = 0           # filled by upload_taxonomy_images.py

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Slug - shared by fetch (file naming / manifest keys) and upload (WP lookup)
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Lowercase ASCII slug. Mirrors WordPress sanitize_title closely enough
    for term lookups: spaces/underscores -> hyphens, strip the rest."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


# ---------------------------------------------------------------------------
# WebP optimization
# ---------------------------------------------------------------------------

def optimize_to_webp(
    src: str | Path | bytes,
    dest: str | Path,
    *,
    max_width: int = MAX_WIDTH,
    target_bytes: int = TARGET_BYTES,
) -> tuple[int, int, int]:
    """Resize + convert an image to WebP under the byte budget.

    `src` is a path or raw bytes; `dest` is the .webp output path. Returns
    (width, height, size_bytes) of what was written. Raises if the bytes are
    not a decodable image (caller treats that as "candidate unusable").

    Strategy: fix orientation, flatten alpha onto white (heros/icons sit on the
    dark theme but transparency on photos is just wasted bytes), downscale to
    max_width, then step quality down from QUALITY_START until under budget or
    QUALITY_FLOOR - whichever comes first. We always write the smallest result
    we produced even if it can't quite hit the target, so a stubborn image
    still lands as a valid (slightly larger) WebP rather than failing.
    """
    if isinstance(src, (bytes, bytearray)):
        img = Image.open(io.BytesIO(src))
    else:
        img = Image.open(src)

    img = ImageOps.exif_transpose(img)  # honor camera rotation before measuring

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize((max_width, max(1, round(img.height * ratio))), Image.Resampling.LANCZOS)

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    best: bytes | None = None
    quality = QUALITY_START
    while quality >= QUALITY_FLOOR:
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality, method=6)
        data = buf.getvalue()
        best = data  # keep the most recent (smallest) attempt
        if len(data) <= target_bytes:
            break
        quality -= QUALITY_STEP

    assert best is not None
    dest.write_bytes(best)
    return img.width, img.height, len(best)


# ---------------------------------------------------------------------------
# License gate (Wikimedia fallback) + attribution rendering
# ---------------------------------------------------------------------------

def is_reusable_license(license_short: str) -> bool:
    """True if a Wikimedia LicenseShortName looks freely reusable (incl. for
    commercial use + modification) and is not an NC/ND variant."""
    s = (license_short or "").lower()
    if not s:
        return False
    if any(b in s for b in BLOCKED_LICENSE_HINTS):
        return False
    return any(h in s for h in REUSABLE_LICENSE_HINTS)


def attribution_line(meta: ImageMeta | dict) -> str:
    """One-line credit suitable for a caption: 'Photo by X (CC BY 2.0) via
    Provider'. Built from whatever fields are present."""
    m = meta.to_dict() if isinstance(meta, ImageMeta) else dict(meta)
    author = (m.get("author") or "Unknown").strip()
    lic = (m.get("license") or "").strip()
    provider = (m.get("provider") or "").strip()
    line = f"Photo by {author}"
    if lic:
        line += f" ({lic})"
    if provider:
        line += f" via {provider}"
    return line


# ---------------------------------------------------------------------------
# Sidecar + manifest IO
# ---------------------------------------------------------------------------

def write_sidecar(image_path: str | Path, meta: ImageMeta | dict) -> Path:
    """Write `<image>.json` next to the staged image with its attribution."""
    image_path = Path(image_path)
    data = meta.to_dict() if isinstance(meta, ImageMeta) else dict(meta)
    sidecar = image_path.with_suffix(image_path.suffix + ".json")
    sidecar.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return sidecar


def load_manifest(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
