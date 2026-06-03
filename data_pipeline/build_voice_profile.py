#!/usr/bin/env python3
"""
build_voice_profile.py — Extract a structured voice profile from Jackson's own
writing samples. Tier 1 of the skill-writer pipeline.

The output gets used by assemble_skill.py to build the final skill folder.

Usage:
  python data_pipeline/build_voice_profile.py
  python data_pipeline/build_voice_profile.py --dry-run    # full analytics, no API call
  python data_pipeline/build_voice_profile.py --model claude-sonnet-4-6
  python data_pipeline/build_voice_profile.py --verbose    # per-file breakdown

Input folder structure (create this and drop your files in):
  voice_materials/
  ├── articles/          your written articles — FORMAT EXEMPLARS + VOICE (highest weight)
  ├── podcasts/          podcast transcripts — CONTENT + OPINIONS + ARGUMENT STRUCTURE (medium weight)
  └── reddit/            Reddit posts + comments — VOICE SIGNAL ONLY (lowest weight)

How the three tiers are used:
  ARTICLES (highest):
    Written, structured pieces. These are the target written voice AND format templates.
    Phrasing is preserved exactly. Structural patterns here take precedence over all else.

  PODCASTS (medium):
    Good content signal. Opinions, argument structure, how you frame a position,
    content depth, and knowledge are all valid extractions from podcasts.
    They should NOT become format templates — spoken cadence ≠ published prose —
    but they carry more weight than Reddit for understanding what you know,
    what you believe, and how you build a case.

  REDDIT (lowest):
    Casual register. Useful for vocabulary, informal opinions, and tics.
    Do not treat as format or content authority.

Reliability note:
  Extraction uses the API's TOOL-USE / structured-output mode. The model is
  forced to return its profile as a constrained tool call, so the output is a
  parsed dict — not hand-written JSON. This eliminates the malformed-JSON
  failures (unescaped quotes from source material) that plagued the text-mode
  approach. A json_repair fallback remains as defence in depth.

Outputs:
  skill_data/voice/voice_profile.md     extracted voice DNA
  skill_data/voice/never_say.md         off-voice phrases and AI-isms
  skill_data/voice/exemplars/           clean copies of your articles
  skill_data/voice/extraction_raw.json  raw model output (for debugging)

Supported file formats:
  .md, .txt — read as plain text
  .json     — read full JSON content (e.g. Reddit JSON exports)

Best practices:
  - Include 5–15 articles minimum for voice DNA to stabilize
  - Mix article lengths (short and long both reveal different patterns)
  - Include recent material (writing styles drift over time)
  - DO NOT include AI-generated drafts — they poison the extraction
"""

import argparse
import json
import logging
import os
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"

# Token estimation (rough — ~3.5 chars per token for English prose)
CHARS_PER_TOKEN = 3.5
MAX_INPUT_TOKENS = 150_000  # leave headroom in Sonnet's 200k+ context
MAX_OUTPUT_TOKENS = 16_000  # well within Sonnet 4.6's 64k output ceiling

SONNET_INPUT_PRICE_PER_M = 3.00
SONNET_OUTPUT_PRICE_PER_M = 15.00

SUPPORTED_EXTS = {".md", ".txt", ".json"}

# Output speed for time estimate (Sonnet ~46 t/s observed; use conservative 40)
OUTPUT_TOKENS_PER_SEC = 40

# ---------------------------------------------------------------------------
# Voice extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = (
    "You are a voice profiler extracting the authentic written voice of a coffee "
    "writer. You read their actual writing and produce a structured profile that "
    "another AI will use to write in their voice. You are precise, concrete, and "
    "never invent patterns that aren't in the samples. Be exhaustive — this profile "
    "is built once and used to generate hundreds of reviews, so more specific "
    "evidence produces better output. Do not summarise when you can quote. Do not "
    "generalise when you can be specific. You record your findings exclusively by "
    "calling the record_voice_profile tool."
)

