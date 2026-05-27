# data_pipeline/reddit_scraper.py
"""
Reddit scraper using direct JSON endpoints — no API credentials required.
Reddit exposes <url>.json on every public listing. Respects rate limits via
a 2-second delay between requests and a descriptive User-Agent header.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("reddit_scraper")

_SESSION: Optional[requests.Session] = None

REDDIT_BASE = "https://www.reddit.com"
REQUEST_DELAY = 2.0  # seconds between requests — stay well under Reddit's rate limit


def setup_logging():
    logging.basicConfig(
        format="[reddit_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


def get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            # Reddit requires a descriptive User-Agent or it returns 429/403
            "User-Agent": "coffee-pipeline/1.0 (training data collector; github.com/JPerreault01/Coffee-Bean-Scraper)"
        })
    return _SESSION


def _get(url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
    """GET a Reddit JSON endpoint with retry logic."""
    session = get_session()
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, params=params, timeout=20)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error (attempt {attempt + 1}/{retries}): {url} — {e}")
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    logger.error(f"Failed after {retries} attempts: {url}")
    return None


def get_domain_tags(text: str, config: dict) -> list[str]:
    text_lower = text.lower()
    return [tag for tag, keywords in config["domain_tags"].items()
            if any(kw.lower() in text_lower for kw in keywords)]


def compute_reddit_quality(post_data: dict, config: dict) -> float:
    qcfg = config["reddit"]["quality"]
    score_norm = min(post_data["score"], qcfg["score_normalize_cap"]) / qcfg["score_normalize_cap"]
    comment_norm = min(post_data["num_comments"], qcfg["comment_normalize_cap"]) / qcfg["comment_normalize_cap"]
    quality = score_norm * qcfg["score_weight"] + comment_norm * qcfg["comment_weight"]

    body = post_data.get("body", "")
    if len(body) < qcfg["short_body_penalty_threshold"]:
        quality = max(0.0, quality - qcfg["short_body_penalty"])

    title_lower = post_data["title"].lower()
    if any(kw in title_lower for kw in qcfg["boost_keywords"]):
        quality = min(1.0, quality + 0.1)

    return round(quality, 4)


def _extract_comments_from_listing(listing: list, depth: int, config: dict) -> list[dict]:
    """Recursively extract comments from a Reddit comment listing."""
    rcfg = config["reddit"]
    comments = []

    for item in listing:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        data = item.get("data", {})

        if kind == "more":
            # Skip "load more" stubs
            continue

        if kind != "t1":
            continue

        body = data.get("body", "")
        if body in ("[deleted]", "[removed]") or not body:
            continue
        if len(body) < rcfg["min_comment_chars"]:
            continue

        comment = {
            "id": data.get("id", ""),
            "author": data.get("author", "[deleted]"),
            "body": body,
            "score": data.get("score", 0),
            "replies": [],
        }

        # Recurse into replies
        if depth < rcfg["comment_reply_depth"]:
            replies_data = data.get("replies")
            if isinstance(replies_data, dict):
                reply_children = replies_data.get("data", {}).get("children", [])
                reply_children_sorted = sorted(
                    [c for c in reply_children if isinstance(c, dict) and c.get("kind") == "t1"],
                    key=lambda c: c.get("data", {}).get("score", 0),
                    reverse=True,
                )
                for reply in reply_children_sorted[: rcfg["max_replies_per_comment"]]:
                    extracted = _extract_comments_from_listing([reply], depth + 1, config)
                    comment["replies"].extend(extracted)

        comments.append(comment)

    return comments


def fetch_comments_for_post(post_id: str, subreddit: str, config: dict) -> list[dict]:
    """Fetch top comments for a post via the post's JSON endpoint."""
    rcfg = config["reddit"]
    url = f"{REDDIT_BASE}/r/{subreddit}/comments/{post_id}.json"
    data = _get(url, params={"limit": rcfg["max_comments_per_post"], "sort": "top", "depth": rcfg["comment_reply_depth"]})

    if not data or not isinstance(data, list) or len(data) < 2:
        return []

    # data[0] = post, data[1] = comments listing
    comment_children = data[1].get("data", {}).get("children", [])

    # Sort top-level comments by score descending
    top_level = sorted(
        [c for c in comment_children if isinstance(c, dict) and c.get("kind") == "t1"],
        key=lambda c: c.get("data", {}).get("score", 0),
        reverse=True,
    )

    return _extract_comments_from_listing(top_level[: rcfg["max_comments_per_post"]], depth=1, config=config)


