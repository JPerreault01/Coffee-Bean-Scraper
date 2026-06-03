#!/usr/bin/env python3
"""
build_voice_profile.py — Extract a structured voice profile from Jackson's own
writing samples. Tier 1 of the skill-writer pipeline.

The output gets used by assemble_skill.py to build the final skill folder.

Usage:
  python data_pipeline/build_voice_profile.py
  python data_pipeline/build_voice_profile.py --dry-run    # estimate cost, don't call API
  python data_pipeline/build_voice_profile.py --model claude-sonnet-4-6

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

Why the distinction still matters:
  Even strong podcast content can bleed in spoken-register structures if the
  extractor treats it as a format exemplar. The rule is: use podcasts for
  WHAT is said and HOW positions are built — not for sentence structure or
  paragraph shape. That's what the articles are for.

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
import shutil
import sys
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
MAX_INPUT_TOKENS = 150_000  # leave headroom in Sonnet's 200k context
TOO_LARGE_THRESHOLD = int(MAX_INPUT_TOKENS * CHARS_PER_TOKEN)

SONNET_INPUT_PRICE_PER_M = 3.00
SONNET_OUTPUT_PRICE_PER_M = 15.00

SUPPORTED_EXTS = {".md", ".txt", ".json"}

# ---------------------------------------------------------------------------
# Voice extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = (
    "You are a voice profiler extracting the authentic written voice of a coffee "
    "writer. You read their actual writing and produce a structured profile that "
    "another AI will use to write in their voice. You are precise, concrete, and "
    "never invent patterns that aren't in the samples. You return only valid JSON. "
    "Be exhaustive — this profile is built once and used to generate hundreds of "
    "reviews. More specific evidence produces better output. Do not summarise when "
    "you can quote. Do not generalise when you can be specific."
)

EXTRACTION_PROMPT_TEMPLATE = """You are extracting a voice profile from a coffee writer's own materials. The output will be saved as a skill that lets an AI write coffee reviews in this person's voice.

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
    Casual register. Use only for:
      - Informal vocabulary and slang
      - Off-the-cuff opinions (treat as supporting evidence, not primary signal)
      - Verbal tics that also appear elsewhere
    Do not treat structure or phrasing from Reddit as a target.

WEIGHTING RULE: When the same opinion or stance appears in both an article and
a podcast, treat the article phrasing as canonical. When a topic appears in
podcasts but not articles, it is still valid content signal — note it but flag
that it's podcast-only so the assembler can decide whether to trust it.

--- MATERIALS ---
{materials}
--- END MATERIALS ---

Extract a thorough, exhaustive voice profile. Be specific and concrete at every
point. Pull actual examples from the materials and cite the source filename in
parentheses. Do not generalise. Do not invent. If a section has insufficient
evidence, say so explicitly rather than filling with assumptions.

For vocabulary and tics especially: aim for the maximum count. It is better to
include 25 vocabulary items with citations than 10 vague ones. This profile is
used to generate hundreds of reviews — every specific data point improves output.

Return ONLY this JSON object, no preamble or backticks:

