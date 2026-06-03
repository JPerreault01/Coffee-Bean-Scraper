#!/usr/bin/env python3
"""
assemble_skill.py — Combine Tier 1 (voice) and Tier 2 (knowledge) outputs into
a complete, installable Claude skill folder following the Agent Skills standard.

This is the script that answers "how do Tier 1 and Tier 2 synthesize" — they
become parallel subfolders inside a single skill, with a SKILL.md that tells
Claude how to navigate them.

Usage:
  python data_pipeline/assemble_skill.py
  python data_pipeline/assemble_skill.py --output-dir skills/coffee-review-writer
  python data_pipeline/assemble_skill.py --overwrite     # wipe & rebuild

Inputs (must exist):
  skill_data/voice/voice_profile.md
  skill_data/voice/never_say.md
  skill_data/voice/exemplars/*.md
  skill_data/skill_knowledge.json     (from build_skill_knowledge.py)

Output:
  skills/coffee-review-writer/
  ├── SKILL.md
  ├── voice/
  │   ├── voice_profile.md
  │   ├── never_say.md
  │   └── exemplars/
  ├── knowledge/
  │   ├── consensus_claims.md
  │   ├── contested_claims.md
  │   ├── vocabulary.md
  │   ├── tasting_descriptors.md
  │   ├── community_framing.md
  │   └── insights_by_category.md
  └── gotchas.md
"""

import argparse
import json
import logging
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

SKILL_NAME = "coffee-review-writer"

# ---------------------------------------------------------------------------
# SKILL.md content
# ---------------------------------------------------------------------------

# YAML description — 1024 char hard limit per Agent Skills spec.
# Written to be specific and slightly pushy per Anthropic skill-creator guidance:
# Claude under-triggers skills by default, so descriptions need explicit signals.
SKILL_DESCRIPTION = (
    "Use this skill whenever the user asks Claude to write, draft, edit, or improve "
    "any piece of writing for Coffee Bean Index (coffeebeanindex.com) — including "
    "individual bean reviews, espresso/dark-roast/pour-over roundups, origin guides, "
    "brew-method explainers, comparison articles, and tasting-note blocks. Triggers "
    "include phrases like 'write a review', 'draft a review for [bean]', 'review "
    "this', 'make a roundup', 'origin guide', 'write something on [coffee topic]', "
    "and any direct request to produce coffee content. This skill encodes the "
    "writer's authentic voice (extracted from their own articles, podcast transcripts, "
    "and forum posts), the Coffee Bean Index review format, and community-validated "
    "knowledge from 50+ curated coffee sources. USE this skill even when the user "
    "just says 'write something for [bean name]' without explicit instructions — "
    "generic AI coffee writing will not match the site's voice or editorial standards."
)