def fetch_listing(subreddit: str, sort: str, params: dict, config: dict, seen_ids: set) -> list[dict]:
    """
    Fetch posts from a subreddit listing endpoint (top/hot/new).
    Paginates using Reddit's `after` cursor until limit is reached or results dry up.
    """
    rcfg = config["reddit"]
    posts = []
    after = None
    page_limit = params.get("limit", 100)
    fetched = 0
    max_fetch = params.get("max_fetch", 500)

    while fetched < max_fetch:
        url = f"{REDDIT_BASE}/r/{subreddit}/{sort}.json"
        req_params = {"limit": min(100, max_fetch - fetched), "raw_json": 1}
        if params.get("t"):
            req_params["t"] = params["t"]
        if after:
            req_params["after"] = after

        data = _get(url, params=req_params)
        if not data:
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for child in children:
            if child.get("kind") != "t3":
                continue
            post = child.get("data", {})
            pid = post.get("id", "")

            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            score = post.get("score", 0)
            num_comments = post.get("num_comments", 0)
            body = post.get("selftext", "") or ""

            if score < rcfg["min_score"]:
                continue
            if num_comments < rcfg["min_comments"]:
                continue
            if len(body) < rcfg["short_post_min_chars"] and score < rcfg["short_post_score_threshold"]:
                continue
            if body in ("[deleted]", "[removed]"):
                continue

            posts.append({
                "post_id": pid,
                "subreddit": subreddit,
                "title": post.get("title", ""),
                "body": body,
                "url": post.get("url", ""),
                "score": score,
                "num_comments": num_comments,
                "created_utc": datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=timezone.utc
                ).isoformat(),
            })

        fetched += len(children)
        after = data.get("data", {}).get("after")
        if not after:
            break

    return posts


def fetch_subreddit_posts(subreddit: str, config: dict) -> list[dict]:
    seen_ids: set[str] = set()
    posts: list[dict] = []

    fetch_jobs = [
        ("top", {"t": "year", "max_fetch": 500}),
        ("top", {"t": "all",  "max_fetch": 500}),
        ("hot", {"max_fetch": 200}),
    ]

    for sort, params in fetch_jobs:
        logger.info(f"r/{subreddit}: fetching {sort} (t={params.get('t', 'n/a')})")
        batch = fetch_listing(subreddit, sort, params, config, seen_ids)
        posts.extend(batch)
        logger.info(f"r/{subreddit}: {len(batch)} new posts from {sort}, {len(posts)} total so far")

    return posts


def run(config: dict) -> dict:
    setup_logging()
    rcfg = config["reddit"]
    output_dir = Path(rcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {"posts": 0, "comments": 0, "subreddits": {}}
    scraped_at = datetime.now(tz=timezone.utc).isoformat()

    for subreddit_name in rcfg["subreddits"]:
        logger.info(f"Starting r/{subreddit_name}")
        posts = fetch_subreddit_posts(subreddit_name, config)
        logger.info(f"r/{subreddit_name}: {len(posts)} posts after filtering — fetching comments...")

        out_path = output_dir / f"{subreddit_name}.jsonl"
        post_count = 0
        comment_count = 0

        with open(out_path, "w", encoding="utf-8") as f:
            for post_data in posts:
                try:
                    comments = fetch_comments_for_post(post_data["post_id"], subreddit_name, config)
                    post_data["comments"] = comments

                    text = post_data["title"] + " " + post_data["body"]
                    domain_tags = get_domain_tags(text, config)
                    quality_score = compute_reddit_quality(post_data, config)

                    envelope = {
                        "source": "reddit",
                        "content_type": "discussion",
                        "domain_tags": domain_tags,
                        "quality_score": quality_score,
                        "raw": post_data,
                        "scraped_at": scraped_at,
                    }

                    f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                    post_count += 1
                    comment_count += len(comments)

                except Exception as e:
                    logger.error(f"Error processing post {post_data.get('post_id', '?')}: {e}")

        summary["subreddits"][subreddit_name] = {"posts": post_count, "comments": comment_count}
        summary["posts"] += post_count
        summary["comments"] += comment_count
        logger.info(f"r/{subreddit_name}: wrote {post_count} posts, {comment_count} comments → {out_path}")

    print(f"Reddit complete:  {summary['posts']:,} posts | {summary['comments']:,} comments")
    return summary


if __name__ == "__main__":
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).parent / "config.json").read_text())
    run(cfg)
