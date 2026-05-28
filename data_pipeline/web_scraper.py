# data_pipeline/web_scraper.py
"""
Web scraper for coffee-focused sites.
Uses Playwright (headless Chromium) to handle JS-rendered pages and Cloudflare challenges.
Collects articles from Sprudge, Coffee Ad Astra, Perfect Daily Grind, Home-Barista, and Barista Hustle.
"""

import json
import logging
import random
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, BrowserContext

logger = logging.getLogger("web_scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

STATE_FILE = Path("training_data/state/web_state.json")


# --- State management ---

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "scraped_urls": [],
        "completed_sites": [],
        "in_progress": None,
        "last_run_at": None,
    }


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def setup_logging():
    logging.basicConfig(
        format="[web_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


@contextmanager
def make_browser_context():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1",
            },
        )
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font", "stylesheet")
            else route.continue_(),
        )
        try:
            yield context
        finally:
            context.close()
            browser.close()


def fetch_page(context: BrowserContext, url: str, timeout: int = 30000) -> Optional[BeautifulSoup]:
    page = None
    try:
        page = context.new_page()
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        html = page.content()
        return BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return None
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


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


def extract_article_text(soup: BeautifulSoup) -> tuple[str, str]:
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

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

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    body = "\n".join(lines)

    return title, body


def _is_article_url(href: str, base_parsed) -> bool:
    try:
        parsed = urlparse(href)
    except Exception:
        return False

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
    context: BrowserContext,
    start_url: str,
    base_url: str,
    max_articles: int,
    delay: float,
) -> list[str]:
    urls: set[str] = set()
    page = 1
    base_parsed = urlparse(base_url)
    consecutive_empty = 0

    while len(urls) < max_articles:
        page_url = start_url if page == 1 else start_url.rstrip("/") + f"/page/{page}/"

        logger.info(f"Collecting URLs from {page_url}")
        soup = fetch_page(context, page_url)
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
    context: BrowserContext,
    start_url: str,
    base_url: str,
    max_articles: int,
    delay: float,
) -> list[str]:
    urls: set[str] = set()
    base_parsed = urlparse(base_url)

    soup = fetch_page(context, start_url)
    if not soup:
        return []

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0]
        if _is_article_url(href, base_parsed) and href != start_url:
            urls.add(href)

    return list(urls)[:max_articles]


def collect_wordpress_category_urls(
    context: BrowserContext,
    base_url: str,
    categories: list[str],
    max_articles: int,
    delay: float,
) -> list[str]:
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
            soup = fetch_page(context, page_url)
            if not soup:
                break

            found_on_page = 0
            for a in soup.find_all("a", href=True):
                href = urljoin(base_url, a["href"]).split("#")[0]
                if _is_article_url(href, base_parsed) and href not in urls:
                    urls.add(href)
                    found_on_page += 1

            if found_on_page == 0 and page > 1:
                break

            page += 1
            time.sleep(delay + random.uniform(0, 1))

    return list(urls)[:max_articles]


def collect_forum_thread_urls(
    context: BrowserContext,
    index_urls: list[str],
    base_url: str,
    max_threads: int,
    delay: float,
    min_replies: int = 10,
) -> list[str]:
    """
    Collect thread URLs from a forum index.
    Only threads with >= min_replies are collected (high-signal discussions only).
    Similar extraction logic to Reddit: thread title + top posts.
    """
    thread_urls: set[str] = set()
    base_parsed = urlparse(base_url)

    for index_url in index_urls:
        if len(thread_urls) >= max_threads:
            break

        page = 1
        consecutive_empty = 0

        while len(thread_urls) < max_threads:
            page_url = index_url if page == 1 else index_url.rstrip("/") + f"?page={page}"
            logger.info(f"Collecting forum thread URLs from {page_url}")
            soup = fetch_page(context, page_url)
            if not soup:
                break

            found_on_page = 0

            # Look for thread rows — common forum patterns
            # Try phpBB-style structure (Home-Barista runs phpBB)
            thread_links = []

            # phpBB: <a class="topictitle"> or links in .forumrow / .topiclist
            for a in soup.select("a.topictitle, .topictitle a, td.topic_title a"):
                href = urljoin(base_url, a.get("href", "")).split("#")[0]
                if href and href not in thread_urls:
                    thread_links.append((href, a))

            # Fall back: any link that looks like a thread (has /viewtopic or /t/ pattern)
            if not thread_links:
                for a in soup.find_all("a", href=True):
                    href = urljoin(base_url, a["href"]).split("#")[0]
                    parsed = urlparse(href)
                    if parsed.netloc == base_parsed.netloc and (
                        "viewtopic" in parsed.path or
                        "/t/" in parsed.path or
                        parsed.query.startswith("t=")
                    ):
                        if href not in thread_urls:
                            thread_links.append((href, a))

            # Check reply count where possible — look for adjacent reply counts
            for href, a_tag in thread_links:
                if len(thread_urls) >= max_threads:
                    break

                # Try to find reply count in sibling/parent cells
                replies = None
                parent = a_tag.find_parent("tr") or a_tag.find_parent("li")
                if parent:
                    for cell in parent.find_all(["td", "span", "div"]):
                        text = cell.get_text(strip=True)
                        if text.isdigit():
                            try:
                                replies = int(text)
                                break
                            except ValueError:
                                pass

                # If we can't determine reply count, include it (can't know without fetching)
                if replies is None or replies >= min_replies:
                    thread_urls.add(href)
                    found_on_page += 1

            if found_on_page == 0:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
            else:
                consecutive_empty = 0

            page += 1
            time.sleep(delay + random.uniform(0, 1))

    return list(thread_urls)[:max_threads]


