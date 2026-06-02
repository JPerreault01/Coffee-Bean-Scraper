#!/usr/bin/env python3
"""
repurpose.py — Repurpose a finished review into derivative formats using the ECC
content-engine skill.

Supported formats: email (Beehiiv price-drop alert), social (Twitter/X post).

Fetches the ECC content-engine SKILL.md at runtime and caches it locally.
Falls back to a built-in prompt if the fetch fails.
"""

import argparse
import logging
import os
import sys
import urllib.request
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

ECC_SKILL_URL = (
    "https://raw.githubusercontent.com/affaan-m/ECC/main/skills/content-engine/SKILL.md"
)
SKILL_CACHE_PATH = (
    Path(__file__).parent.parent / ".cache" / "ecc_content_engine_skill.md"
)

FALLBACK_SKILL = """\
You are a content repurposing specialist. Your job is to take source content and
transform it into optimized derivative formats.

For each format, extract the core value and reshape it for that medium's constraints
and audience expectations. Apply these principles:
- Preserve the core insight from the source material exactly.
- Optimize for each format's specific constraints and conventions.
- Maintain the source's voice and factual accuracy throughout.
- No invented claims — use only what is present in the source content.
- CTAs must be specific and actionable, not vague.

Output only the requested format content. No preamble, no explanation."""


def load_skill(url: str, cache_path: Path) -> str:
    """
    Fetch ECC skill instructions from GitHub, caching locally.

    Returns the cached or freshly fetched content. Falls back to FALLBACK_SKILL
    if the network request fails.
    """
    if cache_path.exists():
        logger.info(f"Using cached skill from {cache_path}")
        return cache_path.read_text()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            content = resp.read().decode()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(content)
        logger.info(f"Fetched and cached skill to {cache_path}")
        return content
    except Exception as exc:
        logger.warning(f"Could not fetch skill from {url}: {exc}. Using built-in fallback.")
        return FALLBACK_SKILL


def generate_email(
    client: anthropic.Anthropic,
    skill_content: str,
    review_text: str,
) -> str:
    """
    Generate a Beehiiv price-drop email alert from the review.

    Output includes a Subject line, 3–5 sentence body, and CTA with [LINK] placeholder.
    """
    system = (
        f"{skill_content}\n\n"
        "---\n\n"
        "You are producing an EMAIL newsletter teaser for a coffee price-drop alert "
        "(delivered via Beehiiv).\n\n"
        "Hard requirements:\n"
        "- First line must be the subject line, formatted as: Subject: [subject here]\n"
        "- Body: 3–5 sentences. Informative tone, not promotional.\n"
        "- End with a clear CTA that includes the placeholder affiliate link [LINK].\n"
        "- Base every claim on the review content — no invented data.\n"
        "- No hashtags. No emojis unless they appear in the source review."
    )
    user = (
        "Based on the following coffee review, write a price-drop email alert.\n\n"
        f"{review_text}\n\n"
        "Output format:\n"
        "Subject: [subject line here]\n\n"
        "[3–5 sentence email body]\n\n"
        "[CTA sentence with [LINK] placeholder]"
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def generate_social(
    client: anthropic.Anthropic,
    skill_content: str,
    review_text: str,
) -> str:
    """
    Generate a Twitter/X post from the review.

    Output is under 280 characters, leads with the verdict, includes price if available.
    """
    system = (
        f"{skill_content}\n\n"
        "---\n\n"
        "You are producing a TWITTER/X post based on a coffee review.\n\n"
        "Hard requirements:\n"
        "- Total output must be under 280 characters.\n"
        "- Lead with the one-line verdict from the review.\n"
        "- Include price information if the review contains it.\n"
        "- No hashtags unless they appear naturally in the content.\n"
        "- Direct and factual — not promotional."
    )
    user = (
        "Based on the following coffee review, write a Twitter/X post under 280 characters.\n\n"
        f"{review_text}\n\n"
        "Output only the tweet text, nothing else."
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def main() -> None:
    """Parse arguments and repurpose the review into requested formats."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    parser = argparse.ArgumentParser(
        description="Repurpose a finished review into derivative formats using the ECC content-engine skill."
    )
    parser.add_argument(
        "--review",
        required=True,
        metavar="PATH",
        help="Path to the finished review draft (Markdown)",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["email", "social", "all"],
        default=["all"],
        metavar="FORMAT",
        help="Formats to generate: email, social, all (default: all)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print(
            "Error: CLAUDE_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    review_path = Path(args.review)
    if not review_path.exists():
        print(f"Error: Review file not found: {review_path}", file=sys.stderr)
        sys.exit(1)
    review_text = review_path.read_text()

    formats: set[str] = set(args.formats)
    if "all" in formats:
        formats = {"email", "social"}

    skill_content = load_skill(ECC_SKILL_URL, SKILL_CACHE_PATH)

    drafts_dir = review_path.parent
    drafts_dir.mkdir(parents=True, exist_ok=True)
    stem = review_path.stem

    client = anthropic.Anthropic(api_key=api_key)

    if "email" in formats:
        email_text = generate_email(client, skill_content, review_text)
        email_path = drafts_dir / f"{stem}-email.md"
        email_path.write_text(email_text + "\n")
        print(str(email_path))

    if "social" in formats:
        social_text = generate_social(client, skill_content, review_text)
        social_path = drafts_dir / f"{stem}-social.txt"
        social_path.write_text(social_text + "\n")
        print(str(social_path))


if __name__ == "__main__":
    main()
