# scrapers/waytocoffee_scraper.py
"""
Scraper for thewaytocoffee.com/beans
=====================================
Two-phase HTML scrape:
  1. Listing pages  → collect coffee names + detail URLs
  2. Detail pages   → scrape origin, flavor notes, roast, processing, typology,
                      roaster name, roaster buy URL, and description

URL flow:
  Listing: https://www.thewaytocoffee.com/beans/
  Detail:  https://www.thewaytocoffee.com/beans/costa-rica-don-claudio-natural/
  Buy URL: https://blinddogcoffee.com/products/costa-rica-don-claudio-natural-...

roaster_url captures the first external non-social link on the detail page —
the actual roaster's product page. NOT the internal /roasters/ profile page.

Resumable: re-running skips already-scraped URLs automatically.

Requirements:
    pip install playwright beautifulsoup4 tqdm
    python -m playwright install chromium

Usage:
    python scrapers/waytocoffee_scraper.py              # 5 pages (test ~125 beans)
    python scrapers/waytocoffee_scraper.py --pages 20
    python scrapers/waytocoffee_scraper.py --all        # full run overnight

After scraping:
    python scrapers/reference_db.py load data/waytocoffee.json
"""

import argparse
import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Browser, Page, sync_playwright
from tqdm import tqdm

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
DATA_DIR    = REPO_ROOT / "data"
STUBS_FILE  = DATA_DIR / "waytocoffee_stubs.json"
OUTPUT_FILE = DATA_DIR / "waytocoffee.json"

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Coffee:
    name:         str
    url:          str
    roaster:      str       = ""
    roaster_url:  str       = ""
    description:  str       = ""
    origins:      list[str] = field(default_factory=list)
    flavor_notes: list[str] = field(default_factory=list)
    roast_level:  str       = ""
    processing:   list[str] = field(default_factory=list)
    typology:     list[str] = field(default_factory=list)


# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL  = "https://www.thewaytocoffee.com"
BEANS_URL = f"{BASE_URL}/beans/"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

FIELD_LABELS = {
    "origin":        "origins",
    "flavor notes":  "flavor_notes",
    "flavour notes": "flavor_notes",
    "roast level":   "roast_level",
    "processing":    "processing",
    "typology":      "typology",
}

# Domains to skip when looking for the roaster buy link
EXCLUDED_DOMAINS = {
    "thewaytocoffee.com", "amazon.com", "amazon.co.uk", "amazon.de",
    "amazon.fr", "amazon.es", "amzn.to", "facebook.com", "instagram.com",
    "pinterest.com", "twitter.com", "x.com", "youtube.com", "linkedin.com",
    "tiktok.com", "google.com",
}

# ── Browser helpers ───────────────────────────────────────────────────────────

def make_page(browser: Browser) -> Page:
    ctx = browser.new_context(
        user_agent=UA,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()
    page.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("image", "font", "media")
        else route.continue_(),
    )
    return page