def render_skill_md(
    knowledge_meta: dict[str, Any],
    exemplar_filenames: list[str],
) -> str:
    """Build the SKILL.md body with frontmatter and instructions."""
    sources_count = knowledge_meta.get("total_sources", 0)
    categories = knowledge_meta.get("categories", [])
    categories_str = ", ".join(sorted(categories)) if categories else "n/a"

    # Format exemplar list as a markdown reference list
    exemplar_lines = "\n".join(
        f"- `voice/exemplars/{name}`" for name in exemplar_filenames
    ) or "- (none yet — add articles to voice_materials/articles/ and re-run the pipeline)"

    body = f"""---
name: {SKILL_NAME}
description: {SKILL_DESCRIPTION}
---

# Coffee Review Writer

This skill writes coffee content for **Coffee Bean Index** in the site's authentic
voice. It is the only voice that ships on the site — never publish generic AI
output unmodified.

## When to use this skill

Use it whenever the user wants to produce a piece of writing for the site:

- Bean reviews (the most common case)
- Roundup posts ("Best Espresso Beans Under $20", etc.)
- Origin guides (Ethiopia, Colombia, etc.)
- Brew-method explainers (French press, pour-over)
- Comparison articles ("X vs Y")
- Standalone tasting-note blocks for an existing page

Do not use this skill for code, technical support, or non-writing tasks.

## Load order — read these before drafting

Always perform these steps before you write the first sentence:

1. **Read `voice/voice_profile.md`** — this is the voice you are producing.
   Pay particular attention to sentence patterns, stance, and specific tics.

2. **Read `voice/never_say.md`** — these are off-voice phrases and AI clichés.
   If your draft contains anything from this list, rewrite the passage.

3. **Read at least one `voice/exemplars/*.md`** — pick the one closest to the
   format the user is asking for (review, roundup, guide). The exemplar is
   the structural template.

4. **Consult `knowledge/` files as relevant to the topic** — see "Knowledge
   files" below. Don't read all of them; read the ones that match the topic.

5. **Read `gotchas.md`** — common mistakes specific to this site's content.

## Knowledge files

The `knowledge/` folder is digested from {sources_count} curated coffee sources
across categories ({categories_str}). Read the file relevant to your task:

- `knowledge/consensus_claims.md` — what the coffee community agrees on. State
  these confidently in the review. Do not hedge what is settled.
- `knowledge/contested_claims.md` — where the community disagrees. These are
  the places your voice should take a stance — pick a side, do not summarize
  the debate.
- `knowledge/vocabulary.md` — technical terms with how the community uses them.
  Reach for these instead of inventing your own phrasing.
- `knowledge/tasting_descriptors.md` — the full sensory vocabulary present in
  the corpus. Use these descriptors; do not invent new ones.
- `knowledge/community_framing.md` — how different communities prioritize
  coffee decisions. Useful when targeting a specific audience.
- `knowledge/insights_by_category.md` — concrete insights by topic. Skim the
  section that matches the topic before drafting.

## The Coffee Bean Index review format

Every individual bean review follows this exact structure (an exemplar is in
`voice/exemplars/`):

```
## [Product Name] Review

**One-line verdict**: [Direct, specific, no hedge words]

| Spec | Detail |
|---|---|
| Roast | |
| Origin | |
| Process | |
| Best for | [brew methods] |
| Price/oz | $X.XX |

### Tasting notes
- [Specific note]
- [3-5 bullets total, no vague descriptors without context]

### Who it's for
[1-2 sentences. Specific.]

### Who should skip it
[1-2 sentences. Honest.]

### Price analysis
[Current price vs 30-day average, value judgment, when to buy]

### Rating: X/10
[One sentence explaining the score]
```

## Process

When the user asks for a review:

1. Confirm you have the product specs. If not, ask: roaster, roast level,
   origin, process method, weight, current price, and sensory ratings if
   available (acidity/body/sweetness/bitterness on a 1–5 scale).
2. Read the voice files (voice_profile.md, never_say.md, one exemplar).
3. Read relevant knowledge files for the bean's roast level and origin.
4. Draft the review section by section, following the format above.
5. Self-check against never_say.md and gotchas.md before delivering.
6. Output the draft as markdown ready to paste into WordPress.

When the user asks for a roundup, origin guide, or other format, the rules are
the same: read voice files first, read relevant knowledge, then draft. The
exact format will differ — use the user's request to determine structure, but
keep voice consistent.

## Available exemplars

These are real on-voice articles from the site. Use them as structural and
tonal templates:

{exemplar_lines}

## Self-check before delivering

Before returning a draft, verify:

- Does the opening match the writer's opening patterns (see voice_profile.md)?
- Does every paragraph contain at least one specific, concrete claim?
- Are tasting descriptors pulled from `knowledge/tasting_descriptors.md` rather
  than invented?
- Is the verdict opinionated, not a hedged summary?
- Have you stripped all AI-isms from `voice/never_say.md`?
- Have you avoided the gotchas in `gotchas.md`?

If any check fails, rewrite the affected section. Do not deliver a draft that
fails self-check.
"""
    return body


# ---------------------------------------------------------------------------
# Knowledge splitting
# ---------------------------------------------------------------------------


