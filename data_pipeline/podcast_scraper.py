# data_pipeline/podcast_scraper.py
"""
RSS-based podcast scraper for coffee-focused shows.
Fetches episode titles, descriptions, and show notes from RSS feeds.
No transcripts — metadata and text only.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    import xml.etree.ElementTree as ET

logger = logging.getLogger("podcast_scraper")

STATE_FILE = Path("training_data/state/podcast_state.json")


def setup_logging():
    logging.basicConfig(
        format="[podcast_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scraped_urls": []}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_domain_tags(text: str, config: dict) -> list:
    text_lower = text.lower()
    return [tag for tag, keywords in config["domain_tags"].items()
            if any(kw.lower() in text_lower for kw in keywords)]


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_feed_feedparser(rss_url: str) -> list:
    feed = feedparser.parse(rss_url)
    episodes = []
    for entry in feed.entries:
        title = getattr(entry, "title", "") or ""
        description = getattr(entry, "summary", "") or ""
        pub_date = getattr(entry, "published", "") or ""
        url = getattr(entry, "link", "") or ""

        content = getattr(entry, "content", None)
        show_notes = ""
        if content:
            show_notes = content[0].get("value", "") if isinstance(content[0], dict) else ""
        if not show_notes:
            show_notes = description

        episodes.append({
            "title": _strip_html(title),
            "description": _strip_html(description),
            "pub_date": pub_date,
            "url": url,
            "show_notes": _strip_html(show_notes),
        })
    return episodes


def _parse_feed_stdlib(xml_text: str) -> list:
    root = ET.fromstring(xml_text)
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    channel = root.find("channel")
    if channel is None:
        return []

    episodes = []
    for item in channel.findall("item"):
        title = item.findtext("title") or ""
        description = item.findtext("description") or ""
        pub_date = item.findtext("pubDate") or ""
        url = item.findtext("link") or ""
        enclosure = item.find("enclosure")
        if not url and enclosure is not None:
            url = enclosure.get("url", "")

        content_encoded = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        show_notes = content_encoded.text if content_encoded is not None else description

        episodes.append({
            "title": _strip_html(title),
            "description": _strip_html(description),
            "pub_date": pub_date,
            "url": url,
            "show_notes": _strip_html(show_notes or ""),
        })
    return episodes


def fetch_episodes(feed_name: str, rss_url: str, max_episodes: int) -> list:
    try:
        if HAS_FEEDPARSER:
            return _parse_feed_feedparser(rss_url)[:max_episodes]
        else:
            resp = requests.get(rss_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            return _parse_feed_stdlib(resp.text)[:max_episodes]
    except Exception as e:
        logger.error(f"{feed_name}: failed to fetch/parse feed — {e}")
        return []


def run(config: dict, fresh: bool = False) -> dict:
    setup_logging()
    pcfg = config["podcasts"]
    output_dir = Path(pcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    state = {"scraped_urls": []}
    if not fresh:
        state = _load_state()
    scraped_urls: set = set(state.get("scraped_urls", []))

    min_chars = pcfg["min_text_chars"]
    max_episodes = pcfg["max_episodes_per_feed"]
    scraped_at = datetime.now(tz=timezone.utc).isoformat()

    summary = {"episodes": 0, "by_feed": {}}

    for feed_key, feed_cfg in pcfg["feeds"].items():
        feed_name = feed_cfg["name"]
        rss_url = feed_cfg["rss_url"]
        authority_weight = feed_cfg.get("authority_weight", 0.8)

        logger.info(f"{feed_name}: fetching RSS feed...")
        episodes = fetch_episodes(feed_name, rss_url, max_episodes)
        logger.info(f"{feed_name}: {len(episodes)} episodes found")

        output_path = output_dir / f"{feed_name}.jsonl"
        count = 0

        with open(output_path, "a", encoding="utf-8") as f:
            for ep in episodes:
                url = ep["url"]
                if url in scraped_urls:
                    continue

                combined_text = ep["description"] + " " + ep["show_notes"]
                if len(combined_text.strip()) < min_chars:
                    scraped_urls.add(url)
                    continue

                quality_score = round(min(len(ep["description"]) / 2000, 1.0), 4)

                domain_tags = get_domain_tags(
                    ep["title"] + " " + ep["description"] + " " + ep["show_notes"],
                    config,
                )

                envelope = {
                    "source": "podcast",
                    "content_type": "episode_notes",
                    "domain_tags": domain_tags,
                    "quality_score": quality_score,
                    "raw": {
                        "feed_name": feed_name,
                        "title": ep["title"],
                        "description": ep["description"],
                        "pub_date": ep["pub_date"],
                        "url": url,
                    },
                    "scraped_at": scraped_at,
                }

                f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                count += 1
                scraped_urls.add(url)

        state["scraped_urls"] = list(scraped_urls)
        _save_state(state)

        summary["by_feed"][feed_name] = count
        summary["episodes"] += count
        logger.info(f"{feed_name}: {count} episodes written")

    by_feed_str = ", ".join(f"{k}: {v}" for k, v in summary["by_feed"].items())
    print(f"Podcasts complete: {summary['episodes']:,} episodes ({by_feed_str})")
    return summary


if __name__ == "__main__":
    cfg = json.loads((Path(__file__).parent / "config.json").read_text())
    run(cfg)
