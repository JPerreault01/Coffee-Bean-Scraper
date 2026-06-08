# scrapers/coffeereview_scraper.py
"""
Scraper for coffeereview.com/review/
=====================================
Two-phase HTML scrape using Playwright + BeautifulSoup:
  1. Listing pages  → collect coffee names + detail URLs
  2. Detail pages   → scrape all review fields (rating, component scores,
                      origin, roast, processing, blind assessment, bottom line,
                      price, roaster location, roaster buy URL)

URL flow:
  Listing page 1: https://www.coffeereview.com/review/
  Listing page N: https://www.coffeereview.com/review/page/N/
  Detail:         https://www.coffeereview.com/review/colombia-penas-blancas-natural-process/

Resumable: re-running skips already-scraped URLs automatically.

Requirements:
    pip install playwright beautifulsoup4 tqdm
    python -m playwright install chromium

Usage:
    python scrapers/coffeereview_scraper.py              # 3 pages (test ~60 reviews)
    python scrapers/coffeereview_scraper.py --pages 20
    python scrapers/coffeereview_scraper.py --all        # full site (~9,000 reviews, overnight)

After scraping:
    python scrapers/coffeereview_db.py load data/coffeereview.json

Query examples:
    python scrapers/coffeereview_db.py stats
    python scrapers/coffeereview_db.py top --n 10
    python scrapers/coffeereview_db.py find "ethiopia"
"""

import argparse
import calendar
import json
import logging
import random
import re
import time
import unicodedata
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

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
DATA_DIR    = REPO_ROOT / "data"
STUBS_FILE  = DATA_DIR / "coffeereview_stubs.json"
OUTPUT_FILE = DATA_DIR / "coffeereview.json"

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL    = "https://www.coffeereview.com"
LISTING_URL = f"{BASE_URL}/review/"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Build month-name → zero-padded-number map (abbreviated + full)
_MONTH_MAP: dict[str, str] = {}
for _i, _m in enumerate(calendar.month_abbr):
    if _m:
        _MONTH_MAP[_m.lower()] = str(_i).zfill(2)
        _MONTH_MAP[f"{_m.lower()}."] = str(_i).zfill(2)
for _i, _m in enumerate(calendar.month_name):
    if _m:
        _MONTH_MAP[_m.lower()] = str(_i).zfill(2)

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class CoffeeReview:
    name:             str
    url:              str
    roaster:          str       = ""
    roaster_location: str       = ""
    rating:           int       = 0
    aroma:            float     = 0.0
    acidity:          float     = 0.0
    body:             float     = 0.0
    flavor:           float     = 0.0
    aftertaste:       float     = 0.0
    origins:          list[str] = field(default_factory=list)
    roast_level:      str       = ""
    processing:       list[str] = field(default_factory=list)
    blind_assessment: str       = ""
    bottom_line:      str       = ""
    review_date:      str       = ""    # ISO format: "2024-03"
    price_usd:        float     = 0.0
    weight_oz:        float     = 0.0
    price_per_oz:     float     = 0.0   # calculated: price_usd / weight_oz if both > 0
    roaster_url:      str       = ""


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
    raise RuntimeError("Could not load %s after %d attempts" % (url, retries))


# ── Text helpers ──────────────────────────────────────────────────────────────

def _text(tag: Optional[Tag]) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(raw: str) -> str:
    """Convert 'June 2026' or 'Jun 2026' to '2026-06'."""
    raw = _clean(raw).lower()
    parts = raw.split()
    if len(parts) >= 2:
        month = _MONTH_MAP.get(parts[0])
        year = parts[-1] if parts[-1].isdigit() and len(parts[-1]) == 4 else None
        if month and year:
            return "%s-%s" % (year, month)
    return raw


def _parse_price(raw: str) -> tuple[float, float, float]:
    """Parse '$28.00/12 ounces' or '$19.50/250 grams' into (price_usd, weight_oz, price_per_oz)."""
    price_m  = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", raw)
    weight_m = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:oz|ounce|gram|g\b|lb)",
        raw, re.I,
    )
    price  = float(price_m.group(1)) if price_m else 0.0
    weight = 0.0
    if weight_m:
        weight = float(weight_m.group(1))
        unit = weight_m.group(0).lower()
        if "gram" in unit or unit.startswith("g"):
            weight = weight / 28.3495
        elif "lb" in unit:
            weight = weight * 16.0
    per_oz = round(price / weight, 3) if weight > 0 else 0.0
    return price, weight, per_oz


