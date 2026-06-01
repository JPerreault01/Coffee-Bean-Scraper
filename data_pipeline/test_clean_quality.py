"""
Quality check for cleaned training data.

Reads all cleaned JSONL from training_data/cleaned/ and produces a readiness
report for Phase 1 (format_for_finetuning.py). Read-only --never modifies data.

Usage:
    python data_pipeline/test_clean_quality.py
    python data_pipeline/test_clean_quality.py --source reddit
    python data_pipeline/test_clean_quality.py --source web
    python data_pipeline/test_clean_quality.py --source youtube
    python data_pipeline/test_clean_quality.py --min-quality 0.70
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, quantiles
from typing import Any

CLEANED_DIR = Path("training_data/cleaned")
REPORT_PATH = CLEANED_DIR / "quality_report.json"

SOURCES = ("reddit", "web", "youtube")

# Minimum text length per source (chars)
MIN_TEXT_LEN: dict[str, int] = {
    "reddit": 150,
    "web": 400,
    "youtube": 300,
}

# YouTube pair yield multiplier (chunking reduces output)
YOUTUBE_PAIR_MULTIPLIER = 0.6

CATEGORIES = [
    "espresso",
    "grinders",
    "pour_over",
    "french_press",
    "cold_brew",
    "roast",
    "origins",
    "equipment_review",
    "troubleshooting",
    "beginner",
]

DEFAULT_MIN_QUALITY = 0.65
CATEGORY_THIN_THRESHOLD = 20


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def get_primary_text(record: dict[str, Any]) -> str | None:
    """Return the primary text field for a record based on its source."""
    source = record.get("source", "")
    raw = record.get("raw", {})
    if not isinstance(raw, dict):
        return None
    if source == "reddit":
        return raw.get("body")
    if source == "web":
        return raw.get("body")
    if source == "youtube":
        return raw.get("transcript")
    return None


def load_source(source: str) -> tuple[list[dict[str, Any]], int]:
    """Load all cleaned records for a source. Returns (records, malformed_count)."""
    source_dir = CLEANED_DIR / source
    records: list[dict[str, Any]] = []
    malformed = 0

    if not source_dir.exists():
        return records, malformed

    for jsonl_file in sorted(source_dir.glob("*.jsonl")):
        with jsonl_file.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue

                if not isinstance(record, dict):
                    malformed += 1
                    continue

                # Require at minimum: source, quality_score
                if "source" not in record or "quality_score" not in record:
                    malformed += 1
                    continue

                records.append(record)

    return records, malformed


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------


def passes_all_filters(
    record: dict[str, Any], min_quality: float
) -> bool:
    """Return True if a record clears every quality gate."""
    if record.get("flagged", False):
        return False
    if record.get("duplicate", False):
        return False
    if not record.get("is_english", True):
        return False
    if record.get("quality_score", 0.0) < min_quality:
        return False
    source = record.get("source", "")
    text = get_primary_text(record)
    if text is None or len(text) < MIN_TEXT_LEN.get(source, 0):
        return False
    return True


def compute_stats(
    records: list[dict[str, Any]],
    source: str,
    min_quality: float,
    malformed: int,
) -> dict[str, Any]:
    """Compute all quality metrics for a single source's records."""
    total = len(records)

    # Filter counters
    n_flagged = 0
    n_duplicate = 0
    n_non_english = 0
    n_short_text = 0
    n_low_quality = 0
    n_passing = 0

    quality_scores: list[float] = []
    text_lengths: list[int] = []

    tag_counter: Counter[str] = Counter()
    n_no_tags = 0

    for rec in records:
        flagged = rec.get("flagged", False)
        duplicate = rec.get("duplicate", False)
        is_english = rec.get("is_english", True)
        q_score = rec.get("quality_score", 0.0)
        text = get_primary_text(rec)
        text_len = len(text) if text else 0

        if flagged:
            n_flagged += 1
        if duplicate:
            n_duplicate += 1
        if not is_english:
            n_non_english += 1
        if text_len < MIN_TEXT_LEN.get(source, 0):
            n_short_text += 1
        if q_score < min_quality:
            n_low_quality += 1

        if passes_all_filters(rec, min_quality):
            n_passing += 1

        quality_scores.append(float(q_score))
        if text_len > 0:
            text_lengths.append(text_len)

        tags = rec.get("domain_tags", [])
        if not tags:
            n_no_tags += 1
        for tag in tags:
            tag_counter[tag] += 1

    # Quality score distribution
    qs_dist = _score_distribution(quality_scores)
    qs_brackets = _score_brackets(quality_scores)

    # Text length distribution
    tl_dist = _length_distribution(text_lengths)

    return {
        "source": source,
        "total": total,
        "malformed": malformed,
        "passing": n_passing,
        "failures": {
            "flagged": n_flagged,
            "duplicate": n_duplicate,
            "non_english": n_non_english,
            "short_text": n_short_text,
            "low_quality": n_low_quality,
        },
        "quality_score": qs_dist,
        "quality_brackets": qs_brackets,
        "text_length": tl_dist,
        "min_text_len_threshold": MIN_TEXT_LEN.get(source, 0),
        "tag_counts": dict(tag_counter.most_common()),
        "n_no_tags": n_no_tags,
    }


