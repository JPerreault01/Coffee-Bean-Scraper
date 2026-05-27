"""
Web scraper for coffee-focused sites.
Collects articles from Barista Hustle, Coffee Ad Astra, and Perfect Daily Grind.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("web_scraper")


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


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
    tech_vocab = config["tech_vocabulary"]

    length_score = min(len(body), qcfg["length_normalize_cap"]) / qcfg["length_normalize_cap"]

    headings = soup.find_all(["h2", "h3", "h4"])
    heading_score = min(len(headings), qcfg["min_headings_for_boost"]) / qcfg["min_headings_for_boost"]

    text_lower = body.lower()
    words = text_lower.split()
    word_count = max(len(words), 1)
    tech_hits = sum(1 for term in tech_vocab if term.lower() in text_lower)
    tech_score = min(tech_hits / 5, 1.0)

    quality = (
        length_score * qcfg["length_weight"]
        + heading_score * qcfg["headings_weight"]
        + tech_score * qcfg["tech_vocab_weight"]
    )
    return round(quality, 4)


def make_session(timeout: int = 30) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; CoffeePipeline/1.0; +https://github.com/JPerreault01/Coffee-Bean-Scraper)"
    })
    return session


def fetch_page(session: requests.Session, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error fetching {url}: {e}")
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching {url}")
    except Exception as e:
        logger.warning(f"Unexpected error fetching {url}: {e}")
    return None


def extract_article_text(soup: BeautifulSoup) -> tuple[str, str]:
    """Return (title, body_text) after stripping boilerplate."""
    # Extract title
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # Remove boilerplate elements
    for selector in [
        "nav", "header", "footer", "aside",
        ".sidebar", ".widget", ".newsletter", ".subscribe",
        ".comment", ".comments", ".comment-section",
        ".advertisement", ".ad", ".ads",
        "[class*='cookie']", "[class*='popup']",
        "script", "style", "noscript",
    ]:
        for el in soup.select(selector):
            el.decompose()

    # Try common article containers first
    article = None
    for selector in ["article", ".entry-content", ".post-content", ".article-content", "main"]:
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


def collect_wordpress_urls(session: requests.Session, start_url: str, base_url: str, max_articles: int, delay: float) -> list[str]:
    """Collect article URLs from a WordPress-paginated blog."""
    urls: set[str] = set()
    page = 1
    base_parsed = urlparse(base_url)

    while len(urls) < max_articles:
        if page == 1:
            page_url = start_url
        else:
            page_url = start_url.rstrip("/") + f"/page/{page}/"

        logger.info(f"Collecting URLs from {page_url}")
        soup = fetch_page(session, page_url)
        if not soup:
            break

        found = False
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            parsed = urlparse(href)
            if (parsed.netloc == base_parsed.netloc
                    and parsed.path not in ("", "/")
                    and href not in urls
                    and not any(x in parsed.path for x in ["/tag/", "/category/", "/author/", "/page/", "?"])):
                urls.add(href)
                found = True

        if not found and page > 1:
            break

        page += 1
        time.sleep(delay)

    return list(urls)[:max_articles]


def collect_link_collection_urls(session: requests.Session, start_url: str, base_url: str, max_articles: int, delay: float) -> list[str]:
    """Collect article URLs by scanning all links on a site's homepage/index."""
    urls: set[str] = set()
    base_parsed = urlparse(base_url)

    soup = fetch_page(session, start_url)
    if not soup:
        return []

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        parsed = urlparse(href)
        if (parsed.netloc == base_parsed.netloc
                and len(parsed.path) > 1
                and not parsed.path.endswith(("/", ".xml", ".json"))
                and "?" not in href
                and href != start_url):
            urls.add(href)

    return list(urls)[:max_articles]


