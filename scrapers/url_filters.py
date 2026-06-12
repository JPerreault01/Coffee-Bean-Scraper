# scrapers/url_filters.py
"""
Shared roaster-URL filters for the scraper pipeline.

Two checks decide whether a product's roaster_url is worth fetching at all:

  - is_skippable_url(url): affiliate redirects / social / link-trackers that
    never resolve to a real product page.
  - build_placeholder_urls(products): (brand, url) pairs reused across 3+
    products of one brand — catalog-expansion artifacts (e.g. every Volcanica
    bean pointing at one sumatra page) that must not be trusted as a given
    product's real source.

These used to live in fetch_bean_images.py and resolvers/_http.py separately.
This is now the single home so fetch_bean_images.py, price_scraper.py, and the
resolver chain all share one implementation.
"""

from __future__ import annotations

from collections import Counter

# Affiliate redirects / social / link-trackers we cannot scrape a real page from.
SKIP_URL_PATTERNS = (
    "awin1.com", "shareasale.com", "linksynergy.com", "impact.com",
    "pinterest.", "prf.hn", "go.redirectingat.com", "track.effiliation.com",
    "sovrn.com", "viglink.com", "flexlinkspro.com", "flexlinks.com",
)

# A (brand, url) pair shared by this many products is treated as a placeholder.
PLACEHOLDER_MIN_SHARED = 3


def is_skippable_url(url: str) -> bool:
    """True for affiliate redirects / social URLs that never yield a product page."""
    if not url:
        return True
    return any(p in url for p in SKIP_URL_PATTERNS)


def build_placeholder_urls(products: list[dict]) -> set[tuple[str, str]]:
    """(brand, url) pairs reused across 3+ products — catalog-expansion
    artifacts (all Volcanica beans pointing at one sumatra page, etc.)."""
    counter: Counter = Counter()
    for p in products:
        brand = p.get("brand", "")
        url = p.get("roaster_url", "")
        if brand and url:
            counter[(brand, url)] += 1
    return {pair for pair, n in counter.items() if n >= PLACEHOLDER_MIN_SHARED}
