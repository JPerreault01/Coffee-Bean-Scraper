# data_pipeline/reddit_scraper.py
"""
Reddit scraper using PRAW (official Reddit API).
Requires REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT in environment or .env file.
Create a free app at https://www.reddit.com/prefs/apps (choose "script" type).
"""

import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import praw
import praw.models
import prawcore.exceptions

logger = logging.getLogger("reddit_scraper")

SUBREDDIT_BREAK_MIN = 8
SUBREDDIT_BREAK_MAX = 15

STATE_FILE = Path("training_data/state/reddit_state.json")


def _load_env():
    """Load .env from repo root if present (no python-dotenv dependency needed)."""
    for candidate in [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent / ".env",
    ]:
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break


def get_reddit() -> praw.Reddit:
    _load_env()
    client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    user_agent = os.environ.get(
        "REDDIT_USER_AGENT",
        "script:coffee-pipeline:v1.0 (by /u/your_reddit_username)",
    ).strip()

    if not client_id or not client_secret:
        raise RuntimeError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set.\n"
            "1. Go to https://www.reddit.com/prefs/apps and create a 'script' app.\n"
            "2. Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to your .env file."
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        read_only=True,
    )


def setup_logging():
    logging.basicConfig(
        format="[reddit_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


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
    for tier in sorted(tiers, key=lambda t: t["min_thread_comments"], reverse=True):
        if num_comments >= tier["min_thread_comments"]:
            return tier["max_extract"]
    return tiers[-1]["max_extract"]


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


def _extract_replies(comment: praw.models.Comment, depth: int, config: dict) -> list[dict]:
    rcfg = config["reddit"]
    if depth >= rcfg["comment_reply_depth"]:
        return []

    replies = []
    sorted_replies = sorted(
        [r for r in comment.replies if isinstance(r, praw.models.Comment)],
        key=lambda r: r.score,
        reverse=True,
    )
    for reply in sorted_replies[: rcfg["max_replies_per_comment"]]:
        body = reply.body
        if body in ("[deleted]", "[removed]") or not body:
            continue
        if len(body) < rcfg["min_comment_chars"]:
            continue
        replies.append({
            "id": reply.id,
            "author": str(reply.author) if reply.author else "[deleted]",
            "body": body,
            "score": reply.score,
            "replies": _extract_replies(reply, depth + 1, config),
        })
    return replies


def fetch_comments_for_post(
    post_id: str,
    subreddit: str,
    num_comments: int,
    config: dict,
    reddit: praw.Reddit,
) -> list[dict]:
    rcfg = config["reddit"]
    tiers = rcfg.get(
        "comment_tiers",
        [{"min_thread_comments": 0, "max_extract": rcfg.get("max_comments_per_post", 25)}],
    )
    limit = _resolve_comment_limit(num_comments, tiers)

    try:
        submission = reddit.submission(id=post_id)
        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
    except prawcore.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch comments for {post_id}: {e}")
        return []
    except Exception as e:
        logger.warning(f"Unexpected error fetching comments for {post_id}: {e}")
        return []

    top_comments = sorted(
        [c for c in submission.comments if isinstance(c, praw.models.Comment)],
        key=lambda c: c.score,
        reverse=True,
    )[:limit]

    comments = []
    for comment in top_comments:
        body = comment.body
        if body in ("[deleted]", "[removed]") or not body:
            continue
        if len(body) < rcfg["min_comment_chars"]:
            continue
        comments.append({
            "id": comment.id,
            "author": str(comment.author) if comment.author else "[deleted]",
            "body": body,
            "score": comment.score,
            "replies": _extract_replies(comment, depth=1, config=config),
        })
    return comments


def fetch_listing(
    subreddit_name: str,
    sort: str,
    params: dict,
    config: dict,
    seen_ids: set,
    reddit: praw.Reddit,
) -> list[dict]:
    rcfg = config["reddit"]
    posts = []
    max_fetch = params.get("max_fetch", 2000)

    try:
        sub = reddit.subreddit(subreddit_name)

        if sort == "top":
            listing = sub.top(time_filter=params.get("t", "year"), limit=max_fetch)
        elif sort == "hot":
            listing = sub.hot(limit=max_fetch)
        elif sort == "new":
            listing = sub.new(limit=max_fetch)
        else:
            logger.warning(f"Unknown sort '{sort}' for r/{subreddit_name}")
            return posts

        for submission in listing:
            pid = submission.id
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            score = submission.score
            num_comments = submission.num_comments
            body = submission.selftext or ""

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
                "subreddit": subreddit_name,
                "title": submission.title,
                "body": body,
                "url": submission.url,
                "score": score,
                "num_comments": num_comments,
                "created_utc": datetime.fromtimestamp(
                    submission.created_utc, tz=timezone.utc
                ).isoformat(),
            })

    except prawcore.exceptions.Forbidden:
        logger.error(f"r/{subreddit_name}: 403 forbidden — subreddit may be private or quarantined")
    except prawcore.exceptions.NotFound:
        logger.error(f"r/{subreddit_name}: 404 not found — subreddit does not exist")
    except prawcore.exceptions.RequestException as e:
        logger.error(f"r/{subreddit_name}: request error fetching {sort}: {e}")

    return posts


def fetch_subreddit_posts(subreddit_name: str, config: dict, reddit: praw.Reddit) -> list[dict]:
    seen_ids: set[str] = set()
    posts: list[dict] = []

    large_subreddits = {"Coffee", "espresso", "JamesHoffmann"}

    if subreddit_name in large_subreddits:
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
        logger.info(f"r/{subreddit_name}: fetching {sort} (t={params.get('t', 'n/a')})")
        batch = fetch_listing(subreddit_name, sort, params, config, seen_ids, reddit)
        posts.extend(batch)
        logger.info(f"r/{subreddit_name}: +{len(batch)} posts from {sort}, {len(posts)} total")

    return posts


def run(config: dict, fresh: bool = False) -> dict:
    setup_logging()
    rcfg = config["reddit"]
    output_dir = Path(rcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    reddit = get_reddit()

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

        posts = fetch_subreddit_posts(subreddit_name, config, reddit)

        sub_cap = rcfg.get("subreddit_comment_caps", {}).get(subreddit_name, max_comment_posts)
        posts_for_comments = sorted(posts, key=lambda p: p["score"], reverse=True)[:sub_cap]
        skipped = len(posts) - len(posts_for_comments)
        logger.info(
            f"r/{subreddit_name}: {len(posts)} posts collected, "
            f"fetching comments for top {len(posts_for_comments)} by score "
            f"({skipped} below threshold skipped)"
        )

        out_path = output_dir / f"{subreddit_name}.jsonl"
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
                        pid, subreddit_name, post_data["num_comments"], config, reddit
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