EXTRACTION_PROMPT_TEMPLATE = """Extract a voice profile from this coffee writer's own materials. The output will be saved as a skill that lets an AI write coffee reviews in this person's voice.

The materials are TAGGED by source type with explicit weighting rules:

  ===ARTICLE===
    Weight: HIGHEST.
    Written, edited, published pieces. These are the TARGET WRITTEN VOICE.
    Use these as format templates AND voice exemplars. Structural patterns
    that appear here take precedence over everything else. Sentence shape,
    paragraph rhythm, opening and closing moves — all come from articles.

  ===PODCAST===
    Weight: MEDIUM-HIGH.
    Spoken transcripts, but content-rich. Extract heavily from these for:
      - Specific opinions and positions on coffee topics
      - How arguments are built and defended
      - Depth of knowledge and which topics the writer dwells on
      - Vocabulary and terminology (carry these into the written voice)
      - Recurring stances and what the writer cares about
    Do NOT import spoken sentence structure into the written voice profile.
    The content and worldview from podcasts is high-signal. The syntax is not.

  ===REDDIT===
    Weight: LOW.
    Casual register. Use only for informal vocabulary, off-the-cuff opinions
    (supporting evidence, not primary signal), and verbal tics that also
    appear elsewhere. Do not treat structure or phrasing from Reddit as a target.

WEIGHTING RULE: When the same opinion appears in both an article and a podcast,
treat the article phrasing as canonical. When a topic appears in podcasts but
not articles, it is still valid content signal — record it under
podcast_only_signals so the assembler knows it's unverified against the written
register.

--- MATERIALS ---
{materials}
--- END MATERIALS ---

Extract a thorough, exhaustive voice profile and record it by calling the
record_voice_profile tool. Be specific and concrete at every point. Pull actual
examples from the materials and cite the source filename in parentheses. Do not
generalise. Do not invent. If a field has insufficient evidence, say so
explicitly in that field rather than filling it with assumptions.

For vocabulary and tics especially: aim for the maximum count. It is better to
include 25 vocabulary items with citations than 10 vague ones. Every specific
data point improves the hundreds of reviews this profile will generate."""


# ---------------------------------------------------------------------------
# Tool schema — forces structured output, eliminates JSON parse failures
# ---------------------------------------------------------------------------

VOICE_PROFILE_TOOL: dict[str, Any] = {
    "name": "record_voice_profile",
    "description": (
        "Record the extracted voice profile. Every field must be grounded in the "
        "provided materials with source citations. This is the only way to return "
        "your findings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tone": {
                "type": "string",
                "description": "3-4 sentences on overall tone, with at least two specific example phrases quoted from samples (cite source file for each).",
            },
            "sentence_patterns": {
                "type": "object",
                "properties": {
                    "length_preference": {
                        "type": "string",
                        "description": "short/medium/long/varied — with evidence from articles specifically.",
                    },
                    "structure": {
                        "type": "string",
                        "description": "how sentences are typically built; cite article examples.",
                    },
                    "rhythm": {
                        "type": "string",
                        "description": "pacing and rhythm patterns; note if podcast material corroborates.",
                    },
                    "examples": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "5 actual sentences from articles exemplifying the typical style (cite source for each).",
                    },
                },
                "required": ["length_preference", "structure", "rhythm", "examples"],
            },
            "vocabulary_signature": {
                "type": "array",
                "items": {"type": "string"},
                "description": "20-35 distinctive words/phrases, each with source and a note on whether it appears in articles, podcasts, or both. Prioritise cross-source items.",
            },
            "stance_patterns": {
                "type": "string",
                "description": "3-4 sentences on how this writer takes positions (assertive/hedged/qualified, and when each happens). Note written vs spoken differences.",
            },
            "content_depth_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "5-10 topics/products/areas where podcast material shows deeper knowledge or stronger opinions than articles alone, each with description and source citation.",
            },
            "opening_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 patterns used to open pieces, each with a direct example. Prefer article examples; note podcast overlap.",
            },
            "closing_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 patterns used to close pieces, each with a direct example. Prefer article examples.",
            },
            "transition_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 ways the writer moves between ideas, each with a direct example. Prefer article examples.",
            },
            "specific_tics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "8-15 verbal/textual quirks (punctuation habits, capitalisation, repeated moves, filler), each noting source type.",
            },
            "never_say_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "8-15 words/phrases/moves this writer does NOT use, inferred from absence across all sources.",
            },
            "ai_isms_to_avoid": {
                "type": "array",
                "items": {"type": "string"},
                "description": "12-20 AI clichés that conflict with this voice (e.g. 'delve into', 'it's worth noting', 'in the world of coffee').",
            },
            "topic_stances": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "stance": {"type": "string", "description": "the writer's specific position on this topic."},
                        "source": {"type": "string", "description": "source citation + whether signal is from article, podcast, or both."},
                    },
                    "required": ["topic", "stance"],
                },
                "description": "Every coffee topic where the writer has expressed a clear view, as discrete objects.",
            },
            "podcast_only_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "0-10 knowledge areas/opinions appearing in podcasts but NOT articles. Empty list if none.",
            },
            "format_exemplar_ranking": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-7 ARTICLE filenames that best exemplify the target written voice, ranked strongest to weakest. Articles only.",
            },
            "notes_for_assembler": {
                "type": "string",
                "description": "2-3 sentences flagging gaps in evidence, surprising patterns, source-type conflicts, or where more material would help.",
            },
        },
        "required": [
            "tone", "sentence_patterns", "vocabulary_signature", "stance_patterns",
            "content_depth_signals", "opening_patterns", "closing_patterns",
            "transition_patterns", "specific_tics", "never_say_list",
            "ai_isms_to_avoid", "topic_stances", "podcast_only_signals",
            "format_exemplar_ranking", "notes_for_assembler",
        ],
    },
}