def _score_distribution(scores: list[float]) -> dict[str, float]:
    """Compute min/max/mean/median/p25/p75 for a list of floats."""
    if not scores:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0}
    qs = quantiles(scores, n=4) if len(scores) >= 4 else [scores[0]] * 3
    return {
        "min": round(min(scores), 4),
        "max": round(max(scores), 4),
        "mean": round(mean(scores), 4),
        "median": round(median(scores), 4),
        "p25": round(qs[0], 4),
        "p75": round(qs[2], 4),
    }


def _score_brackets(scores: list[float]) -> dict[str, int]:
    """Count scores in quality brackets."""
    brackets: dict[str, int] = {
        "<0.50": 0,
        "0.50-0.65": 0,
        "0.65-0.75": 0,
        "0.75-0.85": 0,
        "0.85+": 0,
    }
    for s in scores:
        if s < 0.50:
            brackets["<0.50"] += 1
        elif s < 0.65:
            brackets["0.50-0.65"] += 1
        elif s < 0.75:
            brackets["0.65-0.75"] += 1
        elif s < 0.85:
            brackets["0.75-0.85"] += 1
        else:
            brackets["0.85+"] += 1
    return brackets


def _length_distribution(lengths: list[int]) -> dict[str, float]:
    """Compute min/max/mean/median for a list of int lengths."""
    if not lengths:
        return {"min": 0, "max": 0, "mean": 0.0, "median": 0.0}
    return {
        "min": min(lengths),
        "max": max(lengths),
        "mean": round(mean(lengths), 1),
        "median": round(median(lengths), 1),
    }


# ---------------------------------------------------------------------------
# Category readiness
# ---------------------------------------------------------------------------


def check_categories(
    records_by_source: dict[str, list[dict[str, Any]]],
    min_quality: float,
) -> dict[str, Any]:
    """Count passing records per fine-tuning category."""
    category_counts: Counter[str] = Counter()

    for source, records in records_by_source.items():
        for rec in records:
            if not passes_all_filters(rec, min_quality):
                continue
            for tag in rec.get("domain_tags", []):
                if tag in CATEGORIES:
                    category_counts[tag] += 1

    results: dict[str, Any] = {}
    for cat in CATEGORIES:
        count = category_counts.get(cat, 0)
        if count == 0:
            status = "MISSING"
        elif count < CATEGORY_THIN_THRESHOLD:
            status = "THIN"
        else:
            status = "OK"
        results[cat] = {"count": count, "status": status}

    return results


# ---------------------------------------------------------------------------
# Pair projection
# ---------------------------------------------------------------------------


