# data_pipeline/reddit_scraper.py
"""
Reddit scraper using direct JSON endpoints — no API credentials required.

Anti-ban measures:
  - Randomized delays with jitter (never a fixed pattern)
  - User-Agent rotation across realistic desktop browser strings
  - Exponential backoff with jitter on errors and rate limits
  - Circuit breaker: pauses the whole run after N consecutive failures
  - Per-subreddit cooldown to avoid burst patterns
  - Retry-After header respected on 429s
  - Connection errors handled separately from HTTP errors
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("reddit_scraper")

REDDIT_BASE = "https://www.reddit.com"

# --- Timing constants (all in seconds) ---
DELAY_MIN = 2.0          # minimum wait between any two requests
DELAY_MAX = 5.0          # maximum wait (randomized in this range)
SUBREDDIT_BREAK_MIN = 8  # pause between subreddits
SUBREDDIT_BREAK_MAX = 15
CIRCUIT_BREAK_THRESHOLD = 5   # consecutive failures before pausing
CIRCUIT_BREAK_PAUSE = 120     # how long to pause when circuit breaks (2 min)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_consecutive_failures = 0

STATE_FILE = Path("training_data/state/reddit_state.json")


# --- State management ---

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "scraped_post_ids": [],
        "completed_subreddits": [],
        "in_progress": None,
        "last_run_at": None,
    }


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_comment_limit(num_comments: int, tiers: list[dict]) -> int:
    """Return max comments to extract based on thread size tiers."""
    for tier in sorted(tiers, key=lambda t: t["min_thread_comments"], reverse=True):
        if num_comments >= tier["min_thread_comments"]:
            return tier["max_extract"]
    return tiers[-1]["max_extract"]


# --- HTTP helpers ---

def setup_logging():
    logging.basicConfig(
        format="[reddit_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    })
    return session


def _jitter_sleep(min_s: float, max_s: float):
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Sleeping {delay:.1f}s")
    time.sleep(delay)


def _backoff_sleep(attempt: int, base: float = 3.0, cap: float = 60.0):
    ceiling = min(cap, base * (2 ** attempt))
    delay = random.uniform(1.0, ceiling)
    logger.info(f"Backoff: sleeping {delay:.1f}s (attempt {attempt + 1})")
    time.sleep(delay)


def _get(url: str, params: dict = None, retries: int = 4) -> Optional[dict]:
    global _consecutive_failures

    if _consecutive_failures >= CIRCUIT_BREAK_THRESHOLD:
        logger.warning(
            f"Circuit breaker tripped ({_consecutive_failures} consecutive failures) — "
            f"pausing {CIRCUIT_BREAK_PAUSE}s before retrying"
        )
        time.sleep(CIRCUIT_BREAK_PAUSE)
        _consecutive_failures = 0

    for attempt in range(retries):
        session = _make_session()
        _jitter_sleep(DELAY_MIN, DELAY_MAX)

        try:
            resp = session.get(url, params=params, timeout=20)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                wait = retry_after + random.uniform(5, 15)
                logger.warning(f"429 rate limit — waiting {wait:.0f}s (Retry-After: {retry_after}s)")
                time.sleep(wait)
                _consecutive_failures += 1
                continue

            if resp.status_code == 403:
                logger.warning(f"403 forbidden — {url} (possible block, backing off)")
                _backoff_sleep(attempt)
                _consecutive_failures += 1
                continue

            if resp.status_code == 503:
                logger.warning(f"503 service unavailable — {url} (Reddit overloaded)")
                _backoff_sleep(attempt, base=10.0)
                _consecutive_failures += 1
                continue

            resp.raise_for_status()
            data = resp.json()
            _consecutive_failures = 0
            return data

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error (attempt {attempt + 1}/{retries}): {e}")
            _consecutive_failures += 1
            _backoff_sleep(attempt)

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout (attempt {attempt + 1}/{retries}): {url}")
            _consecutive_failures += 1
            _backoff_sleep(attempt)

        except requests.exceptions.JSONDecodeError:
            logger.warning(f"Invalid JSON response from {url} — skipping")
            _consecutive_failures += 1
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error (attempt {attempt + 1}/{retries}): {url} — {e}")
            _consecutive_failures += 1
            _backoff_sleep(attempt)

    logger.error(f"Giving up after {retries} attempts: {url}")
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
    rcfg = config["reddit"]
    comments = []

    for item in listing:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        data = item.get("data", {})

        if kind in ("more", None):
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


def fetch_comments_for_post(post_id: str, subreddit: str, num_comments: int, config: dict) -> list[dict]:
    rcfg = config["reddit"]
    tiers = rcfg.get("comment_tiers", [{"min_thread_comments": 0, "max_extract": rcfg.get("max_comments_per_post", 25)}])
    limit = _resolve_comment_limit(num_comments, tiers)

    url = f"{REDDIT_BASE}/r/{subreddit}/comments/{post_id}.json"
    data = _get(url, params={
        "limit": limit,
        "sort": "top",
        "depth": rcfg["comment_reply_depth"],
    })

    if not data or not isinstance(data, list) or len(data) < 2:
        return []

    comment_children = data[1].get("data", {}).get("children", [])
    top_level = sorted(
        [c for c in comment_children if isinstance(c, dict) and c.get("kind") == "t1"],
        key=lambda c: c.get("data", {}).get("score", 0),
        reverse=True,
    )

    return _extract_comments_from_listing(top_level[:limit], depth=1, config=config)


def fetch_listing(subreddit: str, sort: str, params: dict, config: dict, seen_ids: set) -> list[dict]:
    rcfg = config["reddit"]
    posts = []
    after = None
    fetched = 0
    max_fetch = params.get("max_fetch", 2000)

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

        new_this_page = 0
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
            new_this_page += 1

        fetched += len(children)
        after = data.get("data", {}).get("after")

        if not after:
            break

    return posts


def fetch_subreddit_posts(subreddit: str, config: dict) -> list[dict]:
    seen_ids: set[str] = set()
    posts: list[dict] = []

    large_subreddits = {"Coffee", "espresso", "JamesHoffmann"}

    if subreddit in large_subreddits:
        fetch_jobs = [
            ("top", {"t": "year",  "max_fetch": 2000}),
            ("top", {"t": "all",   "max_fetch": 2000}),
            ("top", {"t": "month", "max_fetch": 500}),
            ("hot", {"max_fetch":  500}),
            ("new", {"max_fetch":  500}),
        ]
    else:
        fetch_jobs = [
            ("top", {"t": "year", "max_fetch": 2000}),
            ("top", {"t": "all",  "max_fetch": 2000}),
            ("hot", {"max_fetch": 500}),
            ("new", {"max_fetch": 500}),
        ]

    for sort, params in fetch_jobs:
        logger.info(f"r/{subreddit}: fetching {sort} (t={params.get('t', 'n/a')})")
        batch = fetch_listing(subreddit, sort, params, config, seen_ids)
        posts.extend(batch)
        logger.info(f"r/{subreddit}: +{len(batch)} posts from {sort}, {len(posts)} total")

    return posts


def run(config: dict, fresh: bool = False) -> dict:
    setup_logging()
    rcfg = config["reddit"]
    output_dir = Path(rcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load or reset state
    state = {"scraped_post_ids": [], "completed_subreddits": [], "in_progress": None, "last_run_at": None}
    if not fresh:
        state = _load_state()
        if state.get("scraped_post_ids") or state.get("completed_subreddits"):
            logger.info(
                f"Resuming from checkpoint: {len(state['scraped_post_ids'])} posts already scraped, "
                f"{len(state['completed_subreddits'])} subreddits complete"
            )
    else:
        logger.info("--fresh flag set — ignoring existing state")

    scraped_ids_set: set[str] = set(state.get("scraped_post_ids", []))
    completed_subreddits: set[str] = set(state.get("completed_subreddits", []))

    max_comment_posts = rcfg.get("max_comment_posts", 200)
    burst_break_every = rcfg.get("burst_break_every", 30)
    burst_break_min = rcfg.get("burst_break_min_s", 25)
    burst_break_max = rcfg.get("burst_break_max_s", 40)

    summary = {"posts": 0, "comments": 0, "subreddits": {}}
    scraped_at = datetime.now(tz=timezone.utc).isoformat()

    subreddits = rcfg["subreddits"]
    for idx, subreddit_name in enumerate(subreddits):
        if subreddit_name in completed_subreddits:
            logger.info(f"r/{subreddit_name}: already completed, skipping")
            continue

        logger.info(f"Starting r/{subreddit_name} ({idx + 1}/{len(subreddits)})")
        state["in_progress"] = subreddit_name
        state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
        _save_state(state)

        posts = fetch_subreddit_posts(subreddit_name, config)

        sub_cap = rcfg.get("subreddit_comment_caps", {}).get(subreddit_name, max_comment_posts)
        posts_for_comments = sorted(posts, key=lambda p: p["score"], reverse=True)[:sub_cap]
        skipped = len(posts) - len(posts_for_comments)
        logger.info(
            f"r/{subreddit_name}: {len(posts)} posts collected, "
            f"fetching comments for top {len(posts_for_comments)} by score "
            f"({skipped} below threshold skipped)"
        )

        out_path = output_dir / f"{subreddit_name}.jsonl"
        # Append mode — preserves records from previous runs
        open_mode = "a" if out_path.exists() and not fresh else "w"
        post_count = 0
        comment_count = 0
        comment_requests = 0

        with open(out_path, open_mode, encoding="utf-8") as f:
            for post_data in posts_for_comments:
                pid = post_data["post_id"]
                if pid in scraped_ids_set:
                    logger.debug(f"Skipping already-scraped post {pid}")
                    continue

                if comment_requests > 0 and comment_requests % burst_break_every == 0:
                    pause = random.uniform(burst_break_min, burst_break_max)
                    logger.info(f"Burst break after {comment_requests} comment requests — pausing {pause:.0f}s")
                    time.sleep(pause)

                try:
                    comments = fetch_comments_for_post(
                        pid, subreddit_name, post_data["num_comments"], config
                    )
                    comment_requests += 1
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

                    # Update state after each successful record
                    scraped_ids_set.add(pid)
                    state["scraped_post_ids"] = list(scraped_ids_set)
                    state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
                    _save_state(state)

                except Exception as e:
                    logger.error(f"Error processing post {pid}: {e}")

        summary["subreddits"][subreddit_name] = {"posts": post_count, "comments": comment_count}
        summary["posts"] += post_count
        summary["comments"] += comment_count
        logger.info(f"r/{subreddit_name}: wrote {post_count} posts, {comment_count} comments → {out_path}")

        # Mark subreddit complete in state
        completed_subreddits.add(subreddit_name)
        state["completed_subreddits"] = list(completed_subreddits)
        state["in_progress"] = None
        _save_state(state)

        if idx < len(subreddits) - 1:
            cooldown = random.uniform(SUBREDDIT_BREAK_MIN, SUBREDDIT_BREAK_MAX)
            logger.info(f"Cooldown before next subreddit: {cooldown:.0f}s")
            time.sleep(cooldown)

    print(f"Reddit complete:  {summary['posts']:,} posts | {summary['comments']:,} comments")
    return summary


if __name__ == "__main__":
    cfg = json.loads((Path(__file__).parent / "config.json").read_text())
    run(cfg)