# ---------------------------------------------------------------------------
# Material loading
# ---------------------------------------------------------------------------


def read_file(path: Path) -> str:
    """Read a file and return its text content. Handles .md, .txt, .json."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning(f"Could not read {path}: {exc}")
        return ""

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw)
            return _flatten_json(data)
        except json.JSONDecodeError:
            return raw
    return raw


def _flatten_json(obj: Any, depth: int = 0) -> str:
    """Flatten nested JSON into readable text. Useful for Reddit JSON exports."""
    if depth > 6:
        return "..."
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if obj is None:
        return ""
    if isinstance(obj, list):
        return "\n".join(_flatten_json(x, depth + 1) for x in obj if x)
    if isinstance(obj, dict):
        for key in ("title", "selftext", "body", "text", "content", "transcript"):
            if key in obj and obj[key]:
                return _flatten_json(obj[key], depth + 1)
        parts = []
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            sub = _flatten_json(v, depth + 1)
            if sub and len(sub) > 20:
                parts.append(sub)
        return "\n".join(parts)
    return ""


def load_materials(voice_dir: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Walk voice_materials/, return list of materials with metadata."""
    materials: list[dict[str, Any]] = []
    counts: dict[str, int] = {"articles": 0, "reddit": 0, "podcasts": 0}

    for source_type in ("articles", "podcasts", "reddit"):
        subdir = voice_dir / source_type
        if not subdir.exists():
            logger.info(f"No {source_type}/ subfolder — skipping")
            continue

        for path in sorted(subdir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTS:
                continue

            content = read_file(path).strip()
            if len(content) < 100:
                logger.warning(f"Skip {path} — too short ({len(content)} chars)")
                continue

            materials.append({
                "filename": path.name,
                "rel_path": str(path.relative_to(voice_dir)),
                "abs_path": str(path),
                "source_type": source_type,
                "content": content,
                "char_count": len(content),
            })
            counts[source_type] += 1

    return materials, counts


def build_materials_blob(materials: list[dict[str, Any]]) -> str:
    """Concatenate materials with type tags into one prompt input."""
    type_tag = {
        "articles": "===ARTICLE===",
        "podcasts": "===PODCAST===",
        "reddit": "===REDDIT===",
    }
    parts: list[str] = []
    for m in materials:
        tag = type_tag.get(m["source_type"], "===UNKNOWN===")
        parts.append(f"\n\n{tag}  filename: {m['filename']}\n\n{m['content']}\n")
    return "".join(parts)


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# Analytics (dry-run)
# ---------------------------------------------------------------------------


def print_analytics(materials: list[dict[str, Any]], counts: dict[str, int],
                    verbose: bool) -> None:
    """Print a detailed breakdown of loaded materials."""
    by_type: dict[str, list[dict[str, Any]]] = {"articles": [], "podcasts": [], "reddit": []}
    for m in materials:
        by_type[m["source_type"]].append(m)

    total_chars = sum(m["char_count"] for m in materials)
    total_tokens = estimate_tokens(build_materials_blob(materials))

    label = {
        "articles": "Articles (format + voice — highest weight)",
        "podcasts": "Podcasts (content + opinions — medium-high weight)",
        "reddit":   "Reddit   (voice signal only — lowest weight)",
    }

    print("\n=== Voice materials loaded ===")
    for st in ("articles", "podcasts", "reddit"):
        items = by_type[st]
        if not items:
            print(f"  {label[st]}: 0 files")
            continue
        chars = sum(m["char_count"] for m in items)
        toks = estimate_tokens("".join(m["content"] for m in items))
        share = (chars / total_chars * 100) if total_chars else 0
        avg = chars // len(items)
        print(f"  {label[st]}")
        print(f"      {len(items)} files | {chars:,} chars (~{toks:,} tok) "
              f"| {share:.0f}% of corpus | avg {avg:,} chars/file")

    print(f"\n  TOTAL: {len(materials)} files | {total_chars:,} chars "
          f"| ~{total_tokens:,} input tokens")

    # Per-file table (verbose only)
    if verbose:
        print("\n=== Per-file breakdown ===")
        print(f"  {'source':<9} {'tokens':>7}  filename")
        print(f"  {'-'*9} {'-'*7}  {'-'*30}")
        for st in ("articles", "podcasts", "reddit"):
            for m in sorted(by_type[st], key=lambda x: -x["char_count"]):
                toks = estimate_tokens(m["content"])
                print(f"  {st:<9} {toks:>7,}  {m['filename']}")

    # --- Balance & quality diagnostics ---
    diagnostics: list[str] = []

    if counts["articles"] == 0:
        diagnostics.append("❌ No articles. The profile NEEDS articles as format "
                           "exemplars. Add 3-5 written pieces before running.")
    elif counts["articles"] < 3:
        diagnostics.append(f"⚠️  Only {counts['articles']} article(s). Voice DNA "
                           "stabilises at 5-15. Output will be less reliable.")
    elif counts["articles"] < 5:
        diagnostics.append(f"⚠️  {counts['articles']} articles is workable but "
                           "5-15 gives a more stable profile.")
    else:
        diagnostics.append(f"✓ {counts['articles']} articles — good sample size.")

    # Article length spread
    article_items = by_type["articles"]
    if article_items:
        lengths = sorted(m["char_count"] for m in article_items)
        shortest, longest = lengths[0], lengths[-1]
        if longest > 8 * max(shortest, 1):
            diagnostics.append("✓ Good length variety in articles (short + long "
                               "both reveal patterns).")
        else:
            diagnostics.append("ℹ️  Articles are similar in length. A mix of short "
                               "and long pieces reveals more patterns.")
        tiny = [m["filename"] for m in article_items if m["char_count"] < 600]
        if tiny:
            diagnostics.append(f"ℹ️  Very short article(s): {', '.join(tiny)} "
                               "— fine, but contribute little structural signal.")

    # Reddit dominance check
    reddit_chars = sum(m["char_count"] for m in by_type["reddit"])
    if total_chars and reddit_chars / total_chars > 0.35:
        diagnostics.append("⚠️  Reddit is >35% of the corpus by volume. It's the "
                           "lowest-weight source — consider adding more articles "
                           "so casual register doesn't dominate the input.")

    # Single huge file check
    if materials:
        biggest = max(materials, key=lambda m: m["char_count"])
        if total_chars and biggest["char_count"] / total_chars > 0.5:
            diagnostics.append(f"⚠️  '{biggest['filename']}' is >50% of the entire "
                               "corpus. One file dominating can skew the profile "
                               "toward its style.")

    print("\n=== Diagnostics ===")
    for d in diagnostics:
        print(f"  {d}")


def print_cost_and_time(input_tokens: int) -> None:
    output_tokens_est = 13_000  # near the 16k ceiling for exhaustive extraction
    input_cost = input_tokens / 1_000_000 * SONNET_INPUT_PRICE_PER_M
    output_cost = output_tokens_est / 1_000_000 * SONNET_OUTPUT_PRICE_PER_M
    total_cost = input_cost + output_cost
    est_seconds = output_tokens_est / OUTPUT_TOKENS_PER_SEC

    print("\n=== Cost & time estimate ===")
    print(f"  Input:  {input_tokens:>7,} tok  →  ${input_cost:.3f}")
    print(f"  Output: ~{output_tokens_est:,} tok  →  ${output_cost:.3f}  (16k budget)")
    print(f"  Total cost: ${total_cost:.3f}")
    print(f"  Est. wall time: ~{est_seconds/60:.1f} min "
          f"(at ~{OUTPUT_TOKENS_PER_SEC} tok/s output)")


# ---------------------------------------------------------------------------
# Extraction (tool-use / structured output)
# ---------------------------------------------------------------------------


def _extract_tool_input(response: Any) -> dict[str, Any] | None:
    """Pull the record_voice_profile tool input out of a response."""
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_voice_profile":
            return dict(block.input)
    return None


def _text_fallback_parse(response: Any) -> dict[str, Any] | None:
    """
    Defence in depth: if the model returned text instead of a tool call,
    try to recover JSON from it (strict, then json_repair).
    """
    text_blocks = [getattr(b, "text", "") for b in response.content
                   if getattr(b, "type", None) == "text"]
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
        logger.info("Recovered profile from text via json_repair")
        return json.loads(repair_json(raw))
    except Exception:
        return None


def extract_voice_profile(
    materials_blob: str,
    client: anthropic.Anthropic,
    model: str,
) -> dict[str, Any] | None:
    """
    Extract via forced tool use. The model must call record_voice_profile,
    so the result is a constrained, pre-parsed dict — no JSON string parsing.

    Retries only on transient API errors (with exponential backoff).
    Tool-use output essentially never fails to parse; a text fallback covers
    the pathological case where the model ignores the tool.
    """
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(materials=materials_blob)
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=EXTRACTION_SYSTEM,
                tools=[VOICE_PROFILE_TOOL],
                tool_choice={"type": "tool", "name": "record_voice_profile"},
                messages=[{"role": "user", "content": prompt}],
            )

            if response.stop_reason == "max_tokens":
                logger.warning("Hit max_tokens — tool input may be incomplete. "
                               "Profile will still be saved but check for gaps.")

            profile = _extract_tool_input(response)
            if profile is not None:
                return profile

            logger.warning("No tool_use block found; trying text fallback parse")
            profile = _text_fallback_parse(response)
            if profile is not None:
                return profile

            logger.warning(f"Attempt {attempt + 1}: model returned no usable output")

        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            last_err = exc
            wait = 2 ** attempt
            logger.error(f"API error attempt {attempt + 1}: {exc} — retrying in {wait}s")
            time.sleep(wait)
        except anthropic.APIError as exc:
            last_err = exc
            logger.error(f"API error attempt {attempt + 1}: {exc}")

    logger.error(f"All attempts failed. Last error: {last_err}")
    return None


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def render_voice_profile_md(profile: dict[str, Any]) -> str:
    lines = [
        "# Voice Profile",
        "*Extracted from Jackson's writing samples.*",
        "",
        "## Tone",
        "",
        profile.get("tone", "_not extracted_"),
        "",
        "## Sentence patterns",
        "",
    ]
    sp = profile.get("sentence_patterns", {})
    if isinstance(sp, dict):
        lines.append(f"**Length preference:** {sp.get('length_preference', '_n/a_')}")
        lines.append("")
        lines.append(f"**Structure:** {sp.get('structure', '_n/a_')}")
        lines.append("")
        lines.append(f"**Rhythm:** {sp.get('rhythm', '_n/a_')}")
        lines.append("")
        examples = sp.get("examples", [])
        if examples:
            lines.append("**Examples of typical sentences:**")
            for ex in examples:
                lines.append(f"- {ex}")
            lines.append("")

    lines += [
        "## Vocabulary signature",
        "",
        "Words and phrases this writer uses distinctively. Reach for these.",
        "",
    ]
    for item in profile.get("vocabulary_signature", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += [
        "## Stance patterns",
        "",
        profile.get("stance_patterns", "_not extracted_"),
        "",
        "## Content depth signals",
        "",
        "*Topics and areas where podcast material reveals deeper knowledge or "
        "stronger opinions than articles alone. Use these when the review subject "
        "touches these areas.*",
        "",
    ]
    for item in profile.get("content_depth_signals", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Opening patterns", ""]
    for item in profile.get("opening_patterns", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Closing patterns", ""]
    for item in profile.get("closing_patterns", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Transition patterns", ""]
    for item in profile.get("transition_patterns", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += [
        "## Specific tics",
        "",
        "*Quirks the writer probably doesn't notice but that mark the voice.*",
        "",
    ]
    for item in profile.get("specific_tics", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Topic stances", ""]
    topic_stances = profile.get("topic_stances", [])
    if isinstance(topic_stances, list):
        for item in topic_stances:
            if isinstance(item, dict):
                topic = item.get("topic", "")
                stance = item.get("stance", "")
                source = item.get("source", "")
                src_str = f"  _({source})_" if source else ""
                lines.append(f"**{topic}**: {stance}{src_str}")
            else:
                lines.append(f"- {item}")
            lines.append("")
    elif isinstance(topic_stances, dict):
        for topic, stance in topic_stances.items():
            lines.append(f"**{topic}**: {stance}")
            lines.append("")

    podcast_signals = profile.get("podcast_only_signals", [])
    if podcast_signals:
        lines += [
            "## Podcast-only signals",
            "",
            "*Valid content signal from podcasts with no corroborating article evidence. "
            "Treat as available depth but verify before treating as canonical voice.*",
            "",
        ]
        for item in podcast_signals:
            lines.append(f"- {item}")
        lines.append("")

    notes = profile.get("notes_for_assembler", "")
    if notes:
        lines += ["---", "", "## Notes from extraction", "", notes, ""]

    return "\n".join(lines)


def render_never_say_md(profile: dict[str, Any]) -> str:
    lines = [
        "# Never Say",
        "",
        "The following words, phrases, and patterns are off-voice for Coffee Bean Index. ",
        "When drafting, avoid these. If a draft contains them, rewrite the passage.",
        "",
        "## Off-voice phrases (specific to this writer's voice)",
        "",
        "*Inferred from absence in the corpus — these are things this writer doesn't say.*",
        "",
    ]
    for item in profile.get("never_say_list", []):
        lines.append(f"- {item}")
    lines.append("")

    lines += [
        "## AI clichés to suppress",
        "",
        "*Universal AI-isms that conflict with this voice. Suppress on sight.*",
        "",
    ]
    for item in profile.get("ai_isms_to_avoid", []):
        lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines)


def copy_exemplars(
    profile: dict[str, Any],
    materials: list[dict[str, Any]],
    out_dir: Path,
) -> list[str]:
    """Copy ranked article exemplars into the exemplars subfolder."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ranking = profile.get("format_exemplar_ranking", [])
    if not ranking:
        ranking = [m["filename"] for m in materials if m["source_type"] == "articles"]

    article_lookup = {
        m["filename"]: m for m in materials if m["source_type"] == "articles"
    }

    copied: list[str] = []
    for filename in ranking:
        material = article_lookup.get(filename)
        if not material:
            logger.warning(f"Ranking referenced unknown file: {filename}")
            continue
        src = Path(material["abs_path"])
        dst_md = (out_dir / src.name).with_suffix(".md")
        try:
            dst_md.write_text(material["content"], encoding="utf-8")
            copied.append(dst_md.name)
        except Exception as exc:
            logger.warning(f"Could not copy {src.name}: {exc}")

    return copied


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured voice profile from writing samples.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print full analytics and cost without calling the API")
    parser.add_argument("--verbose", action="store_true",
                        help="Show per-file token breakdown in analytics")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    voice_materials_dir = repo_root / "voice_materials"
    skill_data_dir = repo_root / "skill_data"
    voice_out_dir = skill_data_dir / "voice"
    exemplars_dir = voice_out_dir / "exemplars"

    if not voice_materials_dir.exists():
        print(f"Error: {voice_materials_dir} does not exist.", file=sys.stderr)
        print("Create voice_materials/articles/, voice_materials/podcasts/, "
              "voice_materials/reddit/ and drop your files in.", file=sys.stderr)
        sys.exit(1)

    logger.info(f"Loading materials from {voice_materials_dir} ...")
    materials, counts = load_materials(voice_materials_dir)

    if not materials:
        print("No materials loaded. Check that voice_materials/ has files in "
              "articles/, podcasts/, or reddit/.", file=sys.stderr)
        sys.exit(1)

    # Analytics + cost
    print_analytics(materials, counts, verbose=args.verbose or args.dry_run)
    input_tokens = estimate_tokens(build_materials_blob(materials))
    print_cost_and_time(input_tokens)

    # Hard stops
    if counts["articles"] == 0 and not args.dry_run:
        print("\n❌ Cannot proceed without articles. Add some and re-run.", file=sys.stderr)
        sys.exit(1)

    if input_tokens > MAX_INPUT_TOKENS:
        print(f"\n❌ Input is {input_tokens:,} tokens, exceeds limit of "
              f"{MAX_INPUT_TOKENS:,}. Trim some samples and re-run.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("\n(Dry run — no API calls made. Re-run without --dry-run to proceed.)")
        return

    # API key
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: CLAUDE_API_KEY / ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    logger.info(f"Calling {args.model} via tool-use extraction (60-180s)...")
    materials_blob = build_materials_blob(materials)
    profile = extract_voice_profile(materials_blob, client, args.model)

    if not profile:
        print("Extraction failed after retries. Check logs above.", file=sys.stderr)
        sys.exit(1)

    # Write outputs
    voice_out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = voice_out_dir / "extraction_raw.json"
    raw_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote raw extraction: {raw_path}")

    profile_md = render_voice_profile_md(profile)
    profile_path = voice_out_dir / "voice_profile.md"
    profile_path.write_text(profile_md, encoding="utf-8")
    logger.info(f"Wrote voice profile: {profile_path}")

    never_say_md = render_never_say_md(profile)
    never_say_path = voice_out_dir / "never_say.md"
    never_say_path.write_text(never_say_md, encoding="utf-8")
    logger.info(f"Wrote never-say list: {never_say_path}")

    copied = copy_exemplars(profile, materials, exemplars_dir)
    logger.info(f"Copied {len(copied)} format exemplars to {exemplars_dir}")

    # Quick coverage summary so you can eyeball completeness
    print("\n✅ Voice profile extracted.")
    print(f"   {profile_path}")
    print(f"   {never_say_path}")
    print(f"   {exemplars_dir}/  ({len(copied)} exemplars)")
    print(f"   {raw_path}  (raw JSON for inspection)")
    print("\n=== Extraction coverage ===")
    print(f"   Vocabulary items:   {len(profile.get('vocabulary_signature', []))}")
    print(f"   Topic stances:      {len(profile.get('topic_stances', []))}")
    print(f"   Specific tics:      {len(profile.get('specific_tics', []))}")
    print(f"   Never-say items:    {len(profile.get('never_say_list', []))}")
    print(f"   AI-isms flagged:    {len(profile.get('ai_isms_to_avoid', []))}")
    print(f"   Content-depth sigs: {len(profile.get('content_depth_signals', []))}")
    print(f"   Podcast-only sigs:  {len(profile.get('podcast_only_signals', []))}")
    print("\nRead voice_profile.md — check the 'podcast_only_signals' section.")
    print("Those are valid depth signals but not yet confirmed against the written register.")
    print("Edit voice_materials/ and re-run if anything looks wrong before assembly.")


if __name__ == "__main__":
    main()
