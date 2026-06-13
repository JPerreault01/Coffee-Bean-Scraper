# scrapers/fetch_taxonomy_images.py
"""
Source legitimately reusable CONCEPTUAL imagery for taxonomy terms.

Scope: origin / brew-method / flavor-note / process-method / roast-level.
NOT roaster - commercial bean bags keep their affiliate-feed product photos;
Openverse/Wikimedia coverage for specific bags is thin and off-brand. This
pipeline is only for the conceptual art: brewing gear, origin landscapes, the
fruit/chocolate/nut macros behind a flavor note, drying beds, roast color.

Source order (best license clarity first):
  1. Openverse API  - api.openverse.org, no key, pre-filtered to
     license_type=commercial,modification.
  2. Wikimedia Commons - MediaWiki API, no key, license gated locally to
     CC0 / public-domain / CC BY(-SA) and never NC/ND.

For each term we map to a deliberate search query (a flavor note resolves to an
APPETIZING FOOD MACRO, not the abstract word), pick the top usable candidate,
download it, optimize to WebP (<=1600px, <150 KB) via image_utils, and record
provenance to:
    data/image_staging/{taxonomy}__{slug}.webp        (the image)
    data/image_staging/{taxonomy}__{slug}.webp.json    (attribution sidecar)
    data/image_manifest.json                           (keyed {taxonomy}:{term})

Usage:
    # Review the query mappings + top candidate per term, download nothing:
    python scrapers/fetch_taxonomy_images.py --all --dry-run
    python scrapers/fetch_taxonomy_images.py --taxonomy flavor-note --term blueberry --dry-run

    # Real run (single term, a whole taxonomy, or the full seed set):
    python scrapers/fetch_taxonomy_images.py --taxonomy brew-method --term french-press
    python scrapers/fetch_taxonomy_images.py --taxonomy origin
    python scrapers/fetch_taxonomy_images.py --all

    --force   re-fetch terms already present in the manifest.

Dependencies: requests, Pillow (both in requirements.txt).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

import requests

_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent
sys.path.insert(0, str(_REPO_ROOT))

from scrapers.image_utils import (  # noqa: E402
    ImageMeta,
    is_reusable_license,
    load_manifest,
    optimize_to_webp,
    save_manifest,
    slugify,
    write_sidecar,
)

STAGING_DIR = _REPO_ROOT / "data" / "image_staging"
MANIFEST_FILE = _REPO_ROOT / "data" / "image_manifest.json"

TAXONOMIES = ("origin", "brew-method", "flavor-note", "process-method", "roast-level")

OPENVERSE_ENDPOINT = "https://api.openverse.org/v1/images/"
WIKIMEDIA_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
# Descriptive UA for Wikimedia (their API policy asks for one + a contact).
USER_AGENT = "coffeebeanindex-taxonomy-images/1.0 (+https://coffeebeanindex.com)"
# Browser-ish UA tried only against Openverse (it sits behind Cloudflare).
OPENVERSE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Per-run state: once Openverse answers with a Cloudflare bot challenge we stop
# hammering it for the rest of the run and fall straight through to Wikimedia,
# logging the reason exactly once instead of on every term.
_RUN_STATE = {"openverse_blocked": False}

MIN_IMAGE_BYTES = 8 * 1024     # ignore tiny/placeholder downloads
MIN_DIMENSION = 500            # a hero needs at least this on the short side

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ===========================================================================
# Term -> search-query mapping (the part worth reviewing in --dry-run)
# ===========================================================================
#
# Explicit overrides win. They exist because the literal term is a bad query:
# "blueberry" alone returns logos and candy; "fresh blueberries macro" returns
# the appetizing fruit shot we actually want behind the flavor note.

QUERY_OVERRIDES: dict[tuple[str, str], str] = {
    # --- flavor-note: appetizing food macros, never the abstract word ---
    ("flavor-note", "blueberry"):      "fresh blueberries macro",
    ("flavor-note", "blackberry"):     "fresh blackberries macro",
    ("flavor-note", "berry"):          "mixed fresh berries macro",
    ("flavor-note", "cherry"):         "fresh red cherries macro",
    ("flavor-note", "strawberry"):     "fresh strawberries macro",
    ("flavor-note", "raspberry"):      "fresh raspberries macro",
    ("flavor-note", "chocolate"):      "dark chocolate pieces macro",
    ("flavor-note", "dark-chocolate"): "dark chocolate squares macro",
    ("flavor-note", "milk-chocolate"): "milk chocolate pieces macro",
    ("flavor-note", "cocoa"):          "cocoa powder and nibs macro",
    ("flavor-note", "caramel"):        "caramel sauce dripping close up",
    ("flavor-note", "toffee"):         "toffee pieces macro",
    ("flavor-note", "honey"):          "honey dripping from dipper macro",
    ("flavor-note", "brown-sugar"):    "brown sugar pile macro",
    ("flavor-note", "maple"):          "maple syrup pouring macro",
    ("flavor-note", "vanilla"):        "vanilla beans and pods macro",
    ("flavor-note", "nutty"):          "roasted hazelnuts macro",
    ("flavor-note", "hazelnut"):       "roasted hazelnuts macro",
    ("flavor-note", "almond"):         "roasted almonds macro",
    ("flavor-note", "walnut"):         "shelled walnuts macro",
    ("flavor-note", "peanut"):         "roasted peanuts macro",
    ("flavor-note", "citrus"):         "fresh citrus slices macro",
    ("flavor-note", "lemon"):          "fresh lemon slices macro",
    ("flavor-note", "orange"):         "fresh orange slices macro",
    ("flavor-note", "grapefruit"):     "fresh grapefruit slices macro",
    ("flavor-note", "lime"):           "fresh lime slices macro",
    ("flavor-note", "floral"):         "jasmine flowers close up",
    ("flavor-note", "jasmine"):        "jasmine flowers close up",
    ("flavor-note", "rose"):           "rose petals close up",
    ("flavor-note", "stone-fruit"):    "ripe peaches and apricots macro",
    ("flavor-note", "peach"):          "fresh peach halves macro",
    ("flavor-note", "apricot"):        "fresh apricots macro",
    ("flavor-note", "plum"):           "fresh plums macro",
    ("flavor-note", "apple"):          "fresh red apple slices macro",
    ("flavor-note", "green-apple"):    "fresh green apple slices macro",
    ("flavor-note", "tropical"):       "tropical fruit mango pineapple macro",
    ("flavor-note", "mango"):          "fresh mango slices macro",
    ("flavor-note", "pineapple"):      "fresh pineapple slices macro",
    ("flavor-note", "winey"):          "red wine glass swirl macro",
    ("flavor-note", "wine"):           "red wine glass swirl macro",
    ("flavor-note", "molasses"):       "molasses pouring macro",
    ("flavor-note", "spice"):          "whole spices cinnamon star anise macro",
    ("flavor-note", "cinnamon"):       "cinnamon sticks macro",
    ("flavor-note", "clove"):          "whole cloves macro",
    ("flavor-note", "earthy"):         "forest floor moss and earth close up",
    ("flavor-note", "smoky"):          "smoke wisps dark background",
    ("flavor-note", "tobacco"):        "dried tobacco leaves macro",
    ("flavor-note", "herbal"):         "fresh green herbs macro",
    ("flavor-note", "black-tea"):      "black tea leaves and cup macro",
    ("flavor-note", "bergamot"):       "bergamot citrus fruit macro",
    ("flavor-note", "coconut"):        "fresh coconut halves macro",
    ("flavor-note", "graham-cracker"): "graham crackers stack macro",
    ("flavor-note", "malt"):           "malted barley grains macro",

    # --- brew-method: the gear actually brewing ---
    ("brew-method", "espresso"):     "espresso shot pulling from machine",
    ("brew-method", "french-press"): "french press coffee brewing",
    ("brew-method", "pour-over"):    "pour over coffee v60 brewing",
    ("brew-method", "drip"):         "drip coffee maker pouring into carafe",
    ("brew-method", "cold-brew"):    "cold brew coffee in glass",
    ("brew-method", "aeropress"):    "aeropress coffee brewing",
    ("brew-method", "moka-pot"):     "moka pot stovetop espresso brewing",
    ("brew-method", "chemex"):       "chemex pour over coffee brewing",
    ("brew-method", "percolator"):   "stovetop coffee percolator",
    ("brew-method", "siphon"):       "siphon vacuum coffee brewing",
    ("brew-method", "turkish"):      "turkish coffee in cezve copper pot",
    ("brew-method", "espresso-machine"): "espresso machine pulling shot",

    # --- origin: farm / landscape, not a flag ---
    ("origin", "ethiopia"):    "ethiopia coffee plantation highlands",
    ("origin", "colombia"):    "colombia coffee plantation mountains",
    ("origin", "brazil"):      "brazil coffee plantation rows",
    ("origin", "kenya"):       "kenya coffee plantation",
    ("origin", "guatemala"):   "guatemala coffee plantation volcano",
    ("origin", "costa-rica"):  "costa rica coffee plantation",
    ("origin", "sumatra"):     "sumatra coffee plantation indonesia",
    ("origin", "indonesia"):   "indonesia coffee plantation terraces",
    ("origin", "honduras"):    "honduras coffee plantation hills",
    ("origin", "peru"):        "peru coffee plantation andes",
    ("origin", "mexico"):      "mexico coffee plantation chiapas",
    ("origin", "yemen"):       "yemen coffee terraces mountains",
    ("origin", "rwanda"):      "rwanda coffee plantation hills",
    ("origin", "burundi"):     "burundi coffee plantation",
    ("origin", "panama"):      "panama coffee plantation boquete",
    ("origin", "el-salvador"): "el salvador coffee plantation",
    ("origin", "nicaragua"):   "nicaragua coffee plantation",
    ("origin", "tanzania"):    "tanzania coffee plantation kilimanjaro",
    ("origin", "uganda"):      "uganda coffee plantation",
    ("origin", "india"):       "india coffee plantation western ghats",
    ("origin", "vietnam"):     "vietnam coffee plantation terraces",
    ("origin", "jamaica"):     "jamaica blue mountain coffee plantation",
    ("origin", "papua-new-guinea"): "papua new guinea coffee plantation",

    # --- process-method ---
    ("process-method", "washed"):    "coffee cherries washing station water channel",
    ("process-method", "natural"):   "coffee cherries drying on raised beds sun",
    ("process-method", "honey"):     "coffee cherries drying honey process raised beds",
    ("process-method", "anaerobic"): "coffee fermentation stainless tanks",
    ("process-method", "wet-hulled"): "wet hulled coffee beans drying",
    ("process-method", "semi-washed"): "coffee parchment drying patio",
    ("process-method", "pulped-natural"): "coffee cherries drying patio",

    # --- roast-level: bean color macro ---
    ("roast-level", "light"):       "light roast coffee beans macro",
    ("roast-level", "light-medium"): "light medium roast coffee beans macro",
    ("roast-level", "medium"):      "medium roast coffee beans macro",
    ("roast-level", "medium-dark"): "medium dark roast coffee beans macro",
    ("roast-level", "dark"):        "dark roast coffee beans macro oily",
    ("roast-level", "espresso"):    "dark espresso roast coffee beans macro",
    ("roast-level", "french"):      "french roast dark coffee beans macro",
    ("roast-level", "italian"):     "italian roast very dark coffee beans macro",
    ("roast-level", "blonde"):      "blonde light roast coffee beans macro",
}

# Per-taxonomy fallback templates for any term without an explicit override.
QUERY_TEMPLATES: dict[str, str] = {
    "flavor-note":    "fresh {term} macro food photography",
    "brew-method":    "{term} coffee brewing",
    "origin":         "{term} coffee plantation landscape",
    "process-method": "coffee {term} process drying",
    "roast-level":    "{term} roast coffee beans macro",
}

# Descriptive alt-text templates (SEO + screen readers). {term} is title-cased.
ALT_TEMPLATES: dict[str, str] = {
    "flavor-note":    "Close-up of {term}, the flavor note in this coffee",
    "brew-method":    "{term} coffee brewing method",
    "origin":         "Coffee-growing landscape in {term}",
    "process-method": "Coffee {term} processing",
    "roast-level":    "{term} roast coffee beans",
}

# Seed terms used by --all / --taxonomy (no --term). Curated to the catalog's
# common terms; expand freely. Roaster is intentionally absent (see module doc).
SEED_TERMS: dict[str, list[str]] = {
    "origin": [
        "ethiopia", "colombia", "brazil", "kenya", "guatemala", "costa-rica",
        "sumatra", "indonesia", "honduras", "peru", "mexico", "yemen",
        "rwanda", "panama", "el-salvador", "nicaragua", "tanzania", "india",
    ],
    "brew-method": [
        "espresso", "french-press", "pour-over", "drip", "cold-brew",
        "aeropress", "moka-pot", "chemex",
    ],
    "flavor-note": [
        "blueberry", "chocolate", "caramel", "citrus", "nutty", "floral",
        "berry", "stone-fruit", "vanilla", "honey", "cherry", "hazelnut",
        "spice", "tropical", "winey", "brown-sugar", "earthy", "lemon",
    ],
    "process-method": [
        "washed", "natural", "honey", "anaerobic", "wet-hulled",
    ],
    "roast-level": [
        "light", "medium", "medium-dark", "dark", "espresso",
    ],
}


def build_query(taxonomy: str, term: str) -> str:
    """The search string for a (taxonomy, term). Explicit override first, then
    the per-taxonomy template. Term is normalized to a slug for the lookup so
    'French Press' and 'french-press' map identically."""
    key = (taxonomy, slugify(term))
    if key in QUERY_OVERRIDES:
        return QUERY_OVERRIDES[key]
    pretty = slugify(term).replace("-", " ")
    template = QUERY_TEMPLATES.get(taxonomy, "{term} coffee")
    return template.format(term=pretty)


def build_alt_text(taxonomy: str, term: str) -> str:
    pretty = slugify(term).replace("-", " ").title()
    template = ALT_TEMPLATES.get(taxonomy, "{term} coffee")
    return template.format(term=pretty)


# ===========================================================================
# Candidate resolution - Openverse, then Wikimedia
# ===========================================================================

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def openverse_candidate(session: requests.Session, query: str) -> ImageMeta | None:
    """Top usable Openverse image for a query, or None. The API already filters
    to commercially reusable + modifiable; we just take the first landscape-ish
    result that carries a direct image URL."""
    params = {
        "q": query,
        "license_type": "commercial,modification",
        "page_size": 8,
        "mature": "false",
        "aspect_ratio": "wide",
    }
    resp = session.get(OPENVERSE_ENDPOINT, params=params,
                       headers={"User-Agent": OPENVERSE_UA}, timeout=25)
    if resp.status_code != 200:
        # Cloudflare bot challenge (common from datacenter IPs) -> stop trying
        # Openverse this run; Wikimedia carries the rest.
        body = resp.text[:400].lower()
        if resp.status_code in (401, 403, 503) and ("just a moment" in body or "cloudflare" in body or "challenge" in body):
            _RUN_STATE["openverse_blocked"] = True
            log.warning("Openverse unreachable (HTTP %s, Cloudflare challenge) - "
                        "falling back to Wikimedia for the rest of this run.", resp.status_code)
        else:
            log.debug("Openverse HTTP %s for %r", resp.status_code, query)
        return None
    results = (resp.json() or {}).get("results") or []
    for r in results:
        image_url = r.get("url")
        if not image_url:
            continue
        source = r.get("source") or r.get("provider") or "openverse"
        return ImageMeta(
            source_url=r.get("foreign_landing_url") or image_url,
            author=(r.get("creator") or "Unknown").strip(),
            license=_format_license(r.get("license"), r.get("license_version")),
            title=(r.get("title") or "").strip(),
            provider=f"Openverse ({source})",
            license_url=r.get("license_url") or "",
            image_url=image_url,
            width=int(r.get("width") or 0),
            height=int(r.get("height") or 0),
        )
    return None


def _format_license(code: str | None, version: str | None) -> str:
    code = (code or "").strip().lower()
    if not code:
        return ""
    if code in ("cc0", "pdm"):
        return code.upper() if code == "cc0" else "Public Domain"
    label = "CC " + code.upper().replace("-", "-")
    return f"{label} {version}".strip() if version else label


# Only true raster photos. Commons renders .djvu/.pdf/.tif (old book & document
# scans) to a JPEG thumbnail whose source mime is still image/vnd.djvu etc., so
# an "image/*" check lets 1900s book pages through. An allowlist kills them.
_WIKIMEDIA_PHOTO_MIMES = ("image/jpeg", "image/png", "image/webp")

# Generic words carry no subject signal, so they don't count toward relevance.
_RELEVANCE_STOPWORDS = {
    "fresh", "macro", "close", "up", "and", "the", "of", "in", "on", "from",
    "into", "with", "photo", "photography", "view", "for",
}


def _relevance_tokens(term: str, query: str) -> set[str]:
    """4-char prefixes of the meaningful words in the term + query. Used to
    require a Wikimedia title to actually be about the subject (a naive prefix
    handles cherry/cherries, blueberry/blueberries without a real stemmer)."""
    words = re.findall(r"[a-z0-9]+", f"{term} {query}".lower())
    return {w[:4] for w in words if len(w) >= 4 and w not in _RELEVANCE_STOPWORDS}


def _title_relevant(title: str, tokens: set[str]) -> bool:
    """True if any subject prefix appears in the title. Empty token set (very
    short term) is treated as relevant so we don't reject everything."""
    if not tokens:
        return True
    low = title.lower()
    return any(tok in low for tok in tokens)