def split_knowledge_to_files(knowledge: dict[str, Any], out_dir: Path) -> None:
    """Split the compiled skill_knowledge.json into per-section MD files."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # ----- consensus_claims.md -----
    lines = [
        "# Consensus Claims",
        "",
        "*What the curated coffee community agrees on. State these with confidence in the review — do not hedge what is settled.*",
        "",
    ]
    by_cat: dict[str, list[str]] = defaultdict(list)
    for item in knowledge.get("consensus_claims", []):
        by_cat[item["category"]].append(
            f"- {item['claim']} *(via {item['source']})*"
        )
    for cat, claims in sorted(by_cat.items()):
        lines.append(f"## {cat.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(claims)
        lines.append("")
    (out_dir / "consensus_claims.md").write_text("\n".join(lines), encoding="utf-8")

    # ----- contested_claims.md -----
    lines = [
        "# Contested Claims",
        "",
        "*Where the curated community disagrees or qualifies. These are the places your voice should take a stance — pick a side, do not summarize the debate.*",
        "",
    ]
    by_cat = defaultdict(list)
    for item in knowledge.get("contested_claims", []):
        by_cat[item["category"]].append(
            f"- {item['claim']} *(via {item['source']})*"
        )
    for cat, claims in sorted(by_cat.items()):
        lines.append(f"## {cat.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(claims)
        lines.append("")
    (out_dir / "contested_claims.md").write_text("\n".join(lines), encoding="utf-8")

    # ----- vocabulary.md -----
    lines = [
        "# Technical Vocabulary",
        "",
        "*Coffee terms as the community uses them. Reach for these instead of inventing phrasing.*",
        "",
    ]
    vocab = knowledge.get("vocabulary", {})
    for term in sorted(vocab.keys()):
        usage = vocab[term]
        if isinstance(usage, list):
            lines.append(f"**{term}**")
            for u in usage:
                lines.append(f"  - {u}")
            lines.append("")
        else:
            lines.append(f"**{term}**: {usage}")
            lines.append("")
    (out_dir / "vocabulary.md").write_text("\n".join(lines), encoding="utf-8")

    # ----- tasting_descriptors.md -----
    lines = [
        "# Tasting Descriptors",
        "",
        "*The full sensory vocabulary in the corpus. Use these descriptors. Do not invent new ones — every descriptor below has appeared in at least one trusted source.*",
        "",
    ]
    descriptors = knowledge.get("tasting_descriptors", [])
    if descriptors:
        lines.append(", ".join(descriptors))
        lines.append("")
    else:
        lines.append("_(empty — re-run build_skill_knowledge.py)_")
    (out_dir / "tasting_descriptors.md").write_text("\n".join(lines), encoding="utf-8")

    # ----- community_framing.md -----
    lines = [
        "# Community Framing",
        "",
        "*How each source community prioritizes coffee decisions. Useful when targeting a specific audience.*",
        "",
    ]
    for item in knowledge.get("community_framing", []):
        lines.append(f"**{item['source']}**")
        lines.append("")
        lines.append(item["framing"])
        lines.append("")
    (out_dir / "community_framing.md").write_text("\n".join(lines), encoding="utf-8")

    # ----- insights_by_category.md -----
    lines = [
        "# Key Insights by Category",
        "",
        "*Concrete insights from the corpus that improve a review. Skim the section matching the topic before drafting.*",
        "",
    ]
    by_cat = defaultdict(list)
    for item in knowledge.get("key_insights", []):
        by_cat[item["category"]].append(
            f"- {item['insight']} *(via {item['source']})*"
        )
    for cat, insights in sorted(by_cat.items()):
        lines.append(f"## {cat.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(insights)
        lines.append("")
    (out_dir / "insights_by_category.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Gotchas — generated starter, user iterates
# ---------------------------------------------------------------------------


GOTCHAS_STARTER = """# Gotchas

*Common mistakes when writing for Coffee Bean Index. Update this file iteratively as you spot the skill making errors.*

## Voice mistakes

- **Generic openers.** Do not start a review with "Looking for a great espresso?" or "Coffee lovers, rejoice!" These are the AI-blog openers — they are not on voice. Use the patterns in `voice/voice_profile.md` instead.
- **Hedge-summary verdicts.** The one-line verdict must be a stance, not a summary. "A medium-roast Brazilian blend with chocolate notes" is a description, not a verdict. "Forgiving espresso for under-extraction, but no character" is a verdict.
- **Fake personal experience.** Do not claim "I drank this every morning" or "I pulled fifty shots" unless the user explicitly enables personal mode. Default voice describes the coffee, not Jackson's mornings.
- **Reddit register leakage.** Voice signal from Reddit/podcasts (vocabulary, opinions, tics) is fine. Reddit *structure* (run-on sentences, "tbh", "imo", lowercase opens) is not. The exemplars in `voice/exemplars/` are the structural target — match those.

## Format mistakes

- **Missing rating.** Every individual bean review ends with "Rating: X/10" plus a one-sentence explanation. Never omit.
- **Vague tasting notes.** "Smooth and chocolatey" is not a tasting note — it's two words with no context. "Dark chocolate bitterness that fades clean, not lingering" is a tasting note. Always pair the descriptor with a behavior or context.
- **No "Who should skip it" section.** Every review must have this. It is what differentiates the site from press-release content. Be honest.
- **Marketing language in the price analysis.** "Premium quality at an everyday price" is marketing copy. "Twenty percent above the category average; worth it if you want a forgiving espresso blend" is analysis.

## Knowledge mistakes

- **Invented specifics.** Do not make up percentages, prices, production volumes, elevation, or sensory ratings. If a number is not in the product specs you were given, leave it out.
- **Stating a contested claim as settled.** Check `knowledge/contested_claims.md`. If a claim appears there, treat it as a place to take a stance, not as fact. Do not present it neutrally.
- **Importing descriptors not in the corpus.** Only use tasting descriptors that appear in `knowledge/tasting_descriptors.md`. If a perfect descriptor exists outside the corpus, add it to the file rather than slipping it in.

## Process mistakes