def collect_perfect_daily_grind_urls(session: requests.Session, site_cfg: dict, max_articles: int, delay: float) -> list[str]:
    """Collect URLs from PDG's category pages with WordPress pagination."""
    urls: set[str] = set()
    base_url = site_cfg["base_url"]
    base_parsed = urlparse(base_url)

    for category in site_cfg["categories"]:
        page = 1
        category_url = base_url + category

        while len(urls) < max_articles:
            if page == 1:
                page_url = category_url
            else:
                page_url = category_url.rstrip("/") + f"/page/{page}/"

            logger.info(f"Collecting PDG URLs from {page_url}")
            soup = fetch_page(session, page_url)
            if not soup:
                break

            found = False
            for a in soup.find_all("a", href=True):
                href = urljoin(base_url, a["href"])
                parsed = urlparse(href)
                if (parsed.netloc == base_parsed.netloc
                        and len(parsed.path) > 1
                        and not any(x in parsed.path for x in ["/category/", "/tag/", "/author/", "/page/"])
                        and "?" not in href
                        and href not in urls):
                    urls.add(href)
                    found = True

            if not found and page > 1:
                break

            page += 1
            time.sleep(delay)

    return list(urls)[:max_articles]


def scrape_articles(session: requests.Session, urls: list[str], site_name: str, config: dict, output_path: Path) -> int:
    wcfg = config["web"]
    delay = wcfg["request_delay_seconds"]
    scraped_at = datetime.now(tz=timezone.utc).isoformat()
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for url in urls:
            try:
                time.sleep(delay)
                soup = fetch_page(session, url, timeout=wcfg["request_timeout"])
                if not soup:
                    continue

                title, body = extract_article_text(soup)
                if len(body) < wcfg["min_article_chars"]:
                    logger.debug(f"Skipping short article ({len(body)} chars): {url}")
                    continue

                if not title:
                    title = url

                domain_tags = get_domain_tags(title + " " + body, config)
                quality_score = compute_web_quality(title, body, soup, config)

                raw = {
                    "url": url,
                    "title": title,
                    "body": body,
                    "site": site_name,
                }

                envelope = {
                    "source": "web",
                    "content_type": "article",
                    "domain_tags": domain_tags,
                    "quality_score": quality_score,
                    "raw": raw,
                    "scraped_at": scraped_at,
                }

                f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                count += 1

            except Exception as e:
                logger.error(f"Error scraping article {url}: {e}")

    return count


def run(config: dict) -> dict:
    setup_logging()
    wcfg = config["web"]
    output_dir = Path(wcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    session = make_session(timeout=wcfg["request_timeout"])
    delay = wcfg["request_delay_seconds"]
    summary = {"articles": 0, "by_site": {}}

    sites = wcfg["sites"]

    # Barista Hustle — WordPress pagination
    bh_cfg = sites["barista_hustle"]
    logger.info("Collecting Barista Hustle article URLs...")
    bh_urls = collect_wordpress_urls(
        session, bh_cfg["start_url"], bh_cfg["base_url"], bh_cfg["max_articles"], delay
    )
    logger.info(f"Barista Hustle: {len(bh_urls)} URLs collected, scraping...")
    bh_count = scrape_articles(session, bh_urls, "barista_hustle", config, output_dir / "barista_hustle.jsonl")
    summary["by_site"]["barista_hustle"] = bh_count
    summary["articles"] += bh_count

    # Coffee Ad Astra — generic link collection
    caa_cfg = sites["coffee_ad_astra"]
    logger.info("Collecting Coffee Ad Astra article URLs...")
    caa_urls = collect_link_collection_urls(
        session, caa_cfg["start_url"], caa_cfg["base_url"], caa_cfg["max_articles"], delay
    )
    logger.info(f"Coffee Ad Astra: {len(caa_urls)} URLs collected, scraping...")
    caa_count = scrape_articles(session, caa_urls, "coffee_ad_astra", config, output_dir / "coffee_ad_astra.jsonl")
    summary["by_site"]["coffee_ad_astra"] = caa_count
    summary["articles"] += caa_count

    # Perfect Daily Grind — category pages
    pdg_cfg = sites["perfect_daily_grind"]
    logger.info("Collecting Perfect Daily Grind article URLs...")
    pdg_urls = collect_perfect_daily_grind_urls(session, pdg_cfg, pdg_cfg["max_articles"], delay)
    logger.info(f"Perfect Daily Grind: {len(pdg_urls)} URLs collected, scraping...")
    pdg_count = scrape_articles(session, pdg_urls, "perfect_daily_grind", config, output_dir / "perfect_daily_grind.jsonl")
    summary["by_site"]["perfect_daily_grind"] = pdg_count
    summary["articles"] += pdg_count

    by_site_str = ", ".join(f"{k}: {v}" for k, v in summary["by_site"].items())
    print(f"Web complete:     {summary['articles']:,} articles ({by_site_str})")
    return summary