def wikimedia_candidate(session: requests.Session, query: str, term: str = "") -> ImageMeta | None:
    """Top freely-licensed Commons photo for a query, or None. Gated to CC0 /
    public-domain / CC BY(-SA), never NC/ND, to real photo formats, and - to
    fight Wikimedia's weak relevance on food terms (it once returned a moth for
    'chocolate') - preferring a result whose title contains the term before
    settling for the first otherwise-valid one."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,            # File: namespace
        "gsrlimit": 12,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size",
        "iiurlwidth": 1600,
    }
    resp = session.get(WIKIMEDIA_ENDPOINT, params=params, timeout=25)
    if resp.status_code != 200:
        return None
    pages = ((resp.json() or {}).get("query") or {}).get("pages") or {}
    # Commons returns pages keyed by id; sort by the search index when present.
    candidates = sorted(pages.values(), key=lambda p: p.get("index", 999))
    tokens = _relevance_tokens(term, query)
    primary = slugify(term).split("-")[0] if term else ""

    valid: list[tuple[bool, ImageMeta]] = []
    for page in candidates:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        if (info.get("mime") or "").lower() not in _WIKIMEDIA_PHOTO_MIMES:
            continue
        if int(info.get("width") or 0) < MIN_DIMENSION:
            continue
        meta = info.get("extmetadata") or {}
        lic_short = _ext(meta, "LicenseShortName")
        if not is_reusable_license(lic_short):
            continue
        title = page.get("title", "").replace("File:", "").strip()
        # Subject-relevance gate: the title must be about the thing we searched
        # for. Kills off-topic license-valid noise (e.g. a moth for "chocolate").
        if not _title_relevant(title, tokens):
            continue
        cand = ImageMeta(
            source_url=info.get("descriptionurl") or info.get("url") or "",
            author=_strip_html(_ext(meta, "Artist")) or "Unknown",
            license=lic_short,
            title=title,
            provider="Wikimedia Commons",
            license_url=_ext(meta, "LicenseUrl"),
            image_url=info.get("thumburl") or info.get("url") or "",
            width=int(info.get("thumbwidth") or info.get("width") or 0),
            height=int(info.get("thumbheight") or info.get("height") or 0),
        )
        title_match = bool(primary) and primary in title.lower()
        valid.append((title_match, cand))

    if not valid:
        return None
    # Prefer the first title-matching candidate; otherwise the first valid one.
    for matched, cand in valid:
        if matched:
            return cand
    return valid[0][1]


def _ext(meta: dict, key: str) -> str:
    node = meta.get(key)
    if isinstance(node, dict):
        return str(node.get("value", "")).strip()
    return ""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def resolve_candidate(session: requests.Session, taxonomy: str, term: str, query: str) -> ImageMeta | None:
    """Openverse first (clearest licensing), Wikimedia fallback. Fills the
    taxonomy/term/search_query/alt_text fields on whatever is found."""
    cand = None
    if not _RUN_STATE["openverse_blocked"]:
        try:
            cand = openverse_candidate(session, query)
        except requests.RequestException as exc:
            log.warning("Openverse error for %r: %s", query, exc)
    if cand is None:
        try:
            cand = wikimedia_candidate(session, query, term)
        except requests.RequestException as exc:
            log.warning("Wikimedia error for %r: %s", query, exc)
    if cand is not None:
        cand.taxonomy = taxonomy
        cand.term = term
        cand.search_query = query
        cand.alt_text = build_alt_text(taxonomy, term)
    return cand


# ===========================================================================
# Download + stage
# ===========================================================================

def stage_candidate(session: requests.Session, cand: ImageMeta) -> bool:
    """Download the candidate, optimize to WebP, write image + sidecar. Returns
    True on success. The manifest is updated by the caller."""
    try:
        resp = session.get(cand.image_url, timeout=30)
        resp.raise_for_status()
        raw = resp.content
    except requests.RequestException as exc:
        log.warning("Download failed (%s): %s", cand.image_url, exc)
        return False
    if len(raw) < MIN_IMAGE_BYTES:
        log.warning("Too small (%d bytes): %s", len(raw), cand.image_url)
        return False

    slug = slugify(cand.term)
    dest = STAGING_DIR / f"{cand.taxonomy}__{slug}.webp"
    try:
        w, h, size = optimize_to_webp(raw, dest)
    except Exception as exc:  # Pillow can't decode -> candidate unusable
        log.warning("Optimize failed for %s:%s - %s", cand.taxonomy, cand.term, exc)
        return False

    cand.local_path = str(dest)
    cand.width, cand.height, cand.bytes = w, h, size
    write_sidecar(dest, cand)
    log.info("STAGED %s:%s -> %s (%dx%d, %d KB) [%s]",
             cand.taxonomy, cand.term, dest.name, w, h, size // 1024, cand.provider)
    return True


# ===========================================================================
# Orchestration
# ===========================================================================

def _term_jobs(args) -> list[tuple[str, str]]:
    """(taxonomy, term) pairs to process from the CLI flags."""
    jobs: list[tuple[str, str]] = []
    if args.all:
        for tax in TAXONOMIES:
            jobs += [(tax, t) for t in SEED_TERMS.get(tax, [])]
        return jobs
    if not args.taxonomy:
        log.error("Pass --taxonomy (with optional --term) or --all.")
        sys.exit(2)
    if args.taxonomy not in TAXONOMIES:
        log.error("Unknown taxonomy %r. One of: %s", args.taxonomy, ", ".join(TAXONOMIES))
        sys.exit(2)
    if args.term:
        jobs.append((args.taxonomy, args.term))
    else:
        jobs += [(args.taxonomy, t) for t in SEED_TERMS.get(args.taxonomy, [])]
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Source reusable taxonomy imagery (Openverse + Wikimedia).")
    parser.add_argument("--taxonomy", help="one of: " + ", ".join(TAXONOMIES))
    parser.add_argument("--term", help="single term name (omit to run the taxonomy's seed list)")
    parser.add_argument("--all", action="store_true", help="run every seed term across all taxonomies")
    parser.add_argument("--dry-run", action="store_true", help="resolve + print top candidate, download nothing")
    parser.add_argument("--force", action="store_true", help="re-fetch terms already in the manifest")
    args = parser.parse_args()

    jobs = _term_jobs(args)
    session = _session()
    manifest = load_manifest(MANIFEST_FILE)
    if not args.dry_run:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)

    matched: list[str] = []
    unmatched: list[str] = []
    skipped: list[str] = []

    for taxonomy, term in jobs:
        key = f"{taxonomy}:{term}"
        query = build_query(taxonomy, term)

        if not args.dry_run and not args.force:
            existing = manifest.get(key)
            if existing and existing.get("local_path") and Path(existing["local_path"]).exists():
                log.info("SKIP  %s - already staged (%s)", key, Path(existing["local_path"]).name)
                skipped.append(key)
                continue

        cand = resolve_candidate(session, taxonomy, term, query)

        if args.dry_run:
            if cand:
                log.info("MATCH %-28s q=%-44r -> %s | %s | %s",
                         key, query, cand.provider, cand.license or "?", cand.source_url)
                matched.append(key)
            else:
                log.info("NONE  %-28s q=%r  (no usable candidate)", key, query)
                unmatched.append(key)
            time.sleep(0.6)  # be polite to the keyless public APIs
            continue

        if cand and stage_candidate(session, cand):
            manifest[key] = cand.to_dict()
            save_manifest(MANIFEST_FILE, manifest)  # checkpoint after each success
            matched.append(key)
        else:
            log.warning("NO IMAGE for %s (query: %r) - handle manually", key, query)
            unmatched.append(key)
        time.sleep(0.6)

    # ---- Summary -----------------------------------------------------------
    log.info("=" * 66)
    mode = "DRY RUN" if args.dry_run else "FETCH"
    log.info("%s complete - %d matched, %d no-image, %d skipped (already staged)",
             mode, len(matched), len(unmatched), len(skipped))
    if unmatched:
        log.info("No good image (source manually): %s", ", ".join(unmatched))
    if not args.dry_run:
        log.info("Manifest: %s", MANIFEST_FILE)
        log.info("Staging:  %s", STAGING_DIR)


if __name__ == "__main__":
    main()
