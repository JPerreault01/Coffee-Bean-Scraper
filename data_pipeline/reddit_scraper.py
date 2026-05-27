"""
Reddit scraper using PRAW.
Fetches posts from coffee-related subreddits and extracts top comments.
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


def get_domain_tags(text: str, config: dict) -> list[str]:
    text_lower = text.lower()
    tags = []
    for tag, keywords in config["domain_tags"].items():
        if any(kw.lower() in text_lower for kw in keywords):
            tags.append(tag)
    return tags


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


def fetch_subreddit_posts(reddit: praw.Reddit, subreddit_name: str, config: dict) -> list[dict]:
    rcfg = config["reddit"]
    seen_ids: set[str] = set()
    posts: list[dict] = []

    sub = reddit.subreddit(subreddit_name)

    fetch_jobs = [
        ("top", {"time_filter": "year", "limit": 500}),
        ("top", {"time_filter": "all", "limit": 500}),
        ("hot", {"limit": 200}),
    ]

    for method, kwargs in fetch_jobs:
        try:
            listing = getattr(sub, method)(**kwargs)
            for submission in listing:
                if submission.id in seen_ids:
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
    rcfg = config["reddit"]
    try:
        submission = reddit.submission(id=post_data["post_id"])
        submission.comments.replace_more(limit=0)
        sorted_comments = sorted(submission.comments, key=lambda c: c.score, reverse=True)
        comments = []
        for comment in sorted_comments[: rcfg["max_comments_per_post"]]:
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


def run(config: dict) -> dict:
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

    summary = {"posts": 0, "comments": 0, "subreddits": {}}
    scraped_at = datetime.now(tz=timezone.utc).isoformat()

    for subreddit_name in rcfg["subreddits"]:
        logger.info(f"Fetching posts from r/{subreddit_name}")
        posts = fetch_subreddit_posts(reddit, subreddit_name, config)
        logger.info(f"r/{subreddit_name}: {len(posts)} posts after filtering, fetching comments...")

        out_path = output_dir / f"{subreddit_name}.jsonl"
        post_count = 0
        comment_count = 0

        with open(out_path, "w", encoding="utf-8") as f:
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

                except Exception as e:
                    logger.error(f"Error processing post {post_data.get('post_id', '?')}: {e}")

        summary["subreddits"][subreddit_name] = {"posts": post_count, "comments": comment_count}
        summary["posts"] += post_count
        summary["comments"] += comment_count
        logger.info(f"r/{subreddit_name}: wrote {post_count} posts, {comment_count} comments → {out_path}")

    print(f"Reddit complete:  {summary['posts']:,} posts | {summary['comments']:,} comments")
    return summary
