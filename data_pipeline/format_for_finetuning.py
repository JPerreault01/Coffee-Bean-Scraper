#!/usr/bin/env python3
"""
format_for_finetuning.py — Convert cleaned JSONL data into ChatML instruction pairs
for fine-tuning a Hermes-3 or Llama-3.1-8B model.

Phase 1 of the fine-tuning pipeline: backtranslation via claude-haiku to generate
user-side prompts for each cleaned record that passes quality filters.
"""

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

import anthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a coffee expert writing for a niche review and knowledge site. You have deep\n"
    "technical knowledge of espresso, filter brewing, grinders, origins, and roast science.\n"
    "\n"
    "Your voice is direct, confident, and specific. No hedging. No filler. No marketing\n"
    'language. Short declarative sentences. Specific claims over vague ones — "turns acrid\n'
    'past 205°F" not "can be harsh". You apply critical judgment: clean finishes over\n'
    "lingering bitterness, forgiving brew profiles over finicky ones, value over brand\n"
    "premiums.\n"
    "\n"
    "When reviewing products, the coffee is the subject. State what it is and what it does.\n"
    'Second person ("you get", "you\'ll find") is preferred. Never claim to have personally\n'
    "tried a product unless explicitly told this is a personal review."
)

CATEGORY_PRIORITY: list[str] = [
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

SPAM_PATTERNS: list[str] = [
    r"^price check",
    r"^\[wts\]",
    r"^\[wtb\]",
    r"^where to buy",
    r"^iso ",
]

HAIKU_INPUT_PRICE_PER_M = 0.80
HAIKU_OUTPUT_PRICE_PER_M = 4.00
ASSUMED_INPUT_TOKENS = 750
ASSUMED_OUTPUT_TOKENS = 150

SOURCE_TYPE_LABELS: dict[str, str] = {
    "reddit": "reddit discussion",
    "web": "web article",
    "youtube": "youtube transcript",
}


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def load_checkpoint(finetune_dir: Path) -> set[str]:
    """Load previously processed source_ids from checkpoint.json."""
    checkpoint_path = finetune_dir / "checkpoint.json"
    if not checkpoint_path.exists():
        return set()
    try:
        with open(checkpoint_path, encoding='utf-8') as f:
            data = json.load(f)
        return set(data)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load checkpoint: {exc}")
        return set()


def save_checkpoint(finetune_dir: Path, source_id: str) -> None:
    """Atomically append source_id to checkpoint.json."""
    checkpoint_path = finetune_dir / "checkpoint.json"
    existing: list[str] = []
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, encoding='utf-8') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []
    existing.append(source_id)
    tmp = checkpoint_path.with_suffix(".tmp")
    with open(tmp, "w", encoding='utf-8') as f:
        json.dump(existing, f)
    tmp.replace(checkpoint_path)


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def assign_category(domain_tags: list[str]) -> str:
    """Assign the primary category from domain_tags using priority order."""
    tag_set = set(domain_tags)
    for cat in CATEGORY_PRIORITY:
        if cat in tag_set:
            return cat
    return "general"


def passes_quality_filter(
    record: dict[str, Any],
    min_quality: float,
    primary_text: str,
    min_length: int,
) -> bool:
    """Return True if the record passes all common quality gates."""
    if record.get("quality_score", 0) < min_quality:
        return False
    if record.get("flagged"):
        return False
    if record.get("duplicate"):
        return False
    if record.get("is_english") is False:
        return False
    if len(primary_text) < min_length:
        return False
    return True


def is_spam_reddit(title: str) -> bool:
    """Return True if the Reddit post title matches a spam pattern."""
    title_lower = title.lower()
    return any(re.match(pattern, title_lower) for pattern in SPAM_PATTERNS)


def get_source_id_reddit(raw: dict[str, Any], title: str, body: str) -> str:
    """Derive source_id for a Reddit record."""
    if post_id := raw.get("post_id"):
        return str(post_id)
    digest = hashlib.sha256((title + body).encode()).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# YouTube chunking
# ---------------------------------------------------------------------------


