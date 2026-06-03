"""
Scraper for thewaytocoffee.com/beans
=====================================
Two-phase scrape:
  1. Listing pages  → collect coffee names + detail URLs
  2. Detail pages   → scrape origin, flavor notes, roast, processing, typology,
                      roaster name, roaster URL, and description

Requirements:
    pip install playwright beautifulsoup4 tqdm
    playwright install chromium

Usage:
    # Scrape first 5 listing pages (~125 coffees), save to CSV
    python waytocoffee_scraper.py

    # Scrape 20 listing pages (~500 coffees)
    python waytocoffee_scraper.py --pages 20

    # Scrape ALL pages (14,000+ coffees — takes a long time)
    python waytocoffee_scraper.py --all

    # Save as JSON
    python waytocoffee_scraper.py --pages 10 --format json

    # Filter by roast level after scraping
    python waytocoffee_scraper.py --pages 20 --roast Light

    # Custom output file
    python waytocoffee_scraper.py --pages 20 --output my_coffees.csv
"""

import argparse
import csv
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

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

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Coffee:
    name: str
    url: str
    roaster: str = ""
    roaster_url: str = ""
    description: str = ""
    origins: list[str] = field(default_factory=list)
    flavor_notes: list[str] = field(default_factory=list)
    roast_level: str = ""
    processing: list[str] = field(default_factory=list)
    typology: list[str] = field(default_factory=list)

    def as_flat_dict(self) -> dict:
        return {
            "name":         self.name,
            "url":          self.url,
            "roaster":      self.roaster,
            "roaster_url":  self.roaster_url,
            "description":  self.description,
            "origins":      " | ".join(self.origins),
            "flavor_notes": ", ".join(self.flavor_notes),
            "roast_level":  self.roast_level,
            "processing":   ", ".join(self.processing),
            "typology":     ", ".join(self.typology),
        }


# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL  = "https://www.thewaytocoffee.com"
BEANS_URL = f"{BASE_URL}/beans/"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Labels used on detail pages (lowercase)
FIELD_LABELS = {
    "origin":        "origins",
    "flavor notes":  "flavor_notes",
    "flavour notes": "flavor_notes",
    "roast level":   "roast_level",
    "processing":    "processing",
    "typology":      "typology",
}

# ── Browser helpers ───────────────────────────────────────────────────────────

def make_page(browser: Browser) -> Page:
    ctx = browser.new_context(
        user_agent=UA,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()
    # Block images/fonts to speed things up
    page.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("image", "font", "media")
        else route.continue_(),
    )
    return page


def fetch_html(page: Page, url: str, wait_selector: str,
               retries: int = 3, delay: float = 2.0) -> str:
    """Load *url*, wait for *wait_selector*, return rendered HTML."""
    for attempt in range(1, retries + 1):
        try:
            # domcontentloaded is much faster than networkidle
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
    return re.sub(r"\s+", " ", s).strip()

