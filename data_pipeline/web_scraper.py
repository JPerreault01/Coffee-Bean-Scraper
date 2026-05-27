"""
Web scraper for coffee-focused sites.
Supports WordPress blogs, link collections, and forum types.
Supports checkpointing: resumes interrupted runs from last saved state.
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

STATE_PATH = Path("training_data/state/web_state.json")


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


# --- State management ---

def load_state(fresh: bool = False) -> dict:
    if not fresh and STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {
        "scraped_urls": [],
        "completed_sites": [],
        "in_progress": None,
        "last_run_at": None,
    }


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def add_scraped_url(state: dict, url: str):
    if url not in state["scraped_urls"]:
        state["scraped_urls"].append(url)
    save_state(state)


# --- Helpers ---

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
        "[class*='cookie']", "[class*='popup']",
        "script", "style", "noscript",
    ]:
        for el in soup.select(selector):
            el.decompose()

    article = None
    for selector in ["article", ".entry-content", ".post-content", ".article-content", "main"]:
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


# --- URL collectors ---

def collect_wordpress_urls(session: requests.Session, start_url: str, base_url: str, max_articles: int, delay: float) -> list[str]:
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


def collect_forum_urls(session: requests.Session, site_cfg: dict, delay: float) -> list[dict]:
    """Collect forum thread URLs with reply counts from a forum index page."""
    min_replies = site_cfg.get("min_replies", 10)
    max_articles = site_cfg.get("max_articles", 500)
    threads = []

    for list_url in site_cfg["article_list_urls"]:
        logger.info(f"Collecting forum thread URLs from {list_url}")
        base_parsed = urlparse(list_url)
        base_url = f"{base_parsed.scheme}://{base_parsed.netloc}"

        soup = fetch_page(session, list_url)
        if not soup:
            continue

        # Follow sub-forum links one level deep
        subforum_links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            parsed = urlparse(href)
            if parsed.netloc == base_parsed.netloc and parsed.path != base_parsed.path:
                subforum_links.append(href)
        subforum_links = list(dict.fromkeys(subforum_links))[:50]

        pages_to_scan = [list_url] + subforum_links

        for page_url in pages_to_scan:
            if len(threads) >= max_articles:
                break
            time.sleep(delay)
            page_soup = fetch_page(session, page_url)
            if not page_soup:
                continue

            for row in page_soup.find_all(["tr", "li", "div"]):
                if len(threads) >= max_articles:
                    break

                # Look for reply count indicator
                reply_count = 0
                for cell in row.find_all(["td", "span", "div"]):
                    text = cell.get_text(strip=True)
                    if text.isdigit():
                        candidate = int(text)
                        if candidate > reply_count:
                            reply_count = candidate

                if reply_count < min_replies:
                    continue

                link = row.find("a", href=True)
                if not link:
                    continue

                href = urljoin(base_url, link["href"])
                parsed = urlparse(href)
                if parsed.netloc != base_parsed.netloc:
                    continue

                if not any(t["url"] == href for t in threads):
                    threads.append({"url": href, "reply_count": reply_count})

    return threads[:max_articles]


def scrape_forum_thread(session: requests.Session, thread_info: dict, site_name: str, config: dict) -> Optional[dict]:
    """Extract title and top posts from a forum thread."""
    wcfg = config["web"]
    url = thread_info["url"]

    soup = fetch_page(session, url, timeout=wcfg["request_timeout"])
    if not soup:
        return None

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Strip boilerplate
    for selector in ["nav", "header", "footer", "aside", "script", "style", "noscript",
                     ".sidebar", ".widget", ".advertisement", ".ad"]:
        for el in soup.select(selector):
            el.decompose()

    # Collect post bodies — look for common forum post containers
    post_texts = []
    for selector in [".postbody", ".post-content", ".message-body", ".bbWrapper",
                     "[class*='post']", "[class*='message']"]:
        posts = soup.select(selector)
        if posts:
            for post in posts[:20]:
                text = post.get_text(separator=" ", strip=True)
                if len(text) >= wcfg["min_article_chars"] // 4:
                    post_texts.append(text)
            break

    if not post_texts:
        # Fallback: grab all substantial paragraphs
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 80:
                post_texts.append(text)

    body = "\n\n".join(post_texts)
    if len(body) < wcfg["min_article_chars"]:
        return None

    return {
        "url": url,
        "title": title,
        "body": body,
        "site": site_name,
        "reply_count": thread_info.get("reply_count", 0),
    }


# --- Article scraper ---

def scrape_articles(
    session: requests.Session,
    urls: list[str],
    site_name: str,
    config: dict,
    output_path: Path,
    state: dict,
    scraped_urls: set,
) -> int:
    wcfg = config["web"]
    delay = wcfg["request_delay_seconds"]
    scraped_at = datetime.now(tz=timezone.utc).isoformat()
    count = 0

    with open(output_path, "a", encoding="utf-8") as f:
        for url in urls:
            if url in scraped_urls:
                logger.debug(f"Skipping already-scraped URL: {url}")
                continue
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

                add_scraped_url(state, url)
                scraped_urls.add(url)

            except Exception as e:
                logger.error(f"Error scraping article {url}: {e}")

    return count


def scrape_forum_site(
    session: requests.Session,
    site_name: str,
    site_cfg: dict,
    config: dict,
    output_path: Path,
    state: dict,
    scraped_urls: set,
    delay: float,
) -> int:
    threads = collect_forum_urls(session, site_cfg, delay)
    logger.info(f"{site_name}: {len(threads)} qualifying threads found")

    scraped_at = datetime.now(tz=timezone.utc).isoformat()
    count = 0

    with open(output_path, "a", encoding="utf-8") as f:
        for thread_info in threads:
            url = thread_info["url"]
            if url in scraped_urls:
                continue
            try:
                time.sleep(delay)
                raw = scrape_forum_thread(session, thread_info, site_name, config)
                if not raw:
                    continue

                domain_tags = get_domain_tags(raw["title"] + " " + raw["body"], config)
                soup_stub = BeautifulSoup("", "lxml")
                quality_score = compute_web_quality(raw["title"], raw["body"], soup_stub, config)

                envelope = {
                    "source": "web",
                    "content_type": "forum_thread",
                    "domain_tags": domain_tags,
                    "quality_score": quality_score,
                    "raw": raw,
                    "scraped_at": scraped_at,
                }

                f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                count += 1

                add_scraped_url(state, url)
                scraped_urls.add(url)

            except Exception as e:
                logger.error(f"Error scraping forum thread {url}: {e}")

    return count


def run(config: dict, fresh: bool = False) -> dict:
    setup_logging()
    wcfg = config["web"]
    output_dir = Path(wcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    session = make_session(timeout=wcfg["request_timeout"])
    delay = wcfg["request_delay_seconds"]

    state = load_state(fresh=fresh)
    scraped_urls = set(state["scraped_urls"])
    completed_sites = set(state["completed_sites"])

    summary = {"articles": 0, "by_site": {}}
    sites = wcfg["sites"]

    def _run_site(site_name: str):
        if site_name in completed_sites:
            logger.info(f"{site_name}: already completed, skipping")
            return 0

        state["in_progress"] = site_name
        save_state(state)

        site_cfg = sites[site_name]
        out_path = output_dir / f"{site_name}.jsonl"
        site_type = site_cfg.get("type") or site_cfg.get("pagination_type", "wordpress")

        if site_type == "forum":
            count = scrape_forum_site(session, site_name, site_cfg, config, out_path, state, scraped_urls, delay)
        elif site_name == "perfect_daily_grind":
            urls = collect_perfect_daily_grind_urls(session, site_cfg, site_cfg.get("max_articles", 500), delay)
            logger.info(f"{site_name}: {len(urls)} URLs collected, scraping...")
            count = scrape_articles(session, urls, site_name, config, out_path, state, scraped_urls)
        elif site_type == "link_collection":
            urls = collect_link_collection_urls(
                session, site_cfg["start_url"], site_cfg["base_url"], site_cfg.get("max_articles", 500), delay
            )
            logger.info(f"{site_name}: {len(urls)} URLs collected, scraping...")
            count = scrape_articles(session, urls, site_name, config, out_path, state, scraped_urls)
        else:
            urls = collect_wordpress_urls(
                session, site_cfg["start_url"], site_cfg["base_url"], site_cfg.get("max_articles", 500), delay
            )
            logger.info(f"{site_name}: {len(urls)} URLs collected, scraping...")
            count = scrape_articles(session, urls, site_name, config, out_path, state, scraped_urls)

        state["completed_sites"].append(site_name)
        completed_sites.add(site_name)
        save_state(state)

        logger.info(f"{site_name}: {count} articles written → {out_path}")
        return count

    for site_name in sites:
        count = _run_site(site_name)
        summary["by_site"][site_name] = count
        summary["articles"] += count

    state["in_progress"] = None
    state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
    save_state(state)

    by_site_str = ", ".join(f"{k}: {v}" for k, v in summary["by_site"].items())
    print(f"Web complete:     {summary['articles']:,} articles ({by_site_str})")
    return summary
