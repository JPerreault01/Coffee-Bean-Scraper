"""
Reddit scraper using PRAW.
Fetches posts from coffee-related subreddits and extracts top comments.
Supports checkpointing: resumes interrupted runs from last saved state.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import praw
from praw.exceptions import PRAWException

logger = logging.getLogger("reddit_scraper")

STATE_PATH = Path("training_data/state/reddit_state.json")


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def setup_logging():
    logging.basicConfig(
        format="[reddit_scraper] [%(levelname)s] %(asctime)s %(message)s",
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
        "scraped_post_ids": [],
        "completed_subreddits": [],
        "in_progress": None,
        "last_run_at": None,
    }


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def add_scraped_id(state: dict, post_id: str):
    if post_id not in state["scraped_post_ids"]:
        state["scraped_post_ids"].append(post_id)
    save_state(state)


# --- Helpers ---

def get_domain_tags(text: str, config: dict) -> list[str]:
    text_lower = text.lower()
    tags = []
    for tag, keywords in config["domain_tags"].items():
        if any(kw.lower() in text_lower for kw in keywords):
            tags.append(tag)
    return tags


def get_max_comments(num_comments: int, config: dict) -> int:
    for tier in config["reddit"]["comment_tiers"]:
        if num_comments >= tier["min_comments"]:
            return tier["max_comments_per_post"]
    return config["reddit"]["comment_tiers"][-1]["max_comments_per_post"]


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


def extract_comment(comment, depth: int, config: dict) -> Optional[dict]:
    rcfg = config["reddit"]
    if comment.body in ("[deleted]", "[removed]") or not comment.body:
        return None
    if len(comment.body) < rcfg["min_comment_chars"]:
        return None

    author = str(comment.author) if comment.author else "[deleted]"
    result = {
        "id": comment.id,
        "author": author,
        "body": comment.body,
        "score": comment.score,
        "replies": [],
    }

    if depth < rcfg["comment_reply_depth"]:
        try:
            comment.replies.replace_more(limit=0)
            sorted_replies = sorted(comment.replies, key=lambda r: r.score, reverse=True)
            for reply in sorted_replies[: rcfg["max_replies_per_comment"]]:
                extracted = extract_comment(reply, depth + 1, config)
                if extracted:
                    result["replies"].append(extracted)
        except Exception as e:
            logger.warning(f"Error extracting replies for comment {comment.id}: {e}")

    return result


def fetch_subreddit_posts(reddit: praw.Reddit, subreddit_name: str, config: dict, scraped_ids: set) -> list[dict]:
    rcfg = config["reddit"]
    seen_ids: set[str] = set()
    posts: list[dict] = []
    post_limit = rcfg.get("post_limit", 2000)

    sub = reddit.subreddit(subreddit_name)

    fetch_jobs = [
        ("top", {"time_filter": "year", "limit": post_limit}),
        ("top", {"time_filter": "all", "limit": post_limit}),
        ("hot", {"limit": min(post_limit, 1000)}),
        ("new", {"limit": min(post_limit, 1000)}),
    ]

    for method, kwargs in fetch_jobs:
        try:
            listing = getattr(sub, method)(**kwargs)
            for submission in listing:
                if submission.id in seen_ids or submission.id in scraped_ids:
                    continue
                seen_ids.add(submission.id)

                if submission.score < rcfg["min_score"]:
                    continue
                if submission.num_comments < rcfg["min_comments"]:
                    continue

                body = submission.selftext or ""
                if len(body) < rcfg["short_post_min_chars"] and submission.score < rcfg["short_post_score_threshold"]:
                    continue

                posts.append({
                    "post_id": submission.id,
                    "subreddit": subreddit_name,
                    "title": submission.title,
                    "body": body,
                    "url": submission.url,
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "created_utc": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
                })
        except PRAWException as e:
            logger.error(f"PRAW error fetching {method} from r/{subreddit_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {method} from r/{subreddit_name}: {e}")

    return posts


def fetch_comments_for_post(reddit: praw.Reddit, post_data: dict, config: dict) -> list[dict]:
    try:
        max_comments = get_max_comments(post_data["num_comments"], config)
        submission = reddit.submission(id=post_data["post_id"])
        submission.comments.replace_more(limit=0)
        sorted_comments = sorted(submission.comments, key=lambda c: c.score, reverse=True)
        comments = []
        for comment in sorted_comments[:max_comments]:
            extracted = extract_comment(comment, depth=1, config=config)
            if extracted:
                comments.append(extracted)
        return comments
    except PRAWException as e:
        logger.error(f"PRAW error fetching comments for post {post_data['post_id']}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching comments for post {post_data['post_id']}: {e}")
        return []


def run(config: dict, fresh: bool = False) -> dict:
    setup_logging()
    rcfg = config["reddit"]
    output_dir = Path(rcfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "coffee-pipeline/1.0")

    if not client_id or not client_secret:
        logger.error("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set in environment")
        sys.exit(1)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    state = load_state(fresh=fresh)
    scraped_ids = set(state["scraped_post_ids"])
    completed_subreddits = set(state["completed_subreddits"])

    summary = {"posts": 0, "comments": 0, "subreddits": {}}
    scraped_at = datetime.now(tz=timezone.utc).isoformat()

    for subreddit_name in rcfg["subreddits"]:
        if subreddit_name in completed_subreddits:
            logger.info(f"r/{subreddit_name}: already completed, skipping")
            continue

        state["in_progress"] = subreddit_name
        save_state(state)

        logger.info(f"Fetching posts from r/{subreddit_name}")
        posts = fetch_subreddit_posts(reddit, subreddit_name, config, scraped_ids)
        logger.info(f"r/{subreddit_name}: {len(posts)} new posts after filtering, fetching comments...")

        out_path = output_dir / f"{subreddit_name}.jsonl"
        post_count = 0
        comment_count = 0

        # Append mode so interrupted runs don't lose progress
        with open(out_path, "a", encoding="utf-8") as f:
            for post_data in posts:
                try:
                    comments = fetch_comments_for_post(reddit, post_data, config)
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

                    # Update state after each successfully written record
                    add_scraped_id(state, post_data["post_id"])
                    scraped_ids.add(post_data["post_id"])

                except Exception as e:
                    logger.error(f"Error processing post {post_data.get('post_id', '?')}: {e}")

        state["completed_subreddits"].append(subreddit_name)
        completed_subreddits.add(subreddit_name)
        save_state(state)

        summary["subreddits"][subreddit_name] = {"posts": post_count, "comments": comment_count}
        summary["posts"] += post_count
        summary["comments"] += comment_count
        logger.info(f"r/{subreddit_name}: wrote {post_count} posts, {comment_count} comments → {out_path}")

    state["in_progress"] = None
    state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
    save_state(state)

    print(f"Reddit complete:  {summary['posts']:,} posts | {summary['comments']:,} comments")
    return summary