def extract_forum_thread_text(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract thread title and concatenated top posts from a forum thread page."""
    title = ""

    # Title
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()

    # Strip boilerplate
    for selector in ["nav", "header", "footer", ".advertisement", "script", "style", ".signature"]:
        for el in soup.select(selector):
            el.decompose()

    # Collect post bodies — phpBB uses .postbody or div.content inside .post
    posts = []
    for selector in [".postbody", ".post-content", ".content", ".message"]:
        found = soup.select(selector)
        if found:
            for el in found:
                text = el.get_text(separator="\n", strip=True)
                if text and len(text) > 30:
                    posts.append(text)
            break

    body = "\n\n".join(posts) if posts else soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    body = "\n".join(lines)

    return title, body


def scrape_articles(
    context: BrowserContext,
    urls: list[str],
    site_name: str,
    config: dict,
    output_path: Path,
    scraped_urls_set: set,
    state: dict,
    is_forum: bool = False,
) -> int:
    wcfg = config["web"]
    delay = wcfg["request_delay_seconds"]
    timeout = wcfg["request_timeout"]
    min_chars = wcfg["min_article_chars"]
    scraped_at = datetime.now(tz=timezone.utc).isoformat()
    count = 0

    with open(output_path, "a", encoding="utf-8") as f:
        for i, url in enumerate(urls):
            if url in scraped_urls_set:
                logger.debug(f"Skipping already-scraped URL: {url}")
                continue

            try:
                time.sleep(delay + random.uniform(0, 1.5))
                soup = fetch_page(context, url, timeout=timeout * 1000)
                if not soup:
                    continue

                if is_forum:
                    title, body = extract_forum_thread_text(soup)
                    content_type = "forum_thread"
                else:
                    title, body = extract_article_text(soup)
                    content_type = "article"

                if len(body) < min_chars:
                    logger.debug(f"Skipping short content ({len(body)} chars): {url}")
                    scraped_urls_set.add(url)
                    state["scraped_urls"] = list(scraped_urls_set)
                    _save_state(state)
                    continue

                if not title:
                    title = url

                domain_tags = get_domain_tags(title + " " + body, config)
                quality_score = compute_web_quality(title, body, soup, config)

                envelope = {
                    "source": "web",
                    "content_type": content_type,
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

                # Update state after each successful record
                scraped_urls_set.add(url)
                state["scraped_urls"] = list(scraped_urls_set)
                state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
                _save_state(state)

                if count % 25 == 0:
                    logger.info(f"{site_name}: {count} articles scraped so far...")

            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")

    return count


def run(config: dict, fresh: bool = False) -> dict:
    setup_logging()
    wcfg = config["web"]
    output_dir = Path(wcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load or reset state
    state = {"scraped_urls": [], "completed_sites": [], "in_progress": None, "last_run_at": None}
    if not fresh:
        state = _load_state()
        if state.get("scraped_urls") or state.get("completed_sites"):
            logger.info(
                f"Resuming from checkpoint: {len(state['scraped_urls'])} URLs already scraped, "
                f"{len(state['completed_sites'])} sites complete"
            )
    else:
        logger.info("--fresh flag set — ignoring existing state")

    scraped_urls_set: set[str] = set(state.get("scraped_urls", []))
    completed_sites: set[str] = set(state.get("completed_sites", []))

    delay = wcfg["request_delay_seconds"]
    summary = {"articles": 0, "by_site": {}}
    sites = wcfg["sites"]

    with make_browser_context() as context:

        # Sprudge — WordPress pagination
        if "sprudge" not in completed_sites:
            state["in_progress"] = "sprudge"
            _save_state(state)
            sp_cfg = sites["sprudge"]
            logger.info("Collecting Sprudge article URLs...")
            sp_urls = collect_wordpress_urls(
                context, sp_cfg["start_url"], sp_cfg["base_url"], sp_cfg["max_articles"], delay
            )
            logger.info(f"Sprudge: {len(sp_urls)} URLs collected, scraping...")
            sp_count = scrape_articles(
                context, sp_urls, "sprudge", config,
                output_dir / "sprudge.jsonl", scraped_urls_set, state
            )
            summary["by_site"]["sprudge"] = sp_count
            summary["articles"] += sp_count
            completed_sites.add("sprudge")
            state["completed_sites"] = list(completed_sites)
            state["in_progress"] = None
            _save_state(state)
        else:
            logger.info("Sprudge: already completed, skipping")

        # Coffee Ad Astra — single-page link collection
        if "coffee_ad_astra" not in completed_sites:
            state["in_progress"] = "coffee_ad_astra"
            _save_state(state)
            caa_cfg = sites["coffee_ad_astra"]
            logger.info("Collecting Coffee Ad Astra article URLs...")
            caa_urls = collect_link_collection_urls(
                context, caa_cfg["start_url"], caa_cfg["base_url"], caa_cfg["max_articles"], delay
            )
            logger.info(f"Coffee Ad Astra: {len(caa_urls)} URLs collected, scraping...")
            caa_count = scrape_articles(
                context, caa_urls, "coffee_ad_astra", config,
                output_dir / "coffee_ad_astra.jsonl", scraped_urls_set, state
            )
            summary["by_site"]["coffee_ad_astra"] = caa_count
            summary["articles"] += caa_count
            completed_sites.add("coffee_ad_astra")
            state["completed_sites"] = list(completed_sites)
            state["in_progress"] = None
            _save_state(state)
        else:
            logger.info("Coffee Ad Astra: already completed, skipping")

        # Perfect Daily Grind — WordPress category pagination
        if "perfect_daily_grind" not in completed_sites:
            state["in_progress"] = "perfect_daily_grind"
            _save_state(state)
            pdg_cfg = sites["perfect_daily_grind"]
            logger.info("Collecting Perfect Daily Grind article URLs...")
            pdg_urls = collect_wordpress_category_urls(
                context, pdg_cfg["base_url"], pdg_cfg["categories"], pdg_cfg["max_articles"], delay
            )
            logger.info(f"Perfect Daily Grind: {len(pdg_urls)} URLs collected, scraping...")
            pdg_count = scrape_articles(
                context, pdg_urls, "perfect_daily_grind", config,
                output_dir / "perfect_daily_grind.jsonl", scraped_urls_set, state
            )
            summary["by_site"]["perfect_daily_grind"] = pdg_count
            summary["articles"] += pdg_count
            completed_sites.add("perfect_daily_grind")
            state["completed_sites"] = list(completed_sites)
            state["in_progress"] = None
            _save_state(state)
        else:
            logger.info("Perfect Daily Grind: already completed, skipping")

        # Home-Barista — forum scraper
        if "home_barista" in sites and "home_barista" not in completed_sites:
            state["in_progress"] = "home_barista"
            _save_state(state)
            hb_cfg = sites["home_barista"]
            base_url = "https://www.home-barista.com"
            logger.info("Collecting Home-Barista forum thread URLs...")
            hb_urls = collect_forum_thread_urls(
                context,
                hb_cfg.get("article_list_urls", []),
                base_url,
                hb_cfg.get("max_articles", 500),
                delay,
                min_replies=hb_cfg.get("min_replies", 10),
            )
            logger.info(f"Home-Barista: {len(hb_urls)} thread URLs collected, scraping...")
            hb_count = scrape_articles(
                context, hb_urls, "home_barista", config,
                output_dir / "home_barista.jsonl", scraped_urls_set, state,
                is_forum=True,
            )
            summary["by_site"]["home_barista"] = hb_count
            summary["articles"] += hb_count
            completed_sites.add("home_barista")
            state["completed_sites"] = list(completed_sites)
            state["in_progress"] = None
            _save_state(state)
        else:
            if "home_barista" in completed_sites:
                logger.info("Home-Barista: already completed, skipping")

        # Barista Hustle Pro — WordPress knowledgebase
        if "barista_hustle_pro" in sites and "barista_hustle_pro" not in completed_sites:
            state["in_progress"] = "barista_hustle_pro"
            _save_state(state)
            bh_cfg = sites["barista_hustle_pro"]
            logger.info("Collecting Barista Hustle knowledgebase URLs...")
            bh_urls = collect_wordpress_urls(
                context,
                bh_cfg["start_url"],
                bh_cfg["base_url"],
                bh_cfg.get("max_articles", 500),
                delay,
            )
            logger.info(f"Barista Hustle: {len(bh_urls)} URLs collected, scraping...")
            bh_count = scrape_articles(
                context, bh_urls, "barista_hustle_pro", config,
                output_dir / "barista_hustle_pro.jsonl", scraped_urls_set, state
            )
            summary["by_site"]["barista_hustle_pro"] = bh_count
            summary["articles"] += bh_count
            completed_sites.add("barista_hustle_pro")
            state["completed_sites"] = list(completed_sites)
            state["in_progress"] = None
            _save_state(state)
        else:
            if "barista_hustle_pro" in completed_sites:
                logger.info("Barista Hustle Pro: already completed, skipping")

    by_site_str = ", ".join(f"{k}: {v}" for k, v in summary["by_site"].items())
    print(f"Web complete:     {summary['articles']:,} articles ({by_site_str})")
    return summary


if __name__ == "__main__":
    cfg = json.loads((Path(__file__).parent / "config.json").read_text())
    run(cfg)