def chunk_transcript(text: str, chunk_size: int = 3200, overlap: int = 200) -> list[str]:
    """Split a transcript into overlapping chunks."""
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def score_chunk_by_vocab(chunk: str, tech_vocab: list[str]) -> int:
    """Count distinct tech vocabulary terms found in the chunk (case-insensitive)."""
    chunk_lower = chunk.lower()
    return sum(1 for term in tech_vocab if term.lower() in chunk_lower)


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def estimate_cost(api_calls: int) -> float:
    """Estimate total API cost based on number of calls."""
    input_cost = api_calls * ASSUMED_INPUT_TOKENS * HAIKU_INPUT_PRICE_PER_M / 1_000_000
    output_cost = api_calls * ASSUMED_OUTPUT_TOKENS * HAIKU_OUTPUT_PRICE_PER_M / 1_000_000
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------


def call_api_with_retry(
    client: anthropic.Anthropic,
    category: str,
    source_type: str,
    assistant_text: str,
    delay: float,
) -> str | None:
    """
    Call claude-haiku to generate a user-side prompt for the given content.

    Returns the generated question string, or None if all retries are exhausted.
    """
    prompt = (
        "You are generating training data for a coffee knowledge model.\n\n"
        "Below is a piece of coffee content. Write a single natural question or instruction\n"
        "that someone might ask, where this content would be an ideal response. The question\n"
        "should be specific to the content — not generic. Match the technical level of the\n"
        "content. Do not ask about specific author names, dates, or publication sources.\n"
        "Return only the question, no preamble.\n\n"
        f"Content category: {category}\n"
        f"Content source type: {source_type} (reddit discussion / web article / youtube transcript)\n\n"
        f"Content:\n{assistant_text}"
    )

    for attempt in range(3):
        try:
            time.sleep(delay)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except anthropic.RateLimitError:
            logger.warning(f"Rate limit hit (attempt {attempt + 1}/3), waiting 10s...")
            time.sleep(10)
        except Exception as exc:
            logger.warning(f"API error (attempt {attempt + 1}/3): {exc}")

    return None


# ---------------------------------------------------------------------------
# Phase 1: collect candidates (filtering only, no API calls)
# ---------------------------------------------------------------------------

# Each candidate dict has these keys:
#   source, source_id, category, quality_score, site_or_channel, assistant_text


def collect_reddit(
    cleaned_dir: Path,
    min_quality: float,
    checkpoint_ids: set[str],
) -> list[dict]:
    """Collect candidate records from Reddit JSONL files. No API calls."""
    candidates: list[dict] = []
    reddit_dir = cleaned_dir / "reddit"
    if not reddit_dir.exists():
        logger.info("No reddit/ directory found, skipping.")
        return candidates

    for jsonl_file in sorted(reddit_dir.glob("*.jsonl")):
        site_or_channel = jsonl_file.stem
        records: list[dict] = []
        try:
            with open(jsonl_file, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning(f"Malformed record in {jsonl_file}: {exc}")
        except OSError as exc:
            logger.warning(f"Could not read {jsonl_file}: {exc}")
            continue

        total = len(records)
        passed = 0
        filtered = 0

        for i, record in enumerate(records):
            print(
                f"\r[reddit] {jsonl_file.name}: {i + 1}/{total} | "
                f"passed: {passed} | filtered: {filtered}",
                end="",
                flush=True,
            )

            raw = record.get("raw", {})
            title = raw.get("title", "")
            body = raw.get("body", "")
            primary_text = (title + " " + body).strip()

            if is_spam_reddit(title):
                filtered += 1
                continue

            if not passes_quality_filter(record, min_quality, primary_text, 150):
                filtered += 1
                continue

            source_id = get_source_id_reddit(raw, title, body)

            if source_id in checkpoint_ids:
                passed += 1
                continue

            candidates.append({
                "source": "reddit",
                "source_id": source_id,
                "category": assign_category(record.get("domain_tags", [])),
                "quality_score": float(record.get("quality_score", 0.0)),
                "site_or_channel": site_or_channel,
                "assistant_text": primary_text[:1500],
            })
            passed += 1

        print(
            f"\r[reddit] {jsonl_file.name}: {total}/{total} | "
            f"passed: {passed} | filtered: {filtered}"
        )

    return candidates


def collect_web(
    cleaned_dir: Path,
    min_quality: float,
    checkpoint_ids: set[str],
) -> list[dict]:
    """Collect candidate records from web JSONL files. No API calls."""
    candidates: list[dict] = []
    web_dir = cleaned_dir / "web"
    if not web_dir.exists():
        logger.info("No web/ directory found, skipping.")
        return candidates

    for jsonl_file in sorted(web_dir.glob("*.jsonl")):
        site_or_channel = jsonl_file.stem
        indexed_records: list[tuple[int, dict]] = []
        try:
            with open(jsonl_file, encoding='utf-8') as f:
                for line_index, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        indexed_records.append((line_index, json.loads(line)))
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            f"Malformed record in {jsonl_file} line {line_index}: {exc}"
                        )
        except OSError as exc:
            logger.warning(f"Could not read {jsonl_file}: {exc}")
            continue

        total = len(indexed_records)
        passed = 0
        filtered = 0

        for idx, (orig_index, record) in enumerate(indexed_records):
            print(
                f"\r[web] {jsonl_file.name}: {idx + 1}/{total} | "
                f"passed: {passed} | filtered: {filtered}",
                end="",
                flush=True,
            )

            raw = record.get("raw", {})
            body = raw.get("body", "")

            if not passes_quality_filter(record, min_quality, body, 400):
                filtered += 1
                continue

            if url := raw.get("url"):
                source_id = url
            else:
                source_id = str(raw.get("site", "unknown")) + "_" + str(orig_index)

            if source_id in checkpoint_ids:
                passed += 1
                continue

            candidates.append({
                "source": "web",
                "source_id": source_id,
                "category": assign_category(record.get("domain_tags", [])),
                "quality_score": float(record.get("quality_score", 0.0)),
                "site_or_channel": site_or_channel,
                "assistant_text": body[:2500],
            })
            passed += 1

        print(
            f"\r[web] {jsonl_file.name}: {total}/{total} | "
            f"passed: {passed} | filtered: {filtered}"
        )

    return candidates