def _split_origins(raw: str) -> list[str]:
    """Split 'Colombia and Ethiopia' or 'Colombia/Ethiopia' into individual origin strings."""
    parts = re.split(r"\s*/\s*|\s+and\s+", raw, flags=re.I)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]


def _split_list(raw: str) -> list[str]:
    parts = re.split(r"[,;/]", raw)
    return [p.strip() for p in parts if p.strip()]


# ── Phase 1: listing page → collect URLs ─────────────────────────────────────

def parse_listing(html: str) -> list[tuple[str, str]]:
    """Return list of (coffee_name, detail_url) from one listing page."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []

    for card in soup.find_all("div", class_="review-template"):
        row1 = card.find("div", class_="row-1")
        if not row1:
            continue
        col2 = row1.find("div", class_="col-2")
        if not col2:
            continue

        # Coffee name: h2.review-title (listing) or h1.review-title (detail used as listing)
        title_tag = col2.find(["h1", "h2", "h3"], class_="review-title")
        name = _clean(_text(title_tag)) if title_tag else ""

        # URL from the title link
        url = ""
        if title_tag:
            link = title_tag.find("a")
            if link:
                url = link.get("href", "")
        # Fallback: first link in card matching /review/slug/
        if not url:
            for a in card.find_all("a", href=re.compile(r"/review/[^/?#]+/?$")):
                url = a.get("href", "")
                break

        if name and url:
            if not url.startswith("http"):
                url = BASE_URL + url
            results.append((name, url))

    # Deduplicate by URL
    seen: set[str] = set()
    return [(n, u) for n, u in results if not (u in seen or seen.add(u))]


def get_total_pages(html: str) -> Optional[int]:
    """Read highest page number from pagination block."""
    soup = BeautifulSoup(html, "html.parser")
    pag = soup.find("div", class_="archive-pagination")
    if not pag:
        return None
    nums = []
    for a in pag.find_all("a", href=True):
        m = re.search(r"/review/page/(\d+)/", a["href"])
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else None


def listing_url(page_num: int) -> str:
    return LISTING_URL if page_num <= 1 else "%spage/%d/" % (LISTING_URL, page_num)


# ── Phase 2: detail page → parse all fields ───────────────────────────────────

def _table_kv(soup: BeautifulSoup) -> dict[str, str]:
    """Read all review-template-table rows into a normalised key→value dict."""
    kv: dict[str, str] = {}
    for tbl in soup.find_all("table", class_="review-template-table"):
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                k = _clean(tds[0].get_text(strip=True)).rstrip(":")
                v = _clean(tds[1].get_text(strip=True))
                if k and v:
                    kv[k.lower()] = v
    return kv


def _section_text(rt: Tag, label: str) -> str:
    """Return the paragraph that follows an h2 whose text contains label."""
    for h2 in rt.find_all("h2"):
        if label.lower() in h2.get_text(strip=True).lower():
            for sib in h2.next_siblings:
                if hasattr(sib, "get_text"):
                    t = _clean(sib.get_text(" ", strip=True))
                    if t:
                        return t
    return ""


def _roaster_url(rt: Tag) -> str:
    """
    Find the roaster's buy URL.

    Strategy: coffeereview.com places a standalone 'Visit Roaster' link in a
    div.column.col-2 that is a direct child of div.review-template (not inside
    any row). We find that first; fallback to the first external href in the block.
    """
    for child in rt.children:
        classes = getattr(child, "get", lambda k, d=None: d)("class") or []
        if "col-2" in classes and "column" in classes:
            a = child.find("a", href=True)
            if a and a["href"].startswith("http"):
                return a["href"]
    # Fallback: first external link that isn't the site itself
    for a in rt.find_all("a", href=re.compile(r"^https?://")):
        if "coffeereview.com" not in a["href"]:
            return a["href"]
    return ""


def parse_detail(html: str, name: str, url: str) -> CoffeeReview:
    soup = BeautifulSoup(html, "html.parser")
    rt   = soup.find("div", class_="review-template")
    if not rt:
        return CoffeeReview(name=name, url=url)

    # Name and roaster
    h1          = rt.find("h1", class_="review-title")
    parsed_name = _clean(_text(h1)) if h1 else name
    roaster_tag = rt.find("p", class_="review-roaster")
    roaster     = _clean(_text(roaster_tag))

    # Overall rating
    rating     = 0
    rating_tag = rt.find("span", class_="review-template-rating")
    if rating_tag:
        try:
            rating = int(_clean(rating_tag.get_text(strip=True)))
        except ValueError:
            pass

    # All table key-value pairs
    kv = _table_kv(soup)

    # Origins — "Coffee Origin" cell may contain one or multiple countries
    raw_origin = kv.get("coffee origin", "")
    origins    = _split_origins(raw_origin) if raw_origin else []

    # Roast level
    roast_level = kv.get("roast level", "")

    # Processing method (not always present)
    raw_proc   = kv.get("processing method", kv.get("processing", ""))
    processing = _split_list(raw_proc) if raw_proc else []

    # Roaster location
    roaster_location = kv.get("roaster location", "")

    # Price — "Est. Price: $28.00/12 ounces"
    price_usd = weight_oz = price_per_oz = 0.0
    raw_price = kv.get("est. price", kv.get("price", ""))
    if raw_price:
        price_usd, weight_oz, price_per_oz = _parse_price(raw_price)

    # Review date → ISO
    review_date = _parse_date(kv.get("review date", ""))

    # Component scores
    def _score(key: str) -> float:
        try:
            return float(kv.get(key, 0) or 0)
        except (ValueError, TypeError):
            return 0.0

    aroma      = _score("aroma")
    acidity    = _score("acidity/structure")
    body       = _score("body")
    flavor     = _score("flavor")
    aftertaste = _score("aftertaste")

    # Long-form text sections
    blind_assessment = _section_text(rt, "Blind Assessment")
    bottom_line      = _section_text(rt, "Bottom Line")

    # Roaster buy URL
    roaster_url = _roaster_url(rt)

    return CoffeeReview(
        name=parsed_name, url=url,
        roaster=roaster, roaster_location=roaster_location,
        rating=rating,
        aroma=aroma, acidity=acidity, body=body,
        flavor=flavor, aftertaste=aftertaste,
        origins=origins, roast_level=roast_level,
        processing=processing,
        blind_assessment=blind_assessment,
        bottom_line=bottom_line,
        review_date=review_date,
        price_usd=price_usd, weight_oz=weight_oz,
        price_per_oz=price_per_oz,
        roaster_url=roaster_url,
    )


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _load_stubs() -> dict:
    """
    Load the stubs cache.  Returns a metadata envelope:
      {"complete": bool, "pages_scraped": int, "stubs": [(name, url), ...]}

    Backward compat: a plain list (old format) is treated as incomplete so
    Phase 1 restarts from page 1.
    """
    default: dict = {"complete": False, "pages_scraped": 0, "stubs": []}
    if not STUBS_FILE.exists():
        return default
    try:
        data = json.loads(STUBS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            log.warning(
                "Old-format stubs file (plain list) — treating as incomplete, re-running Phase 1."
            )
            return default
        return {
            "complete":      bool(data.get("complete", False)),
            "pages_scraped": int(data.get("pages_scraped", 0)),
            "stubs":         [tuple(s) for s in data.get("stubs", [])],
        }
    except Exception:
        log.warning("Stubs file unreadable — re-running Phase 1.")
        return default


def _save_stubs(
    stubs: list[tuple[str, str]], *, complete: bool, pages_scraped: int
) -> None:
    STUBS_FILE.write_text(
        json.dumps(
            {"complete": complete, "pages_scraped": pages_scraped, "stubs": stubs},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def load_checkpoint() -> tuple[list[dict], set[str]]:
    completed: list[dict] = []
    done_urls: set[str]   = set()

    if OUTPUT_FILE.exists():
        try:
            completed = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            done_urls = {r["url"] for r in completed}
            log.info("Resuming: %d reviews already scraped.", len(done_urls))
        except Exception:
            log.warning("Output file unreadable — starting Phase 2 fresh.")
            completed = []

    return completed, done_urls


def save_output(records: list[dict]) -> None:
    OUTPUT_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

CHECKPOINT_EVERY = 25


def scrape(max_pages: Optional[int] = 3) -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    completed, done_urls = load_checkpoint()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = make_page(browser)

        try:
            # ── Phase 1 ───────────────────────────────────────────────────────
            stubs_data     = _load_stubs()
            phase1_done    = stubs_data["complete"]
            pages_scraped  = stubs_data["pages_scraped"]
            existing_stubs: list[tuple[str, str]] = stubs_data["stubs"]

            if phase1_done:
                unique_stubs = existing_stubs
                log.info("Skipping Phase 1 (complete cache: %d stubs).", len(unique_stubs))
            else:
                resume_from = pages_scraped + 1  # 1 when starting fresh
                stub_list   = list(existing_stubs)

                if resume_from > 1:
                    log.info(
                        "Resuming Phase 1 from page %d (%d stubs already cached).",
                        resume_from, len(stub_list),
                    )
                else:
                    log.info("=== Phase 1: collecting review URLs ===")

                # Fetch page 1 when starting fresh (resume_from == 1)
                # or when --all is used and we need total_pages regardless of resume point
                first_html  = None
                total_pages = None
                if resume_from == 1 or max_pages is None:
                    first_html  = fetch_html(page, LISTING_URL,
                                             wait_selector="div.review-template")
                    total_pages = get_total_pages(first_html)
                    if total_pages:
                        log.info("Total pages on site: %d (~%d reviews)",
                                 total_pages, total_pages * 20)

                end_page = (
                    total_pages if max_pages is None
                    else min(max_pages, total_pages or max_pages)
                )

                # Add page 1 stubs only when starting fresh (not resuming)
                if resume_from == 1 and first_html is not None:
                    p1_stubs = parse_listing(first_html)
                    log.info("  page 1 → %d links", len(p1_stubs))
                    stub_list.extend(p1_stubs)
                    _save_stubs(stub_list, complete=False, pages_scraped=1)

                # Remaining pages
                loop_start = max(resume_from, 2)
                if end_page is not None and loop_start <= end_page:
                    with tqdm(range(loop_start, end_page + 1),
                              desc="Listing pages", unit="page") as pbar:
                        for page_num in pbar:
                            lurl  = listing_url(page_num)
                            log.info("Listing page %d → %s", page_num, lurl)
                            html  = fetch_html(page, lurl,
                                               wait_selector="div.review-template")
                            stubs = parse_listing(html)
                            log.info("  → %d review links found", len(stubs))
                            stub_list.extend(stubs)
                            pbar.set_postfix(collected=len(stub_list))
                            _save_stubs(stub_list, complete=False, pages_scraped=page_num)
                            if page_num < end_page:
                                time.sleep(random.uniform(2.0, 4.0))

                # Deduplicate and mark Phase 1 complete
                seen: set[str] = set()
                unique_stubs = [(n, u) for n, u in stub_list
                                if not (u in seen or seen.add(u))]
                _save_stubs(unique_stubs, complete=True,
                            pages_scraped=end_page or pages_scraped)
                log.info("Phase 1 complete: %d unique stubs cached.", len(unique_stubs))

            # ── Phase 2 ───────────────────────────────────────────────────────
            remaining = [(n, u) for n, u in unique_stubs if u not in done_urls]
            log.info("=== Phase 2: %d detail pages to scrape ===", len(remaining))

            scraped_this_run = 0
            with tqdm(remaining, desc="Detail pages", unit="review") as pbar:
                for name, url in pbar:
                    pbar.set_postfix(review=name[:30])
                    try:
                        html   = fetch_html(page, url,
                                            wait_selector="div.review-template")
                        review = parse_detail(html, name, url)
                        completed.append(asdict(review))
                    except Exception as exc:
                        log.warning("Failed '%s': %s", name, exc)
                        completed.append({"name": name, "url": url})

                    scraped_this_run += 1
                    if scraped_this_run % CHECKPOINT_EVERY == 0:
                        save_output(completed)
                        log.info("Checkpoint: %d total saved.", len(completed))
                    time.sleep(random.uniform(2.0, 5.0))

        finally:
            browser.close()

    save_output(completed)
    return completed


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape professional coffee reviews from coffeereview.com"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument(
        "--pages", type=int, default=3, metavar="N",
        help="Listing pages to scrape (default: 3, ~20 reviews each)",
    )
    grp.add_argument(
        "--all", action="store_true",
        help="Scrape ALL listing pages (~9,000 reviews; run overnight)",
    )
    args = parser.parse_args()

    max_pages = None if args.all else args.pages
    records   = scrape(max_pages=max_pages)

    if not records:
        log.warning("No reviews scraped.")
        return

    print("\nScraped %d reviews -> %s" % (len(records), OUTPUT_FILE))
    print("Next: python scrapers/coffeereview_db.py load %s" % OUTPUT_FILE)


if __name__ == "__main__":
    main()