def compute_pair_projection(stats_by_source: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Estimate instruction pairs Phase 1 will produce."""
    reddit_passing = stats_by_source.get("reddit", {}).get("passing", 0)
    web_passing = stats_by_source.get("web", {}).get("passing", 0)
    youtube_passing = stats_by_source.get("youtube", {}).get("passing", 0)

    youtube_projected = int(youtube_passing * YOUTUBE_PAIR_MULTIPLIER)
    total = reddit_passing + web_passing + youtube_projected

    if total < 300:
        verdict = "WARNING"
        explanation = "Insufficient data - run more pipeline passes before proceeding."
    elif total < 700:
        verdict = "CAUTION"
        explanation = "Enough to proceed but output will be thin."
    else:
        verdict = "READY"
        explanation = "Sufficient data to proceed to format_for_finetuning.py."

    return {
        "reddit": reddit_passing,
        "web": web_passing,
        "youtube_raw_passing": youtube_passing,
        "youtube_projected": youtube_projected,
        "total_projected": total,
        "verdict": verdict,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Console report formatting
# ---------------------------------------------------------------------------


def _divider(width: int = 72) -> str:
    return "-" * width


def print_source_report(stats: dict[str, Any], min_quality: float) -> None:
    """Print the per-source summary block to stdout."""
    source = stats["source"].upper()
    total = stats["total"]
    passing = stats["passing"]
    malformed = stats["malformed"]

    print()
    print(_divider())
    print(f"  SOURCE: {source}")
    print(_divider())

    if total == 0 and malformed == 0:
        print("  No data found for this source.")
        return

    pct = f"{passing / total * 100:.1f}%" if total > 0 else "N/A"
    print(f"  Total records : {total}")
    print(f"  Malformed     : {malformed}")
    print(f"  Passing all   : {passing}  ({pct})")
    print()

    # Failure breakdown
    f = stats["failures"]
    print("  Failure breakdown (records failing each check):")
    print(f"    Flagged          : {f['flagged']}")
    print(f"    Duplicate        : {f['duplicate']}")
    print(f"    Non-English      : {f['non_english']}")
    print(f"    Short text       : {f['short_text']}  (threshold: {stats['min_text_len_threshold']} chars)")
    print(f"    Low quality (<{min_quality}) : {f['low_quality']}")
    print()

    # Quality score distribution
    qs = stats["quality_score"]
    print("  Quality score distribution:")
    print(f"    Min={qs['min']}  Max={qs['max']}  Mean={qs['mean']}  "
          f"Median={qs['median']}  P25={qs['p25']}  P75={qs['p75']}")

    brackets = stats["quality_brackets"]
    print("  Quality brackets:")
    for bracket, count in brackets.items():
        bar = "#" * min(count, 40)
        print(f"    {bracket:>12s} : {count:>5d}  {bar}")
    print()

    # Text length distribution
    tl = stats["text_length"]
    print("  Text length distribution (primary field):")
    print(f"    Min={tl['min']}  Max={tl['max']}  Mean={tl['mean']}  Median={tl['median']}")
    print()

    # Domain tag coverage
    tag_counts = stats["tag_counts"]
    print(f"  Domain tag coverage  (records with no tags: {stats['n_no_tags']}):")
    if tag_counts:
        for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1]):
            print(f"    {tag:<25s} : {cnt}")
    else:
        print("    (none)")


def print_category_table(category_results: dict[str, Any]) -> None:
    """Print the category readiness table."""
    print()
    print(_divider())
    print("  CATEGORY READINESS")
    print(_divider())
    print(f"  {'Category':<22}  {'Passing':>8}  Status")
    print(f"  {'-'*22}  {'-'*8}  ------")
    for cat, info in category_results.items():
        flag = ""
        if info["status"] == "MISSING":
            flag = "  << MISSING"
        elif info["status"] == "THIN":
            flag = "  << THIN"
        print(f"  {cat:<22}  {info['count']:>8}{flag}")


def print_pair_projection(proj: dict[str, Any]) -> None:
    """Print the pair projection section."""
    print()
    print(_divider())
    print("  PAIR PROJECTION")
    print(_divider())
    print(f"  Reddit  (1:1)      : {proj['reddit']}")
    print(f"  Web     (1:1)      : {proj['web']}")
    print(f"  YouTube ({YOUTUBE_PAIR_MULTIPLIER}x)    : {proj['youtube_raw_passing']} passing  ->  {proj['youtube_projected']} projected")
    print(f"  {'-'*40}")
    print(f"  Total projected    : {proj['total_projected']}")
    print()
    print(f"  {proj['verdict']} -- {proj['explanation']}")


def print_final_verdict(proj: dict[str, Any]) -> None:
    """Print the single-line final verdict."""
    print()
    print(_divider())
    print(f"  VERDICT: {proj['verdict']} -- {proj['explanation']}")
    print(_divider())
    print()


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------


def write_json_report(
    stats_by_source: dict[str, dict[str, Any]],
    category_results: dict[str, Any],
    projection: dict[str, Any],
    min_quality: float,
) -> None:
    """Write the full quality report as JSON."""
    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "min_quality_threshold": min_quality,
        "sources": stats_by_source,
        "category_readiness": category_results,
        "pair_projection": projection,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"  JSON report written to: {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Quality check cleaned training data for fine-tuning readiness."
    )
    parser.add_argument(
        "--source",
        choices=list(SOURCES),
        default=None,
        help="Check only one source (default: all).",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=DEFAULT_MIN_QUALITY,
        metavar="FLOAT",
        help=f"Minimum quality_score threshold (default: {DEFAULT_MIN_QUALITY}).",
    )
    return parser.parse_args()


def main() -> None:
    """Run the quality check and print the report."""
    args = parse_args()
    min_quality: float = args.min_quality
    sources_to_check = (args.source,) if args.source else SOURCES

    if not CLEANED_DIR.exists():
        print("No cleaned data found. Run clean_pipeline.py first.")
        sys.exit(1)

    # Check that at least one source directory has data
    any_data = any((CLEANED_DIR / s).exists() for s in SOURCES)
    if not any_data:
        print("No cleaned data found. Run clean_pipeline.py first.")
        sys.exit(1)

    print()
    print("=" * 72)
    print("  COFFEE TRAINING DATA -- QUALITY REPORT")
    print(f"  Min quality threshold : {min_quality}")
    print(f"  Sources checked       : {', '.join(sources_to_check)}")
    print("=" * 72)

    records_by_source: dict[str, list[dict[str, Any]]] = {}
    stats_by_source: dict[str, dict[str, Any]] = {}

    for source in SOURCES:
        source_dir = CLEANED_DIR / source
        if source not in sources_to_check:
            continue

        if not source_dir.exists():
            print()
            print(f"  {source.upper()}: no data")
            stats_by_source[source] = {
                "source": source,
                "total": 0,
                "malformed": 0,
                "passing": 0,
                "failures": {
                    "flagged": 0,
                    "duplicate": 0,
                    "non_english": 0,
                    "short_text": 0,
                    "low_quality": 0,
                },
                "quality_score": _score_distribution([]),
                "quality_brackets": _score_brackets([]),
                "text_length": _length_distribution([]),
                "min_text_len_threshold": MIN_TEXT_LEN.get(source, 0),
                "tag_counts": {},
                "n_no_tags": 0,
            }
            records_by_source[source] = []
            continue

        records, malformed = load_source(source)
        records_by_source[source] = records
        stats = compute_stats(records, source, min_quality, malformed)
        stats_by_source[source] = stats
        print_source_report(stats, min_quality)

    # Aggregated totals (when running all sources)
    if args.source is None and len(stats_by_source) > 1:
        total_all = sum(s["total"] for s in stats_by_source.values())
        passing_all = sum(s["passing"] for s in stats_by_source.values())
        malformed_all = sum(s["malformed"] for s in stats_by_source.values())
        pct_all = f"{passing_all / total_all * 100:.1f}%" if total_all > 0 else "N/A"
        print()
        print(_divider())
        print("  TOTALS (all sources)")
        print(_divider())
        print(f"  Total records   : {total_all}")
        print(f"  Malformed       : {malformed_all}")
        print(f"  Passing all     : {passing_all}  ({pct_all})")

    # Category readiness (uses all loaded sources regardless of --source filter)
    category_results = check_categories(records_by_source, min_quality)
    print_category_table(category_results)

    # Pair projection
    projection = compute_pair_projection(stats_by_source)
    print_pair_projection(projection)
    print_final_verdict(projection)

    # JSON output
    write_json_report(stats_by_source, category_results, projection, min_quality)


if __name__ == "__main__":
    main()