def fetch_html(page: Page, url: str, wait_selector: str,
               retries: int = 3, delay: float = 2.0) -> str:
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_selector(wait_selector, timeout=15_000)
            return page.content()
        except Exception as exc:
            log.warning("Attempt %d/%d failed (%s): %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(delay * attempt)
    raise RuntimeError(f"Could not load {url} after {retries} attempts")


# ── Text helpers ──────────────────────────────────────────────────────────────

def _text(tag: Optional[Tag]) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _clean(s: str) -> str:
    # NFKC converts non-breaking spaces, em-dashes, etc. to plain equivalents
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", " ", s).strip()


def _split(text: str) -> list[str]:
    parts = re.split(r"[,\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def _dd_values(dd: Tag, max_items: int = 12) -> list[str]:
    """
    Extract field values from a <dd> tag.

    On some pages the <dd> element contains the entire rest of the page DOM,
    so stop-token text matching is unreliable. Instead we:
      1. Try Layout A: direct child elements — stop at first long or junk-looking item
      2. Fall back to Layout B: text blob split on commas/newlines
    Both paths are capped at max_items and drop any item > 80 chars.
    For typology, use _filter_typology() after this call for stricter filtering.
    """
    STOP_PHRASES = (
        "buy from roaster", "view all coffees", "similar coffee",
        "privacy policy", "cookie policy", "copyright", "all rights reserved",
        "affiliate", "amazon services",
    )

    def is_junk(text: str) -> bool:
        if len(text) > 80:
            return True
        low = text.lower()
        return any(phrase in low for phrase in STOP_PHRASES)

    # Layout A: per-child-element
    child_tags = [
        c for c in dd.children
        if hasattr(c, "get_text") and c.get_text(strip=True)
        and c.name in ("span", "li", "a", "p", "div", "strong", "em")
    ]
    if child_tags:
        values: list[str] = []
        for c in child_tags:
            text = _clean(c.get_text(" ", strip=True))
            if is_junk(text):
                break
            if text:
                values.append(text)
            if len(values) >= max_items:
                break
        if values:
            return values

    # Layout B: text blob
    raw = _split(_clean(dd.get_text(" ", strip=True)))
    values = []
    for v in raw:
        if is_junk(v):
            break
        values.append(v)
        if len(values) >= max_items:
            break
    return values


def _filter_typology(values: list[str]) -> list[str]:
    """
    Post-filter typology/varietal values.

    Valid entries are short botanical names: Arabica, Geisha, Caturra, Pink Bourbon, etc.
    They are:
      - <= 40 characters
      - Contain only letters, digits, spaces, hyphens, apostrophes, accented chars
      - No more than 5 words
      - Don't look like sentences or URLs

    Anything that fails these rules — or any subsequent items once we've seen
    one failure — is dropped. This catches page-chrome pollution even when the
    stop-token approach in _dd_values doesn't catch it.
    """
    VALID_PATTERN = re.compile(r"^[a-zA-ZÀ-ÿ0-9\s\-\'/]+$")

    out: list[str] = []
    for v in values:
        if len(v) > 40:
            break   # anything this long is page chrome — stop here
        if not VALID_PATTERN.match(v):
            continue  # skip (could be a stray symbol), but don't stop
        if len(v.split()) > 5:
            break   # 5+ words means we've hit a sentence
        if re.search(r"(https?://|\.com\b|copyright|privacy|roaster|coffees)", v, re.I):
            break
        out.append(v)
        if len(out) >= 8:   # no real coffee has more than ~8 typology entries
            break
    return out


def _filter_origins(values: list[str]) -> list[str]:
    """Drop punctuation-only fragments that come from split span elements."""
    return [o for o in values if len(o) > 2 and re.search(r'\w{2,}', o)]


# ── Phase 1: listing page → collect URLs ─────────────────────────────────────

def parse_listing(html: str) -> tuple[list[tuple[str, str]], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []

    cards = soup.find_all("a", href=re.compile(r"/beans/[^/?#]+/?$"))
    for card in cards:
        href = card.get("href", "")
        url  = href if href.startswith("http") else BASE_URL + href
        name_tag = card.find(["h2", "h3", "h4", "strong"])
        if name_tag:
            name = _clean(_text(name_tag))
        else:
            raw = card.get_text("\n", strip=True)
            name = _clean(raw.splitlines()[0]) if raw.splitlines() else ""
        if name and url:
            results.append((name, url))

    seen: set[str] = set()
    unique = [(n, u) for n, u in results if not (u in seen or seen.add(u))]

    next_url: Optional[str] = None
    next_tag = (
        soup.find("a", rel="next")
        or soup.find("a", attrs={"aria-label": re.compile(r"next", re.I)})
        or soup.find("a", string=re.compile(r"^\s*(next|›|»|→)\s*$", re.I))
    )
    if next_tag:
        href = next_tag.get("href", "")
        if href:
            next_url = href if href.startswith("http") else BASE_URL + href

    return unique, next_url


def get_total_count(html: str) -> Optional[int]:
    soup = BeautifulSoup(html, "html.parser")
    m = re.search(r"([\d,]+)\s+coffees?\s+found", soup.get_text(), re.I)
    return int(m.group(1).replace(",", "")) if m else None


# ── Phase 2: detail page → parse fields ──────────────────────────────────────

def _extract_roaster_url(soup: BeautifulSoup) -> str:
    """
    Find the roaster's actual product/buy URL from the detail page.

    Strategy: walk all <a href> tags, skip any that point to thewaytocoffee.com
    or known social/affiliate domains, return the first external URL found.
    This captures the "Buy from Roaster" destination regardless of button text.
    """
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue
        try:
            domain = urlparse(href).netloc.lower()
            domain = re.sub(r"^www\.", "", domain)
        except Exception:
            continue
        if not any(excl in domain for excl in EXCLUDED_DOMAINS):
            return href
    return ""


def parse_detail(html: str, name: str, url: str) -> Coffee:
    soup = BeautifulSoup(html, "html.parser")

    # Roaster name from internal /roasters/ link (display name only)
    roaster = ""
    roaster_tag = soup.find("a", href=re.compile(r"/roasters/[^/?#]+/?$"))
    if roaster_tag:
        roaster = _clean(_text(roaster_tag))

    # Roaster buy URL — first external link on the page
    roaster_url = _extract_roaster_url(soup)

    # Description
    description = ""
    about_tag = soup.find(string=re.compile(r"about this coffee", re.I))
    if about_tag:
        parent = about_tag.parent
        for sib in parent.next_siblings:
            if hasattr(sib, "get_text") and sib.get_text(strip=True):
                description = _clean(_text(sib))
                break

    origins:      list[str] = []
    flavor_notes: list[str] = []
    roast_level:  str       = ""
    processing:   list[str] = []
    typology:     list[str] = []

    for dt in soup.find_all("dt"):
        label = _clean(_text(dt)).lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue

        if "origin" in label:
            origins = _filter_origins(_dd_values(dd))
        elif "flavor" in label or "flavour" in label or "note" in label:
            flavor_notes = _dd_values(dd)
        elif "roast" in label:
            roast_level = ", ".join(_dd_values(dd, max_items=3))
        elif "process" in label:
            processing = _dd_values(dd, max_items=5)
        elif "typolog" in label or "variet" in label:
            # Extra strict filter for typology — stop-tokens alone don't work
            typology = _filter_typology(_dd_values(dd))

    # Fallback: scan plain text for Label / Value pairs
    if not origins and not flavor_notes:
        lines = [_clean(ln) for ln in soup.get_text("\n").splitlines() if _clean(ln)]
        label_set = set(FIELD_LABELS.keys())
        i = 0
        while i < len(lines):
            lower = lines[i].lower()
            matched_field = FIELD_LABELS.get(lower)
            if matched_field:
                i += 1
                values: list[str] = []
                while i < len(lines) and lines[i].lower() not in label_set:
                    values.extend(_split(lines[i]))
                    i += 1
                if matched_field == "origins":
                    origins = _filter_origins(values)
                elif matched_field == "flavor_notes":
                    flavor_notes = values[:12]
                elif matched_field == "roast_level":
                    roast_level = ", ".join(values[:3])
                elif matched_field == "processing":
                    processing = values[:5]
                elif matched_field == "typology":
                    typology = _filter_typology(values)
            else:
                i += 1

    return Coffee(
        name=name, url=url, roaster=roaster, roaster_url=roaster_url,
        description=description, origins=origins, flavor_notes=flavor_notes,
        roast_level=roast_level, processing=processing, typology=typology,
    )


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def load_checkpoint() -> tuple[list[tuple[str, str]], list[dict], set[str]]:
    stubs: list[tuple[str, str]] = []
    completed: list[dict] = []
    done_urls: set[str] = set()

    if STUBS_FILE.exists():
        try:
            stubs = [tuple(s) for s in json.loads(
                STUBS_FILE.read_text(encoding="utf-8"))]
            log.info("Loaded %d stubs from Phase 1 cache.", len(stubs))
        except Exception:
            log.warning("Stubs file unreadable — will redo Phase 1.")

    if OUTPUT_FILE.exists():
        try:
            completed = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            done_urls = {r["url"] for r in completed}
            log.info("Resuming: %d beans already scraped.", len(done_urls))
        except Exception:
            log.warning("Output file unreadable — starting Phase 2 fresh.")
            completed = []

    return stubs, completed, done_urls


def save_output(records: list[dict]) -> None:
    OUTPUT_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

CHECKPOINT_EVERY = 50

def scrape(max_pages: Optional[int] = 5, delay: float = 1.2,
           roast_filter: Optional[str] = None) -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cached_stubs, completed, done_urls = load_checkpoint()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = make_page(browser)

        try:
            # ── Phase 1 ───────────────────────────────────────────────────────
            if cached_stubs:
                unique_stubs = cached_stubs
                log.info("Skipping Phase 1 (using cached stubs).")
            else:
                log.info("=== Phase 1: collecting coffee URLs ===")
                stub_list: list[tuple[str, str]] = []
                current_url = BEANS_URL
                listing_num = 1

                with tqdm(desc="Listing pages", unit="page") as pbar:
                    while current_url:
                        if max_pages and listing_num > max_pages:
                            break
                        log.info("Listing page %d → %s", listing_num, current_url)
                        html = fetch_html(page, current_url,
                                          wait_selector="a[href*='/beans/']")
                        if listing_num == 1:
                            total = get_total_count(html)
                            if total:
                                log.info("Total coffees on site: %d", total)

                        stubs, next_url = parse_listing(html)
                        log.info("  → %d coffee links found", len(stubs))
                        if not stubs:
                            break
                        stub_list.extend(stubs)
                        pbar.update(1)
                        pbar.set_postfix(collected=len(stub_list))

                        if next_url:
                            current_url = next_url
                        elif listing_num == 1:
                            sep = "&" if "?" in current_url else "?"
                            current_url = f"{current_url}{sep}page=2"
                        elif "page=" in current_url:
                            current_url = re.sub(
                                r"page=\d+", f"page={listing_num + 1}", current_url)
                        else:
                            break

                        listing_num += 1
                        time.sleep(delay)

                seen: set[str] = set()
                unique_stubs = [(n, u) for n, u in stub_list
                                if not (u in seen or seen.add(u))]
                STUBS_FILE.write_text(
                    json.dumps(unique_stubs, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log.info("Cached %d stubs to %s", len(unique_stubs), STUBS_FILE)

            # ── Phase 2 ───────────────────────────────────────────────────────
            remaining = [(n, u) for n, u in unique_stubs if u not in done_urls]
            log.info("=== Phase 2: %d detail pages to scrape ===", len(remaining))

            scraped_this_run = 0
            with tqdm(remaining, desc="Detail pages", unit="coffee") as pbar:
                for name, url in pbar:
                    pbar.set_postfix(coffee=name[:30])
                    try:
                        html   = fetch_html(page, url, wait_selector="body")
                        coffee = parse_detail(html, name, url)
                        completed.append(asdict(coffee))
                    except Exception as exc:
                        log.warning("Failed '%s': %s", name, exc)
                        completed.append({
                            "name": name, "url": url, "roaster": "",
                            "roaster_url": "", "description": "",
                            "origins": [], "flavor_notes": [],
                            "roast_level": "", "processing": [], "typology": [],
                        })
                    scraped_this_run += 1
                    if scraped_this_run % CHECKPOINT_EVERY == 0:
                        save_output(completed)
                        log.info("Checkpoint: %d total saved.", len(completed))
                    time.sleep(delay)

        finally:
            browser.close()

    save_output(completed)

    if roast_filter:
        before = len(completed)
        completed = [r for r in completed
                     if roast_filter.lower() in r.get("roast_level", "").lower()]
        log.info("Roast filter '%s': kept %d / %d.",
                 roast_filter, len(completed), before)

    return completed


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape specialty coffee data from thewaytocoffee.com/beans"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--pages", type=int, default=5, metavar="N",
                     help="Listing pages to scrape (default: 5, ~25 coffees each)")
    grp.add_argument("--all", action="store_true",
                     help="Scrape ALL listing pages (~14,000 coffees, run overnight)")
    parser.add_argument("--roast", default=None, metavar="LEVEL",
                        help="Keep only coffees matching this roast level")
    parser.add_argument("--delay", type=float, default=1.2,
                        help="Seconds between requests (default: 1.2)")
    args = parser.parse_args()

    max_pages = None if args.all else args.pages
    records   = scrape(max_pages=max_pages, delay=args.delay, roast_filter=args.roast)

    if not records:
        log.warning("No coffees scraped.")
        return

    print(f"\nScraped {len(records)} coffees -> {OUTPUT_FILE}")
    print(f"Next: python scrapers/reference_db.py load {OUTPUT_FILE}")


if __name__ == "__main__":
    main()