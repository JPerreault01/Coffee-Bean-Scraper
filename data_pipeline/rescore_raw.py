"""
Rescore existing raw training data with updated quality formulas.

Run this after updating config.json and the scorer functions in reddit_scraper.py
and youtube_scraper.py. Reads raw JSONL files, recomputes quality_score in-place,
and prints before/after statistics.

After running this, re-run:
    python data_pipeline/clean_pipeline.py
    python data_pipeline/test_clean_quality.py

Usage:
    python data_pipeline/rescore_raw.py
    python data_pipeline/rescore_raw.py --source reddit
    python data_pipeline/rescore_raw.py --source youtube
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_pipeline.reddit_scraper import compute_reddit_quality
from data_pipeline.youtube_scraper import compute_youtube_quality

RAW_DIR = Path("training_data/raw")
CONFIG_PATH = Path("data_pipeline/config.json")
THRESHOLD = 0.65


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> tuple[list[dict], int]:
    records, malformed = [], 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    return records, malformed


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rescore_reddit(config: dict) -> dict:
    reddit_dir = RAW_DIR / "reddit"
    if not reddit_dir.exists():
        return {}

    stats: dict = {"files": 0, "records": 0, "score_before": [], "score_after": []}

    for jsonl_file in sorted(reddit_dir.glob("*.jsonl")):
        records, _ = _load_jsonl(jsonl_file)
        updated = []

        for rec in records:
            if rec.get("source") != "reddit":
                updated.append(rec)
                continue
            raw = rec.get("raw", {})
            if not isinstance(raw, dict):
                updated.append(rec)
                continue

            old_score = float(rec.get("quality_score", 0.0))
            new_score = compute_reddit_quality(raw, config)

            stats["score_before"].append(old_score)
            stats["score_after"].append(new_score)
            stats["records"] += 1

            rec["quality_score"] = new_score
            updated.append(rec)

        _write_jsonl(jsonl_file, updated)
        stats["files"] += 1
        print(f"    rescored {jsonl_file.name} ({len(records)} records)")

    return stats


def rescore_youtube(config: dict) -> dict:
    youtube_dir = RAW_DIR / "youtube"
    if not youtube_dir.exists():
        return {}

    stats: dict = {"files": 0, "records": 0, "score_before": [], "score_after": []}

    for jsonl_file in sorted(youtube_dir.glob("*.jsonl")):
        records, _ = _load_jsonl(jsonl_file)
        updated = []

        for rec in records:
            if rec.get("source") != "youtube":
                updated.append(rec)
                continue
            raw = rec.get("raw", {})
            if not isinstance(raw, dict):
                updated.append(rec)
                continue

            transcript = raw.get("transcript", "")
            channel_name = raw.get("channel_name", "")

            old_score = float(rec.get("quality_score", 0.0))
            new_score = compute_youtube_quality(transcript, channel_name, config)

            stats["score_before"].append(old_score)
            stats["score_after"].append(new_score)
            stats["records"] += 1

            rec["quality_score"] = new_score
            updated.append(rec)

        _write_jsonl(jsonl_file, updated)
        stats["files"] += 1
        print(f"    rescored {jsonl_file.name} ({len(records)} records)")

    return stats


def print_stats(source: str, stats: dict) -> None:
    if not stats or not stats.get("records"):
        print(f"\n  {source.upper()}: no records found")
        return

    before = stats["score_before"]
    after = stats["score_after"]
    n = len(before)

    passing_before = sum(1 for s in before if s >= THRESHOLD)
    passing_after = sum(1 for s in after if s >= THRESHOLD)

    print(f"\n  {source.upper()}")
    print(f"  Records rescored  : {n:,}")
    print(f"  Mean score before : {mean(before):.4f}  ->  after: {mean(after):.4f}")
    print(f"  Passing before    : {passing_before:,}  ({passing_before/n*100:.1f}%)")
    print(f"  Passing after     : {passing_after:,}  ({passing_after/n*100:.1f}%)")
    print(f"  Net gain          : +{passing_after - passing_before:,} records")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rescore raw training data with updated quality formulas."
    )
    parser.add_argument(
        "--source",
        choices=["reddit", "youtube"],
        default=None,
        help="Rescore a single source (default: both)",
    )
    args = parser.parse_args()

    config = load_config()
    run_all = args.source is None

    print("\n" + "=" * 60)
    print("  RESCORING RAW TRAINING DATA")
    print(f"  Threshold: {THRESHOLD}")
    print("=" * 60)

    reddit_stats, youtube_stats = {}, {}

    if run_all or args.source == "reddit":
        print("\n  Reddit files:")
        reddit_stats = rescore_reddit(config)
        print_stats("reddit", reddit_stats)

    if run_all or args.source == "youtube":
        print("\n  YouTube files:")
        youtube_stats = rescore_youtube(config)
        print_stats("youtube", youtube_stats)

    print("\n" + "=" * 60)
    print("  Rescoring complete. Next steps:")
    print("    python data_pipeline/clean_pipeline.py")
    print("    python data_pipeline/test_clean_quality.py")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
