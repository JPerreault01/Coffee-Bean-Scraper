# data_pipeline/web_scraper.py
"""
Web scraper for coffee-focused sites.
Collects articles from Sprudge, Coffee Ad Astra, and Perfect Daily Grind.
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("web_scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def setup_logging():
    logging.basicConfig(
        format="[web_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


def get_domain_tags(text: str, config: dict) -> list[str]:
    text_lower = text.lower()
    return [tag for tag, keywords in config["domain_tags"].items()
            if any(kw.lower() in text_lower for kw in keywords)]


def compute_web_quality(title: str, body: str, soup: BeautifulSoup, config: dict) -> float:
    qcfg = config["web"]["quality"]
    tech_vocab = config.get("tech_vocabulary", [])

    length_score = min(len(body), qcfg["length_normalize_cap"]) / qcfg["length_normalize_cap"]

    headings = soup.find_all(["h2", "h3", "h4"])
    heading_score = min(len(headings), qcfg["min_headings_for_boost"]) / qcfg["min_headings_for_boost"]

    text_lower = body.lower()
    tech_hits = sum(1 for term in tech_vocab if term.lower() in text_lower)
    tech_score = min(tech_hits / 5, 1.0)

    quality = (
        length_score * qcfg["length_weight"]
        + heading_score * qcfg["headings_weight"]
        + tech_score * qcfg["tech_vocab_weight"]
    )
    return round(quality, 4)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    })
    return session


def fetch_page(session: requests.Session, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
    try:
        # Rotate User-Agent on every fetch
        session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code} fetching {url}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"Connection error fetching {url}")
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching {url}")
    except Exception as e:
        logger.warning(f"Unexpected error fetching {url}: {e}")
    return None


def extract_article_text(soup: BeautifulSoup) -> tuple[str, str]:
    """Return (title, body_text) after stripping boilerplate."""

    # Extract title — prefer og:title, fall back to h1
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # Strip boilerplate elements before extracting body
    for selector in [
        "nav", "header", "footer", "aside",
        ".sidebar", ".widget", ".newsletter", ".subscribe",
        ".comment", ".comments", ".comment-section",
        ".advertisement", ".ad", ".ads",
        "[class*='cookie']", "[class*='popup']", "[class*='banner']",
        "[class*='related']", "[class*='share']", "[class*='social']",
        "script", "style", "noscript",
    ]:
        for el in soup.select(selector):
            el.decompose()

    # Try common article containers in priority order
    article = None
    for selector in [
        "article",
        ".entry-content",
        ".post-content",
        ".article-content",
        ".article-body",
        ".post-body",
        '[class*="article"]',
        "main",
    ]:
        article = soup.select_one(selector)
        if article:
            break

    if article:
        body = article.get_text(separator="\n", strip=True)
    else:
        body = soup.get_text(separator="\n", strip=True)

    # Normalize whitespace
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    body = "\n".join(lines)

    return title, body


def _is_article_url(href: str, base_parsed) -> bool:
    """Return True if a URL looks like an article rather than nav/admin/media."""
    parsed = urlparse(href)

    if parsed.netloc != base_parsed.netloc:
        return False
    if parsed.path in ("", "/"):
        return False
    if parsed.query:
        return False
    if parsed.fragment:
        return False

    skip_segments = [
        "/tag/", "/category/", "/author/", "/page/",
        "/wp-content/", "/wp-admin/", "/wp-json/",
        "/feed/", "/cdn-cgi/", "/cart/", "/checkout/",
        "/account/", "/login/", "/register/", "/search/",
        "/about", "/contact", "/advertise", "/privacy",
        "/terms", "/jobs/", "/events/", "/subscribe",
    ]
    if any(seg in parsed.path for seg in skip_segments):
        return False

    skip_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf",
                       ".xml", ".json", ".css", ".js")
    if parsed.path.lower().endswith(skip_extensions):
        return False

    return True


def collect_wordpress_urls(
    session: requests.Session,
    start_url: str,
    base_url: str,
    max_articles: int,
    delay: float,
) -> list[str]:
    """Collect article URLs from a WordPress-paginated blog index."""
    urls: set[str] = set()
    page = 1
    base_parsed = urlparse(base_url)
    consecutive_empty = 0

    while len(urls) < max_articles:
        page_url = start_url if page == 1 else start_url.rstrip("/") + f"/page/{page}/"

        logger.info(f"Collecting URLs from {page_url}")
        soup = fetch_page(session, page_url)
        if not soup:
            break

        found_on_page = 0
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"]).split("#")[0]
            if _is_article_url(href, base_parsed) and href not in urls:
                urls.add(href)
                found_on_page += 1

        if found_on_page == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2 or page > 1:
                break
        else:
            consecutive_empty = 0

        page += 1
        time.sleep(delay + random.uniform(0, 1))

    return list(urls)[:max_articles]


def collect_link_collection_urls(
    session: requests.Session,
    start_url: str,
    base_url: str,
    max_articles: int,
    delay: float,
) -> list[str]:
    """Collect article URLs by scanning all links on a site's homepage/index page."""
    urls: set[str] = set()
    base_parsed = urlparse(base_url)

    soup = fetch_page(session, start_url)
    if not soup:
        return []

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0]
        if _is_article_url(href, base_parsed) and href != start_url:
            urls.add(href)

    return list(urls)[:max_articles]


