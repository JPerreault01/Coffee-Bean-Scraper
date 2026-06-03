#!/usr/bin/env python3
"""
build_skill_knowledge.py — Select, digest, and compile a knowledge base from the
cleaned coffee corpus. Tier 2 of the skill-writer pipeline.

Reads cleaned JSONL from training_data/cleaned/{reddit,web,youtube}/, selects the
best 50-60 sources with diversity caps, digests each via forced tool-use, and compiles
the results into skill_knowledge.json that assemble_skill.py consumes without
modification.

Usage:
  python data_pipeline/build_skill_knowledge.py --dry-run   # selection + cost, no API
  python data_pipeline/build_skill_knowledge.py             # full run
  python data_pipeline/build_skill_knowledge.py --limit 3   # cheap end-to-end test
  python data_pipeline/build_skill_knowledge.py --force     # re-digest everything
  python data_pipeline/build_skill_knowledge.py --verbose   # per-source breakdown

Inputs:
  training_data/cleaned/{reddit,web,youtube}/*.jsonl
  skill_data/sources_override.txt   (optional — one source_id per line)

Outputs:
  skill_data/selection_report.md    written before any API spend
  skill_data/digests/<id>.json      one per selected source (during Phase B)
  skill_data/checkpoint.json        processed source_ids
  skill_data/skill_knowledge.json   compiled knowledge base (assembler input)
  skill_data/skill_knowledge.md     human-readable mirror
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"

SELECTION_MIN = 50
SELECTION_MAX = 60

# Max chars sent to API per source — limits token cost, controls digest quality
TEXT_DIGEST_CAP = 6000

# Diversity caps (per site/channel)
MAX_PER_WEB_SITE = 5
MAX_PER_YT_CHANNEL = 4
MAX_PER_SUBREDDIT = 8
MIN_PER_CATEGORY = 2  # backfill categories that would otherwise be underrepresented

# Sonnet 4.6 pricing
SONNET_INPUT_PRICE_PER_M = 3.00
SONNET_OUTPUT_PRICE_PER_M = 15.00

# Estimation constants
CHARS_PER_TOKEN = 3.5
OUTPUT_TOKENS_PER_SEC = 40
EST_OUTPUT_TOKENS_PER_DIGEST = 1500   # conservative; actual varies by source length
EST_INPUT_OVERHEAD_PER_DIGEST = 800   # system + user prompt chars (overhead, not source text)

# Min text lengths per source (from test_clean_quality.py)
MIN_TEXT_LEN: dict[str, int] = {
    "reddit": 150,
    "web": 400,
    "youtube": 300,
}

# Category list (from test_clean_quality.py)
CATEGORIES: list[str] = [
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

# Priority order for assign_category (from format_for_finetuning.py)
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

# ---------------------------------------------------------------------------
# Shared helpers — match format_for_finetuning.py exactly
# ---------------------------------------------------------------------------


def assign_category(domain_tags: list[str]) -> str:
    """Assign primary category from domain_tags using CATEGORY_PRIORITY order."""
    tag_set = set(domain_tags)
    for cat in CATEGORY_PRIORITY:
        if cat in tag_set:
            return cat
    return "general"


def estimate_tokens(char_count: int) -> int:
    return max(0, int(char_count / CHARS_PER_TOKEN))


# ---------------------------------------------------------------------------
# Source ID derivation — mirrors format_for_finetuning.py
# ---------------------------------------------------------------------------


def _derive_source_id_reddit(raw: dict[str, Any]) -> str:
    if post_id := raw.get("post_id"):
        return str(post_id)
    title = raw.get("title", "")
    body = raw.get("body", "")
    return hashlib.sha256((title + body).encode()).hexdigest()[:16]


def _derive_source_id_web(raw: dict[str, Any], line_index: int) -> str:
    if url := raw.get("url"):
        return url
    return str(raw.get("site", "unknown")) + "_" + str(line_index)


def _derive_source_id_youtube(raw: dict[str, Any], record_index: int) -> str:
    return str(raw.get("video_id", f"unknown_{record_index}"))


def _safe_filename(source_id: str) -> str:
    """Convert a source_id to a filesystem-safe stem (no path separators, bounded length)."""
    safe = source_id
    for ch in ("/", "\\", ":", "?", "&", "=", "#", " ", "\t"):
        safe = safe.replace(ch, "_")
    if len(safe) > 120:
        safe = hashlib.sha256(source_id.encode()).hexdigest()[:24]
    return safe


# ---------------------------------------------------------------------------
# Primary text extraction — mirrors test_clean_quality.py / format_for_finetuning.py
# ---------------------------------------------------------------------------


def get_primary_text(record: dict[str, Any]) -> str | None:
    """Return the primary text for a record, or None if missing/wrong type."""
    source = record.get("source", "")
    raw = record.get("raw", {})
    if not isinstance(raw, dict):
        return None
    if source == "reddit":
        title = raw.get("title", "")
        body = raw.get("body", "")
        combined = (title + " " + body).strip()
        return combined if combined else None
    if source == "web":
        return raw.get("body") or None
    if source == "youtube":
        return raw.get("transcript") or None
    return None


# ---------------------------------------------------------------------------
# Phase A — Load records from cleaned corpus
# ---------------------------------------------------------------------------


def load_cleaned_records(cleaned_dir: Path) -> list[dict[str, Any]]:
    """
    Walk cleaned/{reddit,web,youtube}/*.jsonl, filter by text length, and return
    a flat list of candidate dicts. Skips malformed lines with a warning.
    """
    candidates: list[dict[str, Any]] = []

    for source_type in ("reddit", "web", "youtube"):
        source_dir = cleaned_dir / source_type
        if not source_dir.exists():
            logger.info(f"No {source_type}/ directory in cleaned corpus — skipping")
            continue

        for jsonl_file in sorted(source_dir.glob("*.jsonl")):
            site_or_channel = jsonl_file.stem
            try:
                raw_lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                logger.warning(f"Could not read {jsonl_file}: {exc}")
                continue

            for line_index, line in enumerate(raw_lines):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        f"Malformed JSON in {jsonl_file.name} line {line_index + 1}: {exc}"
                    )
                    continue

                if not isinstance(record, dict):
                    logger.warning(
                        f"Non-dict record in {jsonl_file.name} line {line_index + 1} — skipping"
                    )
                    continue

                if "source" not in record or "quality_score" not in record:
                    logger.warning(
                        f"Missing required fields in {jsonl_file.name} line {line_index + 1} — skipping"
                    )
                    continue

                primary_text = get_primary_text(record)
                if primary_text is None:
                    continue

                min_len = MIN_TEXT_LEN.get(source_type, 0)
                if len(primary_text) < min_len:
                    continue

                raw = record.get("raw", {})
                if source_type == "reddit":
                    source_id = _derive_source_id_reddit(raw)
                elif source_type == "web":
                    source_id = _derive_source_id_web(raw, line_index)
                else:
                    source_id = _derive_source_id_youtube(raw, line_index)

                truncated = len(primary_text) > TEXT_DIGEST_CAP
                if truncated:
                    logger.debug(
                        f"Truncating {source_id!r} from {len(primary_text):,} to {TEXT_DIGEST_CAP:,} chars"
                    )
                text_for_digest = primary_text[:TEXT_DIGEST_CAP]

                candidates.append({
                    "source": source_type,
                    "source_id": source_id,
                    "safe_id": _safe_filename(source_id),
                    "site_or_channel": site_or_channel,
                    "category": assign_category(record.get("domain_tags", [])),
                    "quality_score": float(record.get("quality_score", 0.0)),
                    "text": text_for_digest,
                    "text_chars": len(text_for_digest),
                    "original_chars": len(primary_text),
                    "truncated": truncated,
                })

    return candidates


# ---------------------------------------------------------------------------
# Phase A — Source selection with diversity caps
# ---------------------------------------------------------------------------

_CAP_MAX: dict[str, int] = {
    "reddit": MAX_PER_SUBREDDIT,
    "web": MAX_PER_WEB_SITE,
    "youtube": MAX_PER_YT_CHANNEL,
}


def select_sources(
    candidates: list[dict[str, Any]],
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Select SELECTION_MIN–SELECTION_MAX sources with diversity caps and category backfill.

    Strategy:
      1. Backfill: ensure every CATEGORY with ≥MIN_PER_CATEGORY corpus entries gets at
         least MIN_PER_CATEGORY sources selected (respecting site caps).
      2. Fill: greedily add highest-quality remaining sources up to target_max.

    Returns (selected, cap_excluded) where cap_excluded holds sources that were
    skipped because their site/channel hit its cap — these go in the selection report
    so Jackson can override them.
    """
    target_max = limit if limit is not None else SELECTION_MAX

    ranked = sorted(candidates, key=lambda c: -c["quality_score"])

    site_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    cap_excluded_ids: set[str] = set()
    cap_excluded: list[dict[str, Any]] = []

    def _can_add(c: dict[str, Any]) -> bool:
        return site_counts[c["site_or_channel"]] < _CAP_MAX[c["source"]]

    def _add(c: dict[str, Any]) -> None:
        selected.append(c)
        used_ids.add(c["source_id"])
        site_counts[c["site_or_channel"]] += 1
        category_counts[c["category"]] += 1

    def _mark_cap_excluded(c: dict[str, Any]) -> None:
        if c["source_id"] not in cap_excluded_ids and c["source_id"] not in used_ids:
            cap_excluded_ids.add(c["source_id"])
            cap_excluded.append(c)

    # Count how many corpus candidates exist per category
    corpus_cat_counts: dict[str, int] = defaultdict(int)
    for c in ranked:
        corpus_cat_counts[c["category"]] += 1

    # Pass 1 — backfill underrepresented categories
    for cat in CATEGORIES:
        if corpus_cat_counts.get(cat, 0) < MIN_PER_CATEGORY:
            continue  # corpus doesn't have enough for this category
        needed = MIN_PER_CATEGORY - category_counts[cat]
        if needed <= 0:
            continue

        for c in ranked:
            if len(selected) >= target_max:
                break
            if c["source_id"] in used_ids or c["category"] != cat:
                continue
            if not _can_add(c):
                _mark_cap_excluded(c)
                continue
            _add(c)
            needed -= 1
            if needed <= 0:
                break

    # Pass 2 — fill up to target_max greedily
    for c in ranked:
        if len(selected) >= target_max:
            break
        if c["source_id"] in used_ids:
            continue
        if not _can_add(c):
            _mark_cap_excluded(c)
            continue
        _add(c)

    return selected, cap_excluded


def load_override(
    override_path: Path,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """
    If sources_override.txt exists, return exactly those source_ids from the corpus.
    Lines starting with # are comments. Returns None if the file does not exist.
    """
    if not override_path.exists():
        return None

    lines = override_path.read_text(encoding="utf-8").splitlines()
    override_ids: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        override_ids.append(line)

    logger.info(
        f"Manual override: {len(override_ids)} source_ids from {override_path.name}"
    )

    id_to_candidate = {c["source_id"]: c for c in candidates}
    selected: list[dict[str, Any]] = []
    for sid in override_ids:
        if sid in id_to_candidate:
            selected.append(id_to_candidate[sid])
        else:
            logger.warning(f"Override source_id not found in corpus: {sid!r}")

    return selected


# ---------------------------------------------------------------------------
# Phase A — Selection report
# ---------------------------------------------------------------------------


def write_selection_report(
    selected: list[dict[str, Any]],
    cap_excluded: list[dict[str, Any]],
    total_candidates: int,
    report_path: Path,
    is_override: bool,
) -> None:
    """Write a human-readable markdown selection report to report_path."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Source Selection Report",
        "",
        f"*Generated: {now}*",
        "",
    ]

    if is_override:
        lines += [
            f"> **Manual override active** — `skill_data/sources_override.txt` "
            f"({len(selected)} sources).",
            "",
        ]
    else:
        lines += [
            f"**Total corpus candidates:** {total_candidates}  ",
            f"**Selected:** {len(selected)}  ",
            f"**Excluded by cap (notable):** {len(cap_excluded)}",
            "",
        ]

    # Source-type breakdown
    by_type: dict[str, int] = defaultdict(int)
    for c in selected:
        by_type[c["source"]] += 1

    lines += [
        "## Source type breakdown",
        "",
        "| Type | Count |",
        "|------|-------|",
    ]
    for st in ("reddit", "web", "youtube"):
        lines.append(f"| {st} | {by_type.get(st, 0)} |")
    lines.append("")

    # Selected sources grouped by category
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in selected:
        by_cat[c["category"]].append(c)

    total_chars = 0
    total_tokens = 0

    lines += ["## Selected sources by category", ""]

    for cat in sorted(by_cat.keys()):
        items = sorted(by_cat[cat], key=lambda x: -x["quality_score"])
        lines.append(
            f"### {cat.replace('_', ' ').title()} ({len(items)} source{'s' if len(items) != 1 else ''})"
        )
        lines.append("")
        lines.append(
            "| source_id | type | site/channel | quality | chars | ~tokens | truncated |"
        )
        lines.append(
            "|-----------|------|-------------|---------|-------|---------|-----------|"
        )
        for c in items:
            sid = c["source_id"]
            sid_display = (sid[:40] + "…") if len(sid) > 40 else sid
            toks = estimate_tokens(c["text_chars"])
            total_chars += c["text_chars"]
            total_tokens += toks
            trunc_mark = "yes" if c["truncated"] else ""
            lines.append(
                f"| `{sid_display}` | {c['source']} | {c['site_or_channel']} "
                f"| {c['quality_score']:.3f} | {c['text_chars']:,} | {toks:,} | {trunc_mark} |"
            )
        lines.append("")

    lines += [
        "## Totals",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Selected sources | {len(selected)} |",
        f"| Total chars | {total_chars:,} |",
        f"| Total ~tokens | {total_tokens:,} |",
        "",
    ]

    if cap_excluded:
        lines += [
            "## Notable sources excluded by diversity cap",
            "",
            "*These scored well but their site/channel already hit its cap.*  ",
            "*Add the `source_id` to `skill_data/sources_override.txt` to include them.*",
            "",
            "| source_id | type | site/channel | category | quality |",
            "|-----------|------|-------------|----------|---------|",
        ]
        for c in sorted(cap_excluded[:30], key=lambda x: -x["quality_score"]):
            sid = c["source_id"]
            sid_display = (sid[:40] + "…") if len(sid) > 40 else sid
            lines.append(
                f"| `{sid_display}` | {c['source']} | {c['site_or_channel']} "
                f"| {c['category']} | {c['quality_score']:.3f} |"
            )
        if len(cap_excluded) > 30:
            lines.append(f"| *(+{len(cap_excluded) - 30} more)* | | | | |")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Wrote selection report: {report_path}")


# ---------------------------------------------------------------------------
# Phase A — Dry-run analytics
# ---------------------------------------------------------------------------


def print_dry_run_analytics(
    selected: list[dict[str, Any]],
    cap_excluded: list[dict[str, Any]],
    total_candidates: int,
    verbose: bool,
    model: str,
) -> None:
    """Print selection summary + cost/time estimate. No API calls."""
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in selected:
        by_source[c["source"]].append(c)
        by_cat[c["category"]].append(c)

    total_text_chars = sum(c["text_chars"] for c in selected)
    total_text_tokens = estimate_tokens(total_text_chars)
    overhead_tokens = len(selected) * estimate_tokens(EST_INPUT_OVERHEAD_PER_DIGEST)
    total_input_tokens = total_text_tokens + overhead_tokens
    total_output_tokens = len(selected) * EST_OUTPUT_TOKENS_PER_DIGEST

    input_cost = total_input_tokens / 1_000_000 * SONNET_INPUT_PRICE_PER_M
    output_cost = total_output_tokens / 1_000_000 * SONNET_OUTPUT_PRICE_PER_M
    total_cost = input_cost + output_cost
    est_seconds = total_output_tokens / OUTPUT_TOKENS_PER_SEC

    print("\n=== Source selection summary ===")
    print(f"  Total corpus candidates : {total_candidates}")
    print(f"  Selected                : {len(selected)}")
    print(f"  Cap-excluded (notable)  : {len(cap_excluded)}")
    print()

    print("=== By source type ===")
    for st in ("reddit", "web", "youtube"):
        items = by_source.get(st, [])
        if not items:
            continue
        chars = sum(c["text_chars"] for c in items)
        toks = estimate_tokens(chars)
        avg_qs = sum(c["quality_score"] for c in items) / len(items)
        print(
            f"  {st:<8} : {len(items):>3} sources | "
            f"{chars:>8,} chars (~{toks:>6,} tok) | avg quality {avg_qs:.3f}"
        )

    print()
    print("=== By category ===")
    for cat in sorted(by_cat.keys()):
        items = by_cat[cat]
        chars = sum(c["text_chars"] for c in items)
        print(f"  {cat:<22} : {len(items):>3} sources | {chars:>8,} chars")

    if verbose:
        print()
        print("=== Per-source breakdown ===")
        print(f"  {'source':<8} {'quality':>8} {'chars':>8}  {'category':<22}  site/channel")
        print(f"  {'-'*8} {'-'*8} {'-'*8}  {'-'*22}  {'-'*25}")
        for c in sorted(selected, key=lambda x: -x["quality_score"]):
            trunc = "*" if c["truncated"] else " "
            print(
                f"  {c['source']:<8} {c['quality_score']:>8.3f} "
                f"{c['text_chars']:>7,}{trunc}  {c['category']:<22}  {c['site_or_channel']}"
            )

    print()
    print("=== Cost & time estimate ===")
    print(f"  Sources            : {len(selected)}")
    print(f"  Input tokens total : ~{total_input_tokens:>8,}")
    print(f"  Output tokens total: ~{total_output_tokens:>8,}  "
          f"(~{EST_OUTPUT_TOKENS_PER_DIGEST}/digest)")
    print(f"  Input cost         : ${input_cost:.3f}")
    print(f"  Output cost        : ${output_cost:.3f}")
    print(f"  Total cost         : ${total_cost:.3f}")
    print(
        f"  Est. wall time     : ~{est_seconds / 60:.1f} min  "
        f"(at ~{OUTPUT_TOKENS_PER_SEC} tok/s output)"
    )
    print()
    print(
        "(Dry run — no API calls made. "
        "Re-run without --dry-run to proceed.)"
    )


# ---------------------------------------------------------------------------
# Phase B — Digest tool schema
# ---------------------------------------------------------------------------

DIGEST_TOOL: dict[str, Any] = {
    "name": "record_source_digest",
    "description": (
        "Record the structured knowledge extracted from this coffee source. "
        "Be concrete and faithful — never invent claims the source did not make. "
        "Opinions and qualified statements belong in contested_claims, not "
        "consensus_claims. This is the only way to return your findings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "What this source covers and its main argument or focus."
                ),
            },
            "consensus_claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Settled facts stated without qualification in this source. "
                    "Only include claims the source presents as established."
                ),
            },
            "contested_claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Claims with caveats, qualifications, or acknowledged complexity. "
                    "Include opinions and debated points here."
                ),
            },
            "technical_vocabulary": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "usage": {
                            "type": "string",
                            "description": "How this source uses or defines this term.",
                        },
                    },
                    "required": ["term", "usage"],
                },
                "description": (
                    "Technical coffee terms and how this source uses each one. "
                    "Array of {term, usage} objects."
                ),
            },
            "community_framing": {
                "type": "string",
                "description": (
                    "What this community or source prioritizes in coffee decisions. "
                    "What does it care about most?"
                ),
            },
            "tasting_descriptors": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Sensory words and phrases used in this source to describe coffee."
                ),
            },
            "key_insights": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Specific, concrete insights from this source that would improve "
                    "a coffee review."
                ),
            },
            "source_perspective": {
                "type": "string",
                "description": (
                    "What angle or perspective distinguishes this source from a generic "
                    "coffee overview."
                ),
            },
            "products_or_topics_referenced": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Products, equipment, origins, or specific topics named in this source."
                ),
            },
        },
        "required": [
            "summary",
            "consensus_claims",
            "contested_claims",
            "technical_vocabulary",
            "community_framing",
            "tasting_descriptors",
            "key_insights",
            "source_perspective",
            "products_or_topics_referenced",
        ],
    },
}

DIGEST_SYSTEM = (
    "You are a coffee-knowledge analyst extracting reusable, source-attributed "
    "knowledge for a review-writing skill. You read a single coffee source and "
    "extract structured knowledge from it. You are concrete and faithful to the "
    "source — never invent claims the source did not make. When a claim is the "
    "source's opinion rather than settled fact, it belongs in contested_claims, "
    "not consensus_claims. You record your findings exclusively by calling the "
    "record_source_digest tool."
)


def _build_digest_prompt(candidate: dict[str, Any]) -> str:
    trunc_note = " [truncated to 6000 chars]" if candidate["truncated"] else ""
    return (
        f"Extract structured knowledge from this coffee source.\n\n"
        f"Source type: {candidate['source']}\n"
        f"Category: {candidate['category']}\n"
        f"Site/channel: {candidate['site_or_channel']}\n\n"
        f"--- SOURCE TEXT{trunc_note} ---\n"
        f"{candidate['text']}\n"
        f"--- END SOURCE TEXT ---\n\n"
        "Extract only what this source actually says. "
        "Do not attribute any claims beyond what the text supports. "
        "Call the record_source_digest tool to record your findings."
    )


# ---------------------------------------------------------------------------
# Phase B — Tool-use extraction helpers (mirrors build_voice_profile.py)
# ---------------------------------------------------------------------------


def _extract_tool_input(response: Any) -> dict[str, Any] | None:
    """Pull the record_source_digest tool input from a response."""
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and block.name == "record_source_digest"
        ):
            return dict(block.input)
    return None


def _text_fallback_parse(response: Any) -> dict[str, Any] | None:
    """
    Defence in depth: if the model returned text instead of a tool call,
    attempt to recover JSON from the text (strict parse, then json_repair).
    """
    text_blocks = [
        getattr(b, "text", "")
        for b in response.content
        if getattr(b, "type", None) == "text"
    ]
    raw = "\n".join(t for t in text_blocks if t).strip()
    if not raw:
        return None

    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("`").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    try:
        from json_repair import repair_json  # type: ignore
        logger.info("Recovered digest from text via json_repair")
        return json.loads(repair_json(raw))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Phase B — Digest a single source
# ---------------------------------------------------------------------------


def digest_source(
    candidate: dict[str, Any],
    client: anthropic.Anthropic,
    model: str,
) -> dict[str, Any] | None:
    """
    Call the API with forced tool use to digest a single source.
    Retries 3 times on transient errors (exponential backoff: 1s, 2s, 4s).
    Returns the parsed digest dict, or None if all attempts fail.
    """
    prompt = _build_digest_prompt(candidate)
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=DIGEST_SYSTEM,
                tools=[DIGEST_TOOL],
                tool_choice={"type": "tool", "name": "record_source_digest"},
                messages=[{"role": "user", "content": prompt}],
            )

            if response.stop_reason == "max_tokens":
                logger.warning(
                    f"max_tokens hit for {candidate['source_id']!r} — "
                    "digest may be incomplete"
                )

            digest = _extract_tool_input(response)
            if digest is not None:
                return digest

            logger.warning(
                f"No tool_use block for {candidate['source_id']!r}; "
                "trying text fallback"
            )
            digest = _text_fallback_parse(response)
            if digest is not None:
                return digest

            logger.warning(
                f"Attempt {attempt + 1}: no usable output for {candidate['source_id']!r}"
            )

        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            last_err = exc
            wait = 2 ** attempt
            logger.error(f"API error attempt {attempt + 1}: {exc} — retrying in {wait}s")
            time.sleep(wait)
        except anthropic.APIError as exc:
            last_err = exc
            logger.error(f"API error attempt {attempt + 1}: {exc}")

    logger.error(
        f"All attempts failed for {candidate['source_id']!r}. Last error: {last_err}"
    )
    return None


# ---------------------------------------------------------------------------
# Checkpoint helpers (mirrors format_for_finetuning.py)
# ---------------------------------------------------------------------------


def load_checkpoint(checkpoint_path: Path) -> set[str]:
    if not checkpoint_path.exists():
        return set()
    try:
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load checkpoint: {exc}")
        return set()


def save_checkpoint(checkpoint_path: Path, processed_ids: set[str]) -> None:
    """Atomically write checkpoint via a temp file."""
    tmp = checkpoint_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(processed_ids), indent=2), encoding="utf-8")
    tmp.replace(checkpoint_path)


# ---------------------------------------------------------------------------
# Phase C — Compile per-source digests into skill_knowledge.json
# ---------------------------------------------------------------------------


def compile_knowledge(
    selected: list[dict[str, Any]],
    digests: dict[str, dict[str, Any]],
    model: str,
) -> dict[str, Any]:
    """
    Compile per-source digests into a single skill_knowledge.json.
    Schema matches exactly what assemble_skill.py reads from split_knowledge_to_files().
    """
    consensus_claims: list[dict[str, Any]] = []
    contested_claims: list[dict[str, Any]] = []
    vocab_raw: dict[str, list[str]] = defaultdict(list)
    tasting_set: set[str] = set()
    community_framing: list[dict[str, Any]] = []
    key_insights: list[dict[str, Any]] = []

    source_type_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)

    for c in selected:
        source_id = c["source_id"]
        digest = digests.get(source_id)
        if not digest:
            continue

        category = c["category"]
        source_type_counts[c["source"]] += 1
        category_counts[category] += 1

        # consensus_claims — assemble_skill reads item["claim"], item["category"], item["source"]
        for claim in digest.get("consensus_claims", []):
            if isinstance(claim, str) and claim.strip():
                consensus_claims.append({
                    "claim": claim.strip(),
                    "category": category,
                    "source": source_id,
                })

        # contested_claims — same shape
        for claim in digest.get("contested_claims", []):
            if isinstance(claim, str) and claim.strip():
                contested_claims.append({
                    "claim": claim.strip(),
                    "category": category,
                    "source": source_id,
                })

        # technical_vocabulary — digest produces [{term, usage}]; compiler folds to dict
        for entry in digest.get("technical_vocabulary", []):
            if isinstance(entry, dict):
                term = entry.get("term", "").strip().lower()
                usage = entry.get("usage", "").strip()
                if term and usage:
                    vocab_raw[term].append(usage)
            elif isinstance(entry, str) and entry.strip():
                # Graceful handling if model returns plain strings despite schema
                vocab_raw[entry.strip().lower()].append(entry.strip())

        # tasting_descriptors — deduplicated list of strings
        for desc in digest.get("tasting_descriptors", []):
            if isinstance(desc, str) and desc.strip():
                tasting_set.add(desc.strip().lower())

        # community_framing — assemble_skill reads item["source"], item["framing"]
        framing = digest.get("community_framing", "")
        if isinstance(framing, str) and framing.strip():
            community_framing.append({
                "source": source_id,
                "framing": framing.strip(),
            })

        # key_insights — assemble_skill reads item["insight"], item["category"], item["source"]
        for insight in digest.get("key_insights", []):
            if isinstance(insight, str) and insight.strip():
                key_insights.append({
                    "insight": insight.strip(),
                    "category": category,
                    "source": source_id,
                })

    # Compile vocabulary dict: term → longest usage (most informative when sources differ)
    vocabulary: dict[str, Any] = {}
    for term, usages in sorted(vocab_raw.items()):
        vocabulary[term] = max(usages, key=len)

    tasting_descriptors = sorted(tasting_set)

    meta: dict[str, Any] = {
        "total_sources": len(digests),
        "categories": sorted(category_counts.keys()),
        "per_source_type": dict(source_type_counts),
        "per_category": dict(category_counts),
        "digest_model": model,
        "build_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "total_consensus_claims": len(consensus_claims),
        "total_contested_claims": len(contested_claims),
        "total_vocabulary_terms": len(vocabulary),
        "total_tasting_descriptors": len(tasting_descriptors),
        "total_key_insights": len(key_insights),
    }

    return {
        "consensus_claims": consensus_claims,
        "contested_claims": contested_claims,
        "vocabulary": vocabulary,
        "tasting_descriptors": tasting_descriptors,
        "community_framing": community_framing,
        "key_insights": key_insights,
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# Phase D — Human-readable markdown mirror
# ---------------------------------------------------------------------------


def render_knowledge_md(knowledge: dict[str, Any]) -> str:
    """Render a readable markdown version of skill_knowledge.json."""
    meta = knowledge.get("meta", {})
    lines: list[str] = [
        "# Skill Knowledge Base",
        "",
        f"*Built: {meta.get('build_timestamp', 'unknown')}*  ",
        f"*Model: {meta.get('digest_model', 'unknown')}*  ",
        f"*Sources: {meta.get('total_sources', 0)}*",
        "",
    ]

    def _append_claims(
        section_title: str,
        intro: str,
        items: list[dict[str, Any]],
    ) -> None:
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(f"*{intro}*")
        lines.append("")
        by_cat: dict[str, list[str]] = defaultdict(list)
        for item in items:
            by_cat[item["category"]].append(
                f"- {item['claim']} *(via {item['source']})*"
            )
        for cat in sorted(by_cat.keys()):
            lines.append(f"### {cat.replace('_', ' ').title()}")
            lines.append("")
            lines.extend(by_cat[cat])
            lines.append("")

    _append_claims(
        "Consensus Claims",
        "What the curated sources agree on. State with confidence in reviews.",
        knowledge.get("consensus_claims", []),
    )

    _append_claims(
        "Contested Claims",
        "Where sources disagree or qualify. Take a stance — do not summarise the debate.",
        knowledge.get("contested_claims", []),
    )

    lines += [
        "## Technical Vocabulary",
        "",
        "*Coffee terms with definitions from the corpus.*",
        "",
    ]
    for term, usage in sorted(knowledge.get("vocabulary", {}).items()):
        if isinstance(usage, list):
            lines.append(f"**{term}**")
            for u in usage:
                lines.append(f"  - {u}")
        else:
            lines.append(f"**{term}**: {usage}")
        lines.append("")

    lines += [
        "## Tasting Descriptors",
        "",
        "*Sensory vocabulary from the corpus. Use these descriptors.*",
        "",
    ]
    descriptors = knowledge.get("tasting_descriptors", [])
    if descriptors:
        lines.append(", ".join(descriptors))
        lines.append("")
    else:
        lines.append("*(empty — re-run build_skill_knowledge.py)*")
        lines.append("")

    lines += [
        "## Community Framing",
        "",
        "*How each source community prioritizes coffee decisions.*",
        "",
    ]
    for item in knowledge.get("community_framing", []):
        lines.append(f"**{item['source']}**")
        lines.append("")
        lines.append(item["framing"])
        lines.append("")

    lines += [
        "## Key Insights by Category",
        "",
        "*Concrete insights from the corpus.*",
        "",
    ]
    by_cat: dict[str, list[str]] = defaultdict(list)
    for item in knowledge.get("key_insights", []):
        by_cat[item["category"]].append(
            f"- {item['insight']} *(via {item['source']})*"
        )
    for cat in sorted(by_cat.keys()):
        lines.append(f"### {cat.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(by_cat[cat])
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-run coverage summary
# ---------------------------------------------------------------------------


def print_coverage_summary(knowledge: dict[str, Any]) -> None:
    meta = knowledge.get("meta", {})
    print("\n=== Knowledge base coverage ===")
    print(f"  Sources digested    : {meta.get('total_sources', 0)}")
    print(f"  Consensus claims    : {meta.get('total_consensus_claims', 0)}")
    print(f"  Contested claims    : {meta.get('total_contested_claims', 0)}")
    print(f"  Vocabulary terms    : {meta.get('total_vocabulary_terms', 0)}")
    print(f"  Tasting descriptors : {meta.get('total_tasting_descriptors', 0)}")
    print(f"  Key insights        : {meta.get('total_key_insights', 0)}")
    print()
    print("  By source type:")
    for st, count in sorted(meta.get("per_source_type", {}).items()):
        print(f"    {st:<10} : {count}")
    print()
    print("  By category:")
    for cat, count in sorted(meta.get("per_category", {}).items()):
        print(f"    {cat:<22} : {count}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tier 2: digest cleaned coffee sources into a structured knowledge base "
            "for the skill-writer pipeline."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Phase A only: selection + selection_report.md + cost/time estimate. "
            "No API calls. Run this first before spending money."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Per-source breakdown in the analytics output.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Digest model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Cap selection at N sources (for cheap test runs, e.g. --limit 3).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Explicitly continue from checkpoint. "
            "This is also the implicit default — re-running always skips completed digests."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore checkpoint and re-digest all selected sources from scratch.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    cleaned_dir = repo_root / "training_data" / "cleaned"
    skill_data_dir = repo_root / "skill_data"
    digests_dir = skill_data_dir / "digests"
    override_path = skill_data_dir / "sources_override.txt"
    checkpoint_path = skill_data_dir / "checkpoint.json"
    report_path = skill_data_dir / "selection_report.md"
    knowledge_json_path = skill_data_dir / "skill_knowledge.json"
    knowledge_md_path = skill_data_dir / "skill_knowledge.md"

    skill_data_dir.mkdir(parents=True, exist_ok=True)
    digests_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase A: Load ──────────────────────────────────────────────────────
    if not cleaned_dir.exists():
        logger.warning(
            f"Cleaned corpus not found at {cleaned_dir}. "
            "Run the cleaning pipeline first, or use --dry-run to preview with 0 sources."
        )
        candidates: list[dict[str, Any]] = []
    else:
        logger.info(f"Loading cleaned records from {cleaned_dir} …")
        candidates = load_cleaned_records(cleaned_dir)
        logger.info(f"Loaded {len(candidates)} candidates after text-length filter")

    # ── Phase A: Select ────────────────────────────────────────────────────
    override_result = load_override(override_path, candidates)
    is_override = override_result is not None

    if is_override:
        selected = override_result
        cap_excluded: list[dict[str, Any]] = []
    else:
        selected, cap_excluded = select_sources(candidates, limit=args.limit)

    logger.info(f"Selected {len(selected)} sources for digestion")

    # ── Phase A: Selection report ──────────────────────────────────────────
    write_selection_report(
        selected, cap_excluded, len(candidates), report_path, is_override
    )

    if args.dry_run:
        print_dry_run_analytics(
            selected, cap_excluded, len(candidates), args.verbose, args.model
        )
        return

    # ── Live run: require API key ──────────────────────────────────────────
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: CLAUDE_API_KEY / ANTHROPIC_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # ── Checkpoint ─────────────────────────────────────────────────────────
    if args.force:
        processed_ids: set[str] = set()
        logger.info("--force: ignoring checkpoint, re-digesting all selected sources")
    else:
        processed_ids = load_checkpoint(checkpoint_path)
        if processed_ids:
            logger.info(
                f"Resuming: {len(processed_ids)} source_ids already in checkpoint"
            )

    # ── Phase B: Load already-complete digests ─────────────────────────────
    digests: dict[str, dict[str, Any]] = {}
    for c in selected:
        digest_path = digests_dir / f"{c['safe_id']}.json"
        if c["source_id"] in processed_ids and digest_path.exists():
            try:
                outer = json.loads(digest_path.read_text(encoding="utf-8"))
                # Digest files have shape {source_id, source_meta, digest}
                digest = outer.get("digest", outer)
                digests[c["source_id"]] = digest
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Could not reload digest {digest_path.name}: {exc}")

    to_process = [c for c in selected if c["source_id"] not in digests]
    logger.info(
        f"Need to digest {len(to_process)} sources "
        f"({len(digests)} already complete from checkpoint)"
    )

    # ── Phase B: Digest ────────────────────────────────────────────────────
    for i, c in enumerate(to_process):
        source_id = c["source_id"]
        logger.info(
            f"[{i + 1}/{len(to_process)}] Digesting {c['source']} "
            f"{source_id[:60]!r} …"
        )

        digest = digest_source(c, client, args.model)

        if digest is None:
            logger.error(f"Failed to digest {source_id!r} — skipping")
            continue

        # Write digest file: outer wrapper preserves metadata alongside the digest
        digest_file = digests_dir / f"{c['safe_id']}.json"
        meta_copy = {k: v for k, v in c.items() if k != "text"}
        digest_file.write_text(
            json.dumps(
                {"source_id": source_id, "source_meta": meta_copy, "digest": digest},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        digests[source_id] = digest
        processed_ids.add(source_id)
        save_checkpoint(checkpoint_path, processed_ids)

        logger.info(
            f"  → {len(digest.get('consensus_claims', []))} consensus | "
            f"{len(digest.get('contested_claims', []))} contested | "
            f"{len(digest.get('tasting_descriptors', []))} descriptors | "
            f"{len(digest.get('key_insights', []))} insights"
        )

    # ── Phase C: Compile ───────────────────────────────────────────────────
    logger.info("Compiling knowledge base …")
    knowledge = compile_knowledge(selected, digests, args.model)

    # ── Phase D: Write outputs ─────────────────────────────────────────────
    knowledge_json_path.write_text(
        json.dumps(knowledge, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Wrote {knowledge_json_path}")

    knowledge_md_path.write_text(render_knowledge_md(knowledge), encoding="utf-8")
    logger.info(f"Wrote {knowledge_md_path}")

    print_coverage_summary(knowledge)

    print()
    print("✅ Tier 2 complete.")
    print(f"   {knowledge_json_path}")
    print(f"   {knowledge_md_path}")
    print(f"   {report_path}")
    print(f"   {digests_dir}/  ({len(digests)} digests)")
    print()
    print(
        "Next: run `python data_pipeline/assemble_skill.py` to assemble the final skill."
    )


if __name__ == "__main__":
    main()