{{
  "tone": "3-4 sentences on the overall tone, with at least two specific example phrases quoted from samples (cite source file for each)",
  "sentence_patterns": {{
    "length_preference": "describe — short/medium/long/varied — with evidence from articles specifically",
    "structure": "describe how sentences are typically built (e.g., 'subject-verb-object with frequent appositives'); cite article examples",
    "rhythm": "describe pacing and rhythm patterns; note if podcast material corroborates or adds nuance",
    "examples": ["5 actual sentences from articles that exemplify the typical sentence style (cite source for each)"]
  }},
  "vocabulary_signature": [
    "specific words or phrases this writer uses distinctively, with the source where each appeared and a note on whether it appears in articles, podcasts, or both. Aim for 20-35 items. Prioritise items that appear across multiple source types."
  ],
  "stance_patterns": "3-4 sentences on how this writer takes positions (assertive? hedged? qualified? When does each happen?). Note any differences between the written and spoken register.",
  "content_depth_signals": [
    "topics, products, or technical areas where the podcast material shows deeper knowledge or stronger opinions than the articles alone would reveal. 5-10 items, each with a brief description and source citation. These are content areas the skill should treat as available depth."
  ],
  "opening_patterns": [
    "4-6 patterns the writer uses to open articles or posts, each with a direct example from the source. Prefer article examples; note if a pattern also appears in podcasts."
  ],
  "closing_patterns": [
    "4-6 patterns the writer uses to close articles or posts, each with a direct example. Prefer article examples."
  ],
  "transition_patterns": [
    "4-6 ways the writer moves between ideas, each with a direct example. Prefer article examples."
  ],
  "specific_tics": [
    "verbal or textual quirks that mark this writer's voice — things they probably do without noticing. Include punctuation habits, capitalization habits, repeated structural moves, filler phrases. Note the source type for each. 8-15 items."
  ],
  "never_say_list": [
    "words, phrases, or rhetorical moves that this writer does NOT use — patterns that would feel off-voice if inserted. Infer this from absence across all source types. 8-15 items."
  ],
  "ai_isms_to_avoid": [
    "common AI clichés that conflict with this writer's voice (e.g., 'delve into', 'it's worth noting', 'in the world of coffee', em-dashes used as filler). 12-20 items."
  ],
  "topic_stances": {{
    "topic_name": "the writer's specific position or opinion on this coffee-related topic, with source citation and whether the signal comes from article, podcast, or both. Include any topic where the writer has expressed a clear view."
  }},
  "podcast_only_signals": [
    "knowledge areas, opinions, or stances that appear in podcast material but NOT in articles. Flag these separately so the assembler knows they are valid content signals but unverified against the written register. 0-10 items, or empty list if none."
  ],
  "format_exemplar_ranking": [
    "filenames of the articles that BEST exemplify the target written voice — rank from strongest to weakest. Only include files from ===ARTICLE=== sources. 3-7 items."
  ],
  "notes_for_assembler": "2-3 sentences flagging anything the human should know about this voice extraction — gaps in evidence, surprising patterns, conflicts between source types, or areas where more material would improve accuracy."
}}"""


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
        # Try to flatten JSON into readable text
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
        # Prefer "body", "text", "selftext", "title", "content" fields
        for key in ("title", "selftext", "body", "text", "content", "transcript"):
            if key in obj and obj[key]:
                return _flatten_json(obj[key], depth + 1)
        # Fallback: dump all string values
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
    """
    Walk voice_materials/, return list of materials with metadata.
    Each item: {filename, source_type, content, char_count}
    """
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
# Extraction
# ---------------------------------------------------------------------------


def extract_voice_profile(
    materials_blob: str,
    client: anthropic.Anthropic,
    model: str,
) -> dict[str, Any] | None:
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(materials=materials_blob)

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=EXTRACTION_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip().rstrip("`").strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(f"JSON parse failed attempt {attempt+1}: {exc}")
            if attempt == 2:
                logger.error("Final parse attempt failed; saving raw response for inspection")
                return {"_raw": raw, "_parse_error": str(exc)}
        except anthropic.APIError as exc:
            logger.error(f"API error attempt {attempt+1}: {exc}")
            if attempt == 2:
                return None
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
    topic_stances = profile.get("topic_stances", {})
    if isinstance(topic_stances, dict):
        for topic, stance in topic_stances.items():
            lines.append(f"**{topic}**: {stance}")
            lines.append("")
    elif isinstance(topic_stances, list):
        for item in topic_stances:
            lines.append(f"- {item}")
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
        lines += [
            "---",
            "",
            "## Notes from extraction",
            "",
            notes,
            "",
        ]

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
        # Fallback: use all articles
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
        dst = out_dir / src.name
        # Write as .md so it's readable as text content
        dst_md = dst.with_suffix(".md")
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
                        help="Print stats and estimated cost without calling the API")
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

    # Load materials
    logger.info(f"Loading materials from {voice_materials_dir} ...")
    materials, counts = load_materials(voice_materials_dir)

    if not materials:
        print("No materials loaded. Check that voice_materials/ has files in "
              "articles/, podcasts/, or reddit/.", file=sys.stderr)
        sys.exit(1)

    total_chars = sum(m["char_count"] for m in materials)
    est_tokens = estimate_tokens(build_materials_blob(materials))

    print("\n=== Voice materials loaded ===")
    print(f"  Articles:  {counts['articles']}  (format + voice — highest weight)")
    print(f"  Podcasts:  {counts['podcasts']}  (content + opinions — medium-high weight)")
    print(f"  Reddit:    {counts['reddit']}  (voice signal only — lowest weight)")
    print(f"  Total files: {len(materials)}")
    print(f"  Total chars: {total_chars:,}")
    print(f"  Estimated input tokens: {est_tokens:,}")

    # Sanity checks
    if counts["articles"] == 0:
        print("\n⚠️  WARNING: No articles found. The voice profile needs articles "
              "as format exemplars. Add at least 3-5 of your written articles "
              "to voice_materials/articles/ before proceeding.", file=sys.stderr)
        if not args.dry_run:
            sys.exit(1)

    if counts["articles"] < 3:
        print(f"\n⚠️  WARNING: Only {counts['articles']} article(s). Voice DNA "
              f"stabilizes with 5-15 articles. Add more if available.",
              file=sys.stderr)

    if est_tokens > MAX_INPUT_TOKENS:
        print(f"\n❌ Input is {est_tokens:,} tokens, exceeds limit of "
              f"{MAX_INPUT_TOKENS:,}. Trim some samples and re-run.",
              file=sys.stderr)
        sys.exit(1)

    # Cost estimate — output budget raised to 8000 for exhaustive extraction
    output_tokens_est = 13000
    input_cost = est_tokens / 1_000_000 * SONNET_INPUT_PRICE_PER_M
    output_cost = output_tokens_est / 1_000_000 * SONNET_OUTPUT_PRICE_PER_M
    total_cost = input_cost + output_cost

    print(f"\n=== Cost estimate ===")
    print(f"  Input cost:  ${input_cost:.3f}")
    print(f"  Output cost: ${output_cost:.3f}  (16k token budget for exhaustive extraction)")
    print(f"  Total:       ${total_cost:.3f}")

    if args.dry_run:
        print("\n(Dry run — no API calls made. Re-run without --dry-run to proceed.)")
        return

    # API call
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: CLAUDE_API_KEY / ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    logger.info(f"Calling {args.model} for voice extraction (this takes 60-120s with extended output)...")
    materials_blob = build_materials_blob(materials)
    profile = extract_voice_profile(materials_blob, client, args.model)

    if not profile:
        print("Extraction failed. Check logs.", file=sys.stderr)
        sys.exit(1)

    # Write outputs
    voice_out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = voice_out_dir / "extraction_raw.json"
    raw_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    logger.info(f"Wrote raw extraction: {raw_path}")

    if "_parse_error" in profile:
        print(f"\n❌ Parse error during extraction: {profile['_parse_error']}",
              file=sys.stderr)
        print(f"Raw response saved to {raw_path} — inspect and re-run.",
              file=sys.stderr)
        sys.exit(1)

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

    print("\n✅ Voice profile extracted.")
    print(f"   {profile_path}")
    print(f"   {never_say_path}")
    print(f"   {exemplars_dir}/  ({len(copied)} exemplars)")
    print(f"   {raw_path}  (raw JSON for inspection)")
    print("\nRead voice_profile.md — pay attention to 'podcast_only_signals' section.")
    print("Those are valid depth signals but not yet confirmed against written register.")
    print("Edit voice_materials/ and re-run if anything looks wrong before assembly.")


if __name__ == "__main__":
    main()