def collect_wordpress_category_urls(
    session: requests.Session,
    base_url: str,
    categories: list[str],
    max_articles: int,
    delay: float,
) -> list[str]:
    """
    Collect article URLs from a list of WordPress category paths.
    Each category is paginated as /category/slug/page/2/ etc.
    Stops each category when pages return no new URLs.
    """
    urls: set[str] = set()
    base_parsed = urlparse(base_url)

    for category in categories:
        if len(urls) >= max_articles:
            break

        category_url = base_url.rstrip("/") + "/" + category.lstrip("/")
        page = 1

        while len(urls) < max_articles:
            page_url = category_url if page == 1 else category_url.rstrip("/") + f"/page/{page}/"

            logger.info(f"Collecting PDG URLs from {page_url}")
            soup = fetch_page(session, page_url)
            if not soup:
                break

            found_on_page = 0
            for a in soup.find_all("a", href=True):
                href = urljoin(base_url, a["href"]).split("#")[0]
                if _is_article_url(href, base_parsed) and href not in urls:
                    urls.add(href)
                    found_on_page += 1

            # If no new articles found on page 2+, this category is exhausted
            if found_on_page == 0 and page > 1:
                break

            page += 1
            time.sleep(delay + random.uniform(0, 1))

    return list(urls)[:max_articles]


def scrape_articles(
    session: requests.Session,
    urls: list[str],
    site_name: str,
    config: dict,
    output_path: Path,
) -> int:
    wcfg = config["web"]
    delay = wcfg["request_delay_seconds"]
    timeout = wcfg["request_timeout"]
    min_chars = wcfg["min_article_chars"]
    scraped_at = datetime.now(tz=timezone.utc).isoformat()
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for i, url in enumerate(urls):
            try:
                time.sleep(delay + random.uniform(0, 1.5))
                soup = fetch_page(session, url, timeout=timeout)
                if not soup:
                    continue

                title, body = extract_article_text(soup)

                if len(body) < min_chars:
                    logger.debug(f"Skipping short article ({len(body)} chars): {url}")
                    continue

                if not title:
                    title = url

                domain_tags = get_domain_tags(title + " " + body, config)
                quality_score = compute_web_quality(title, body, soup, config)

                envelope = {
                    "source": "web",
                    "content_type": "article",
                    "domain_tags": domain_tags,
                    "quality_score": quality_score,
                    "raw": {
                        "url": url,
                        "title": title,
                        "body": body,
                        "site": site_name,
                    },
                    "scraped_at": scraped_at,
                }

                f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                count += 1

                if count % 25 == 0:
                    logger.info(f"{site_name}: {count} articles scraped so far...")

            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")

    return count


def run(config: dict) -> dict:
    setup_logging()
    wcfg = config["web"]
    output_dir = Path(wcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    session = make_session()
    delay = wcfg["request_delay_seconds"]
    timeout = wcfg["request_timeout"]
    summary = {"articles": 0, "by_site": {}}
    sites = wcfg["sites"]

    # Sprudge — WordPress pagination
    sp_cfg = sites["sprudge"]
    logger.info("Collecting Sprudge article URLs...")
    sp_urls = collect_wordpress_urls(
        session, sp_cfg["start_url"], sp_cfg["base_url"], sp_cfg["max_articles"], delay
    )
    logger.info(f"Sprudge: {len(sp_urls)} URLs collected, scraping...")
    sp_count = scrape_articles(session, sp_urls, "sprudge", config, output_dir / "sprudge.jsonl")
    summary["by_site"]["sprudge"] = sp_count
    summary["articles"] += sp_count

    # Coffee Ad Astra — single-page link collection
    caa_cfg = sites["coffee_ad_astra"]
    logger.info("Collecting Coffee Ad Astra article URLs...")
    caa_urls = collect_link_collection_urls(
        session, caa_cfg["start_url"], caa_cfg["base_url"], caa_cfg["max_articles"], delay
    )
    logger.info(f"Coffee Ad Astra: {len(caa_urls)} URLs collected, scraping...")
    caa_count = scrape_articles(session, caa_urls, "coffee_ad_astra", config, output_dir / "coffee_ad_astra.jsonl")
    summary["by_site"]["coffee_ad_astra"] = caa_count
    summary["articles"] += caa_count

    # Perfect Daily Grind — WordPress category pagination
    pdg_cfg = sites["perfect_daily_grind"]
    logger.info("Collecting Perfect Daily Grind article URLs...")
    pdg_urls = collect_wordpress_category_urls(
        session, pdg_cfg["base_url"], pdg_cfg["categories"], pdg_cfg["max_articles"], delay
    )
    logger.info(f"Perfect Daily Grind: {len(pdg_urls)} URLs collected, scraping...")
    pdg_count = scrape_articles(session, pdg_urls, "perfect_daily_grind", config, output_dir / "perfect_daily_grind.jsonl")
    summary["by_site"]["perfect_daily_grind"] = pdg_count
    summary["articles"] += pdg_count

    by_site_str = ", ".join(f"{k}: {v}" for k, v in summary["by_site"].items())
    print(f"Web complete:     {summary['articles']:,} articles ({by_site_str})")
    return summary


if __name__ == "__main__":
    cfg = json.loads((Path(__file__).parent / "config.json").read_text())
    run(cfg)