- **Skipping the voice files.** Even on review #50, re-read `voice/voice_profile.md` and at least one exemplar before drafting. Voice drift happens silently.
- **Skipping self-check.** Always run the self-check listed in SKILL.md before delivering. The check catches more issues than the draft step does.
"""


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def assemble(
    skill_data_dir: Path,
    output_dir: Path,
    overwrite: bool,
) -> None:
    """Build the final skill folder from skill_data/ outputs."""
    knowledge_path = skill_data_dir / "skill_knowledge.json"
    voice_dir = skill_data_dir / "voice"

    if not knowledge_path.exists():
        print(f"Error: {knowledge_path} not found.\n"
              "Run `python data_pipeline/build_skill_knowledge.py` first.",
              file=sys.stderr)
        sys.exit(1)

    if not voice_dir.exists():
        print(f"Error: {voice_dir} not found.\n"
              "Run `python data_pipeline/build_voice_profile.py` first.",
              file=sys.stderr)
        sys.exit(1)

    # Read inputs
    with open(knowledge_path, encoding="utf-8") as f:
        knowledge = json.load(f)

    # Handle output directory
    if output_dir.exists():
        if not overwrite:
            print(f"Error: {output_dir} already exists. Use --overwrite to replace it.",
                  file=sys.stderr)
            sys.exit(1)
        shutil.rmtree(output_dir)
        logger.info(f"Removed existing {output_dir}")

    output_dir.mkdir(parents=True)

    # Voice subfolder — copy from skill_data/voice
    voice_out = output_dir / "voice"
    voice_out.mkdir()
    for fname in ("voice_profile.md", "never_say.md"):
        src = voice_dir / fname
        if src.exists():
            shutil.copy(src, voice_out / fname)
            logger.info(f"Copied {fname}")
        else:
            logger.warning(f"Voice file missing: {fname}")

    # Exemplars
    exemplars_src = voice_dir / "exemplars"
    exemplars_dst = voice_out / "exemplars"
    exemplar_filenames: list[str] = []
    if exemplars_src.exists():
        exemplars_dst.mkdir()
        for ex in sorted(exemplars_src.glob("*.md")):
            shutil.copy(ex, exemplars_dst / ex.name)
            exemplar_filenames.append(ex.name)
        logger.info(f"Copied {len(exemplar_filenames)} exemplars")
    else:
        logger.warning("No exemplars/ folder in skill_data/voice — skill will work "
                       "but won't have format templates")

    # Knowledge subfolder — split JSON into per-section MD files
    knowledge_out = output_dir / "knowledge"
    split_knowledge_to_files(knowledge, knowledge_out)
    logger.info(f"Wrote {len(list(knowledge_out.glob('*.md')))} knowledge files")

    # Gotchas
    gotchas_path = output_dir / "gotchas.md"
    gotchas_path.write_text(GOTCHAS_STARTER, encoding="utf-8")
    logger.info("Wrote gotchas.md (starter — iterate on this as you find issues)")

    # SKILL.md — the entry point
    skill_md = render_skill_md(
        knowledge_meta=knowledge.get("meta", {}),
        exemplar_filenames=exemplar_filenames,
    )
    (output_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    logger.info("Wrote SKILL.md")

    # Validate frontmatter description length
    desc_len = len(SKILL_DESCRIPTION)
    if desc_len > 1024:
        logger.warning(f"SKILL.md description is {desc_len} chars — exceeds 1024 limit. "
                       "Some installations may truncate.")

    # Summary
    print("\n✅ Skill assembled.")
    print(f"   {output_dir}/")
    print(f"   ├── SKILL.md")
    print(f"   ├── voice/")
    print(f"   │   ├── voice_profile.md")
    print(f"   │   ├── never_say.md")
    print(f"   │   └── exemplars/  ({len(exemplar_filenames)} files)")
    print(f"   ├── knowledge/  ({len(list(knowledge_out.glob('*.md')))} files)")
    print(f"   └── gotchas.md")
    print()
    print("Next steps:")
    print(f"  1. Read {output_dir}/SKILL.md and verify the description triggers correctly")
    print(f"  2. Read {output_dir}/voice/voice_profile.md and confirm it matches your voice")
    print(f"  3. Install the skill in Claude (claude.ai → Settings → Capabilities → Skills → Upload)")
    print(f"     OR upload via the API skill management endpoints")
    print(f"  4. Test by asking Claude to write a review of any bean in products.json")
    print(f"  5. If output is off, edit voice_materials/ or curated sources and re-run")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble Tier 1 + Tier 2 outputs into a final installable skill folder."
    )
    parser.add_argument("--output-dir", default=None,
                        help="Output directory for the skill (default: skills/coffee-review-writer)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Wipe and rebuild the output directory if it exists")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    skill_data_dir = repo_root / "skill_data"

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = repo_root / "skills" / SKILL_NAME

    assemble(skill_data_dir, output_dir, args.overwrite)


if __name__ == "__main__":
    main()
