"""
Orchestrator for the coffee training data pipeline.

Usage:
    python data_pipeline/run_pipeline.py              # run all scrapers
    python data_pipeline/run_pipeline.py --reddit
    python data_pipeline/run_pipeline.py --web
    python data_pipeline/run_pipeline.py --youtube
    python data_pipeline/run_pipeline.py --youtube --video-id <id>
    python data_pipeline/run_pipeline.py --fresh      # ignore checkpoints, start from zero
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root: python data_pipeline/run_pipeline.py
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_pipeline import reddit_scraper, web_scraper, youtube_scraper

logger = logging.getLogger("run_pipeline")


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def write_summary(config: dict, run_summary: dict):
    summary_path = Path(config["output"]["summary_file"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, indent=2, ensure_ascii=False)
    logger.info(f"Run summary written to {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="Coffee training data pipeline orchestrator")
    parser.add_argument("--reddit", action="store_true", help="Run the Reddit scraper only")
    parser.add_argument("--web", action="store_true", help="Run the web scraper only")
    parser.add_argument("--youtube", action="store_true", help="Run the YouTube scraper only")
    parser.add_argument("--video-id", metavar="VIDEO_ID", help="Scrape a single YouTube video by ID (use with --youtube)")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore existing checkpoint state and start from zero",
    )
    args = parser.parse_args()

    # If no source flags given, run all scrapers
    run_all = not (args.reddit or args.web or args.youtube)

    logging.basicConfig(
        format="[run_pipeline] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )

    config = load_config()
    run_summary = {
        "run_at": datetime.now(tz=timezone.utc).isoformat(),
        "fresh": args.fresh,
        "reddit": {"posts": 0, "comments": 0, "subreddits": {}},
        "web": {"articles": 0, "by_site": {}},
        "youtube": {"transcripts": 0, "by_channel": {}},
    }

    if run_all or args.reddit:
        try:
            reddit_result = reddit_scraper.run(config, fresh=args.fresh)
            run_summary["reddit"] = reddit_result
        except SystemExit:
            logger.error("Reddit scraper exited with an error — check credentials")
        except Exception as e:
            logger.error(f"Reddit scraper failed: {e}")

    if run_all or args.web:
        try:
            web_result = web_scraper.run(config, fresh=args.fresh)
            run_summary["web"] = web_result
        except Exception as e:
            logger.error(f"Web scraper failed: {e}")

    if run_all or args.youtube:
        try:
            youtube_result = youtube_scraper.run(config, video_id_override=args.video_id, fresh=args.fresh)
            run_summary["youtube"] = youtube_result
        except Exception as e:
            logger.error(f"YouTube scraper failed: {e}")

    write_summary(config, run_summary)


if __name__ == "__main__":
    main()