def collect_youtube(
    cleaned_dir: Path,
    min_quality: float,
    checkpoint_ids: set[str],
    max_chunks_per_video: int = 3,
    tech_vocab: list[str] | None = None,
) -> list[dict]:
    """Collect candidate records from YouTube JSONL files. No API calls."""
    candidates: list[dict] = []
    youtube_dir = cleaned_dir / "youtube"
    if not youtube_dir.exists():
        logger.info("No youtube/ directory found, skipping.")
        return candidates

    for jsonl_file in sorted(youtube_dir.glob("*.jsonl")):
        site_or_channel = jsonl_file.stem
        records: list[dict] = []
        try:
            with open(jsonl_file, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning(f"Malformed record in {jsonl_file}: {exc}")
        except OSError as exc:
            logger.warning(f"Could not read {jsonl_file}: {exc}")
            continue

        total = len(records)
        passed = 0
        filtered = 0

        for i, record in enumerate(records):
            raw = record.get("raw", {})
            transcript = raw.get("transcript", "")

            if not passes_quality_filter(record, min_quality, transcript, 300):
                filtered += 1
                print(
                    f"\r[youtube] {jsonl_file.name}: {i + 1}/{total} | "
                    f"passed: {passed} | filtered: {filtered}",
                    end="",
                    flush=True,
                )
                continue

            video_id = str(raw.get("video_id", f"unknown_{i}"))
            category = assign_category(record.get("domain_tags", []))
            quality_score = float(record.get("quality_score", 0.0))
            all_chunks = chunk_transcript(transcript)
            vocab = tech_vocab or []
            scored = sorted(
                enumerate(all_chunks),
                key=lambda ic: score_chunk_by_vocab(ic[1], vocab),
                reverse=True,
            )
            selected_chunks = scored[:max_chunks_per_video]

            for chunk_index, chunk in selected_chunks:
                source_id = f"{video_id}_{chunk_index}"

                print(
                    f"\r[youtube] {jsonl_file.name}: {i + 1}/{total} | "
                    f"passed: {passed} | filtered: {filtered}",
                    end="",
                    flush=True,
                )

                if source_id in checkpoint_ids:
                    passed += 1
                    continue

                candidates.append({
                    "source": "youtube",
                    "source_id": source_id,
                    "category": category,
                    "quality_score": quality_score,
                    "site_or_channel": site_or_channel,
                    "assistant_text": chunk[:2500],
                })
                passed += 1

        print(
            f"\r[youtube] {jsonl_file.name}: {total}/{total} | "
            f"passed: {passed} | filtered: {filtered}"
        )

    return candidates


# ---------------------------------------------------------------------------
# Phase 2: category cap (applied before API calls)
# ---------------------------------------------------------------------------


def cap_candidates(
    candidates: list[dict], max_per_cat: int
) -> tuple[list[dict], dict[str, int]]:
    """
    Cap candidates per non-'general' category to max_per_cat, sampling with seed 42.

    Returns (capped_candidates, pre_cap_counts_by_category).
    """
    rng = random.Random(42)
    by_category: dict[str, list[dict]] = {}
    for c in candidates:
        by_category.setdefault(c["category"], []).append(c)

    result: list[dict] = []
    pre_cap: dict[str, int] = {}

    for cat, items in by_category.items():
        pre_cap[cat] = len(items)
        if cat == "general" or len(items) <= max_per_cat:
            result.extend(items)
        else:
            result.extend(rng.sample(items, max_per_cat))

    return result, pre_cap


# ---------------------------------------------------------------------------
# Train/val split and output
# ---------------------------------------------------------------------------


def split_and_write(pairs: list[dict], finetune_dir: Path) -> dict[str, Any]:
    """
    Stratified 90/10 train/val split, then write train.jsonl, val.jsonl, stats.json.

    Categories with fewer than 5 records are placed entirely in train.
    """
    rng = random.Random(42)

    by_category: dict[str, list[dict]] = {}
    for pair in pairs:
        cat = pair["meta"]["category"]
        by_category.setdefault(cat, []).append(pair)

    train_pairs: list[dict] = []
    val_pairs: list[dict] = []
    by_split: dict[str, dict[str, int]] = {"train": {}, "val": {}}

    for cat, cat_pairs in by_category.items():
        rng.shuffle(cat_pairs)
        if len(cat_pairs) < 5:
            train_pairs.extend(cat_pairs)
            by_split["train"][cat] = len(cat_pairs)
            by_split["val"][cat] = 0
        else:
            val_count = max(1, int(len(cat_pairs) * 0.1))
            val_part = cat_pairs[:val_count]
            train_part = cat_pairs[val_count:]
            train_pairs.extend(train_part)
            val_pairs.extend(val_part)
            by_split["train"][cat] = len(train_part)
            by_split["val"][cat] = len(val_part)

    rng.shuffle(train_pairs)
    rng.shuffle(val_pairs)

    with open(finetune_dir / "train.jsonl", "w", encoding='utf-8') as f:
        for pair in train_pairs:
            f.write(json.dumps(pair) + "\n")

    with open(finetune_dir / "val.jsonl", "w", encoding='utf-8') as f:
        for pair in val_pairs:
            f.write(json.dumps(pair) + "\n")

    by_source: dict[str, int] = {"reddit": 0, "web": 0, "youtube": 0}
    by_category_total: dict[str, int] = {}
    for pair in pairs:
        src = pair["meta"]["source"]
        cat = pair["meta"]["category"]
        by_source[src] = by_source.get(src, 0) + 1
        by_category_total[cat] = by_category_total.get(cat, 0) + 1

    stats: dict[str, Any] = {
        "total_pairs": len(pairs),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "by_source": by_source,
        "by_category": by_category_total,
        "by_split": by_split,
    }

    with open(finetune_dir / "stats.json", "w", encoding='utf-8') as f:
        json.dump(stats, f, indent=2)

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run the format-for-finetuning pipeline."""
    parser = argparse.ArgumentParser(
        description="Convert cleaned JSONL into ChatML instruction pairs for fine-tuning."
    )
    parser.add_argument(
        "--source",
        choices=["reddit", "web", "youtube"],
        help="Process only this source (default: all three)",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.65,
        metavar="SCORE",
        help="Minimum quality_score threshold (default: 0.65)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        metavar="SECONDS",
        help="Delay between API calls in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear the entire checkpoint before processing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count pairs without making API calls or writing output files",
    )
    parser.add_argument(
        "--max-chunks-per-video",
        type=int,
        default=3,
        metavar="N",
        help="Max chunks to keep per YouTube video, scored by tech vocab density (default: 3)",
    )
    parser.add_argument(
        "--max-pairs-per-category",
        type=int,
        default=500,
        metavar="N",
        help="Cap per category (excluding 'general') before train/val split (default: 500)",
    )
    args = parser.parse_args()

    config_path = Path(__file__).parent / "config.json"
    tech_vocab: list[str] = []
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            tech_vocab = config.get("tech_vocabulary", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not load config.json: {exc}")

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not args.dry_run and not api_key:
        print(
            "Error: CLAUDE_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = Path(__file__).parent.parent
    cleaned_dir = repo_root / "training_data" / "cleaned"
    finetune_dir = repo_root / "training_data" / "finetune"

    if not cleaned_dir.exists():
        print(
            f"Error: {cleaned_dir} does not exist. Run the cleaning pipeline first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.dry_run:
        finetune_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = finetune_dir / "checkpoint.json"
    if args.fresh and not args.dry_run and checkpoint_path.exists():
        checkpoint_path.unlink()
        logger.info("Cleared checkpoint.")

    checkpoint_ids: set[str] = set()
    if not args.dry_run:
        checkpoint_ids = load_checkpoint(finetune_dir)
        logger.info(f"Loaded {len(checkpoint_ids)} already-processed source_ids from checkpoint.")

    client: anthropic.Anthropic | None = None
    if not args.dry_run:
        client = anthropic.Anthropic(api_key=api_key)

    sources = [args.source] if args.source else ["reddit", "web", "youtube"]

    # Phase 1: load all passing records — filtering only, no API calls
    candidates: list[dict] = []
    for source in sources:
        if source == "reddit":
            candidates.extend(collect_reddit(cleaned_dir, args.min_quality, checkpoint_ids))
        elif source == "web":
            candidates.extend(collect_web(cleaned_dir, args.min_quality, checkpoint_ids))
        elif source == "youtube":
            candidates.extend(
                collect_youtube(
                    cleaned_dir,
                    args.min_quality,
                    checkpoint_ids,
                    args.max_chunks_per_video,
                    tech_vocab,
                )
            )

    pre_cap_total = len(candidates)
    pre_cap_by_cat: dict[str, int] = {}
    for c in candidates:
        pre_cap_by_cat[c["category"]] = pre_cap_by_cat.get(c["category"], 0) + 1

    # Phase 2: apply --max-pairs-per-category cap before any API calls
    candidates, _ = cap_candidates(candidates, args.max_pairs_per_category)

    if args.dry_run:
        by_source: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for c in candidates:
            by_source[c["source"]] = by_source.get(c["source"], 0) + 1
            by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1

        cost = estimate_cost(len(candidates))

        print("\nDry-run breakdown:")
        print(f"  Total pairs (pre-cap):  {pre_cap_total}")
        print(f"  Total pairs (post-cap): {len(candidates)}")
        print("  By source:")
        for src, count in sorted(by_source.items()):
            print(f"    {src}: {count}")
        print("  By category (pre-cap → post-cap):")
        for cat in sorted(pre_cap_by_cat.keys()):
            pre = pre_cap_by_cat[cat]
            post = by_cat.get(cat, 0)
            if cat == "general":
                print(f"    {cat}: {pre} (uncapped)")
            elif pre != post:
                print(f"    {cat}: {pre} → {post} (trimmed {pre - post})")
            else:
                print(f"    {cat}: {post}")
        print(f"  Estimated cost: ${cost:.2f} (based on {len(candidates)} post-cap pairs)")
        return

    # Phase 3: iterate the post-cap candidates and make API calls
    pairs: list[dict] = []
    api_calls_ref: list[int] = [0]

    for i, candidate in enumerate(candidates):
        print(
            f"\rProcessing {i + 1}/{len(candidates)} | pairs: {len(pairs)}",
            end="",
            flush=True,
        )

        source = candidate["source"]
        source_id = candidate["source_id"]
        category = candidate["category"]
        quality_score = candidate["quality_score"]
        site_or_channel = candidate["site_or_channel"]
        assistant_text = candidate["assistant_text"]

        user_text = call_api_with_retry(
            client,
            category,
            SOURCE_TYPE_LABELS[source],
            assistant_text,
            args.delay,
        )
        api_calls_ref[0] += 1

        if user_text is None:
            logger.warning(f"Failed to generate prompt for {source} source_id={source_id}")
            continue

        pairs.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ],
                "meta": {
                    "source": source,
                    "site_or_channel": site_or_channel,
                    "category": category,
                    "quality_score": quality_score,
                    "source_id": source_id,
                },
            }
        )
        checkpoint_ids.add(source_id)
        save_checkpoint(finetune_dir, source_id)

    cost = estimate_cost(api_calls_ref[0])

    if not pairs:
        print("\nNo new pairs generated.")
        return

    print()
    stats = split_and_write(pairs, finetune_dir)
    print(f"Done. {stats['train_pairs']} train / {stats['val_pairs']} val pairs written.")
    print(f"Estimated cost: ${cost:.3f}")
    print(f"Output: {finetune_dir}/")


if __name__ == "__main__":
    main()