def _split(text: str) -> list[str]:
    """Split on commas or newlines, return non-empty stripped parts."""
    parts = re.split(r"[,\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def _dd_values(dd: Tag) -> list[str]:
    """
    Extract all values from a <dd> tag, handling both layouts:

    Layout A — each value is its own child element (span, li, a, p, div):
        <dd>
          <span>Orange</span>
          <span>Dark Chocolate</span>
          <span>Caramel</span>
        </dd>

    Layout B — all values in one text node, comma/newline separated:
        <dd>Orange, Dark Chocolate, Caramel</dd>
        <dd>Arabica\nPink Bourbon\nCaturra</dd>

    The site renders extra page content (roaster bio, similar coffees, footer)
    inside the same <dd> on detail pages. We stop collecting as soon as we hit
    any known page-chrome sentinel.
    """
    # Tokens that signal the start of non-field page content.
    STOP_TOKENS = {
        "buy from roaster",
        "view all coffees",
        "similar coffee beans",
        "exclusive discount",
        "privacy policy",
        "cookie policy",
    }

    def is_junk(text: str) -> bool:
        low = text.lower()
        # Stop on known chrome tokens
        if low in STOP_TOKENS:
            return True
        # Stop if any stop token appears as a substring (handles e.g. long footer blobs)
        if any(tok in low for tok in STOP_TOKENS):
            return True
        # Stop on suspiciously long strings — valid typology/flavor values are short
        if len(text) > 80:
            return True
        return False

    # Collect direct child tags that carry their own text
    child_tags = [
        c for c in dd.children
        if hasattr(c, "get_text") and c.get_text(strip=True)
        and c.name in ("span", "li", "a", "p", "div", "strong", "em")
    ]

    if child_tags:
        # Layout A: one item per child element — stop at first chrome sentinel
        values: list[str] = []
        for c in child_tags:
            text = _clean(c.get_text(" ", strip=True))
            if is_junk(text):
                break
            if text:
                values.append(text)
    else:
        # Layout B: one text blob — split, then drop anything after a stop token
        raw_values = _split(_clean(dd.get_text(" ", strip=True)))
        values = []
        for v in raw_values:
            if is_junk(v):
                break
            values.append(v)

    return values


# ── Phase 1: listing page → collect URLs ─────────────────────────────────────

def parse_listing(html: str) -> tuple[list[tuple[str, str]], Optional[str]]:
    """
    Parse a /beans/ listing page.
    Returns:
        ([(name, detail_url), ...], next_page_url_or_None)
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []

    # Every coffee card is an <a> linking to /beans/<slug>/
    cards = soup.find_all("a", href=re.compile(r"/beans/[^/?#]+/?$"))
    for card in cards:
        href = card.get("href", "")
        url  = href if href.startswith("http") else BASE_URL + href

        # Name: first heading-like tag, or first non-empty text
        name_tag = card.find(["h2", "h3", "h4", "strong"])
        if name_tag:
            name = _clean(_text(name_tag))
        else:
            # Grab first line of card text before any field label
            raw = card.get_text("\n", strip=True)
            name = _clean(raw.splitlines()[0]) if raw.splitlines() else ""

        if name and url:
            results.append((name, url))

    # Deduplicate
    seen: set[str] = set()
    unique = [(n, u) for n, u in results if not (u in seen or seen.add(u))]

    # Next page: look for rel="next", aria-label="Next", or text Next/›/»
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

def parse_detail(html: str, name: str, url: str) -> Coffee:
    """
    Parse a single coffee detail page into a Coffee object.

    The detail page uses a definition-list pattern:
        <dt>Origin</dt><dd>Cajamarca (Peru)</dd>
        ...
    with a separate <p> or <div> for the description, and an <a> for the roaster.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Roaster ───────────────────────────────────────────────────────────────
    roaster = ""
    roaster_url = ""
    roaster_tag = soup.find("a", href=re.compile(r"/roasters/[^/?#]+/?$"))
    if roaster_tag:
        roaster     = _clean(_text(roaster_tag))
        r_href      = roaster_tag.get("href", "")
        roaster_url = r_href if r_href.startswith("http") else BASE_URL + r_href

    # ── Description ───────────────────────────────────────────────────────────
    description = ""
    # Look for a section labelled "About This Coffee"
    about_tag = soup.find(string=re.compile(r"about this coffee", re.I))
    if about_tag:
        # The description is typically the next <p> sibling or parent's next sibling
        parent = about_tag.parent
        desc_tag = None
        for sib in parent.next_siblings:
            if hasattr(sib, "get_text") and sib.get_text(strip=True):
                desc_tag = sib
                break
        if desc_tag:
            description = _clean(_text(desc_tag))

    # ── Structured fields via <dl>/<dt>/<dd> ─────────────────────────────────
    origins:      list[str] = []
    flavor_notes: list[str] = []
    roast_level:  str       = ""
    processing:   list[str] = []
    typology:     list[str] = []

    dts = soup.find_all("dt")
    for dt in dts:
        label = _clean(_text(dt)).lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue

        if "origin" in label:
            origins = _dd_values(dd)
        elif "flavor" in label or "flavour" in label or "note" in label:
            flavor_notes = _dd_values(dd)
        elif "roast" in label:
            # Roast level is a single value — join in case of unexpected children
            roast_level = ", ".join(_dd_values(dd))
        elif "process" in label:
            processing = _dd_values(dd)
        elif "typolog" in label or "variet" in label:
            typology = _dd_values(dd)

    # ── Fallback: scan all text lines for Label / Value pairs ────────────────
    if not origins and not flavor_notes:
        lines = [_clean(ln) for ln in soup.get_text("\n").splitlines() if _clean(ln)]
        # Build a set of all known labels for quick lookup
        label_set = set(FIELD_LABELS.keys())
        i = 0
        while i < len(lines):
            lower = lines[i].lower()
            matched_field = FIELD_LABELS.get(lower)
            if matched_field:
                # Collect all following lines until the next label or end
                i += 1
                values: list[str] = []
                while i < len(lines) and lines[i].lower() not in label_set:
                    values.extend(_split(lines[i]))
                    i += 1
                if matched_field == "origins":
                    origins = values
                elif matched_field == "flavor_notes":
                    flavor_notes = values
                elif matched_field == "roast_level":
                    roast_level = ", ".join(values)
                elif matched_field == "processing":
                    processing = values
                elif matched_field == "typology":
                    typology = values
            else:
                i += 1

    return Coffee(
        name=name,
        url=url,
        roaster=roaster,
        roaster_url=roaster_url,
        description=description,
        origins=origins,
        flavor_notes=flavor_notes,
        roast_level=roast_level,
        processing=processing,
        typology=typology,
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

def scrape(
    max_pages:    Optional[int] = 5,
    roast_filter: Optional[str] = None,
    delay:        float         = 1.2,
) -> list[Coffee]:
    """
    Full two-phase scrape.

    Phase 1 — walk listing pages to collect (name, url) pairs.
    Phase 2 — visit each detail URL and parse the full coffee record.
    """
    all_coffees: list[Coffee] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = make_page(browser)

        try:
            # ── Phase 1: collect detail URLs from listing pages ───────────────
            stub_list: list[tuple[str, str]] = []   # [(name, url), ...]
            current_url = BEANS_URL
            listing_num = 1

            log.info("=== Phase 1: collecting coffee URLs from listing pages ===")
            with tqdm(desc="Listing pages", unit="page") as pbar:
                while current_url:
                    if max_pages and listing_num > max_pages:
                        log.info("Reached listing-page limit (%d).", max_pages)
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
                        log.warning("No links on listing page %d — stopping.", listing_num)
                        break

                    stub_list.extend(stubs)
                    pbar.update(1)
                    pbar.set_postfix(collected=len(stub_list))

                    # Advance to next listing page
                    if next_url:
                        current_url = next_url
                    elif listing_num == 1:
                        sep = "&" if "?" in current_url else "?"
                        current_url = f"{current_url}{sep}page=2"
                    elif "page=" in current_url:
                        current_url = re.sub(
                            r"page=\d+", f"page={listing_num + 1}", current_url
                        )
                    else:
                        log.info("No next listing page — done collecting.")
                        break

                    listing_num += 1
                    time.sleep(delay)

            # Deduplicate stubs in case they appeared across pages
            seen: set[str] = set()
            unique_stubs = [(n, u) for n, u in stub_list
                            if not (u in seen or seen.add(u))]
            log.info("Total unique coffees to detail-scrape: %d", len(unique_stubs))

            # ── Phase 2: scrape each detail page ─────────────────────────────
            log.info("=== Phase 2: scraping detail pages ===")
            with tqdm(unique_stubs, desc="Detail pages", unit="coffee") as pbar:
                for name, url in pbar:
                    pbar.set_postfix(coffee=name[:30])
                    try:
                        html   = fetch_html(page, url, wait_selector="body")
                        coffee = parse_detail(html, name, url)
                        all_coffees.append(coffee)
                    except Exception as exc:
                        log.warning("Failed to scrape detail for '%s': %s", name, exc)
                        # Still save a stub record so we don't lose the entry
                        all_coffees.append(Coffee(name=name, url=url))
                    time.sleep(delay)

        finally:
            browser.close()

    # ── Optional roast filter ─────────────────────────────────────────────────
    if roast_filter:
        before = len(all_coffees)
        all_coffees = [
            c for c in all_coffees
            if roast_filter.lower() in c.roast_level.lower()
        ]
        log.info("Roast filter '%s': kept %d / %d.",
                 roast_filter, len(all_coffees), before)

    return all_coffees


# ── Output ────────────────────────────────────────────────────────────────────

CSV_FIELDS = ["name", "url", "roaster", "roaster_url", "description",
              "origins", "flavor_notes", "roast_level", "processing", "typology"]

def save_csv(coffees: list[Coffee], path: str) -> None:
    out = Path(path)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(c.as_flat_dict() for c in coffees)
    log.info("Saved %d rows → %s", len(coffees), out.resolve())

def save_json(coffees: list[Coffee], path: str) -> None:
    out = Path(path)
    with out.open("w", encoding="utf-8") as fh:
        json.dump([asdict(c) for c in coffees], fh, ensure_ascii=False, indent=2)
    log.info("Saved %d records → %s", len(coffees), out.resolve())


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape specialty coffee data from thewaytocoffee.com/beans"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--pages", type=int, default=5, metavar="N",
                     help="Listing pages to scrape (default: 5, ~25 coffees each)")
    grp.add_argument("--all", action="store_true",
                     help="Scrape ALL listing pages (14,000+ coffees)")
    parser.add_argument("--format", choices=["csv", "json"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--output", default=None,
                        help="Output filename (default: coffees.csv / coffees.json)")
    parser.add_argument("--roast", default=None, metavar="LEVEL",
                        help="Keep only coffees matching this roast level, e.g. Light")
    parser.add_argument("--delay", type=float, default=1.2,
                        help="Seconds between requests (default: 1.2)")
    args = parser.parse_args()

    max_pages = None if args.all else args.pages
    output    = args.output or f"coffees.{args.format}"

    coffees = scrape(max_pages=max_pages, roast_filter=args.roast, delay=args.delay)

    if not coffees:
        log.warning("No coffees scraped.")
        return

    if args.format == "json":
        save_json(coffees, output)
    else:
        save_csv(coffees, output)

    print(f"\n✅  Scraped {len(coffees)} coffees → {output}")


if __name__ == "__main__":
    main()