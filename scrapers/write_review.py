#!/usr/bin/env python3
"""
write_review.py — Generate a full coffee bean review using the ECC article-writing skill.

Fetches the ECC article-writing SKILL.md at runtime and uses it as the system prompt
(cached locally in .cache/). Falls back to a built-in prompt if the fetch fails.
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

ECC_SKILL_URL = (
    "https://raw.githubusercontent.com/affaan-m/ECC/main/skills/article-writing/SKILL.md"
)
SKILL_CACHE_PATH = (
    Path(__file__).parent.parent / ".cache" / "ecc_article_writing_skill.md"
)

REVIEW_FORMAT = """\
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
- [3–5 bullets total]

### Who it's for
[1–2 sentences. Specific.]

### Who should skip it
[1–2 sentences. Honest.]

### Price analysis
[Current price vs 30-day average, value judgment]

### Rating: X/10
[One sentence explaining the score]"""

WRITING_RULES = """\
- Direct, slightly opinionated voice
- No filler phrases: "in conclusion", "it's worth noting", "at the end of the day"
- No fake hedging: "some may find", "could potentially"
- Specific over vague: details beat generalities
- Short sentences preferred"""

FALLBACK_SKILL = """\
You are an expert content writer specializing in structured, well-researched product reviews.

Your workflow:
1. RESEARCH: Analyze all provided product information and specifications thoroughly.
2. STRUCTURE: Follow the exact review format provided — every section must be present.
3. DRAFT: Write with authority and specificity. Ground every claim in the product data.
4. REFINE: Ensure the review serves the reader — direct, actionable, no filler.

Core principles:
- Lead with the most valuable insight (the one-line verdict).
- Use specific details over generalizations at every opportunity.
- Every claim must be grounded in the provided specs or well-documented product characteristics.
- Structure for scannability: the spec table, tasting notes bullets, and named sections are mandatory.
- No padding, no marketing language, no invented personal consumption experience.

Follow the format precisely. Output only the review content, starting with the ## heading."""


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


def load_product(products_path: Path, product_id: str) -> dict[str, Any]:
    """Load a product record from products.json by ID."""
    with open(products_path) as f:
        products = json.load(f)
    for product in products:
        if product.get("id") == product_id:
            return product
    raise ValueError(f"Product '{product_id}' not found in {products_path}")


def load_context_file(path: str) -> str:
    """Load optional RAG context snippets from a plain-text file."""
    try:
        return Path(path).read_text()
    except OSError as exc:
        logger.warning(f"Could not read context file '{path}': {exc}")
        return ""


def build_system_prompt(skill_content: str) -> str:
    """Combine ECC skill instructions with the site's review format and voice rules."""
    return f"""{skill_content}

---

SITE REVIEW FORMAT — follow this exactly, every section is required:

{REVIEW_FORMAT}

---

WRITING RULES — hard requirements:
{WRITING_RULES}

VOICE RULES — non-negotiable:
- The coffee is the subject. State what it IS and DOES.
- Second person ("you get", "you'll find") is preferred.
- Never claim to have personally tried the product.
- Never write "buyers say", "customers report", or any crowd attribution.
- No hedging language: "may", "might", "could", "tends to", "can be" are banned.
- Absolute statements about product characteristics are fine and encouraged."""


def build_user_prompt(product: dict[str, Any], context: str) -> str:
    """Build the user-turn prompt with the full product spec."""
    flavor_notes = ", ".join(product.get("flavor_notes", []))
    brew_methods = ", ".join(product.get("best_brew_methods", []))

    lines = [
        f"Write a complete review of the following coffee product using the specified format.",
        "",
        f"Product: {product['name']}",
        f"Brand: {product['brand']}",
        f"Roast level: {product['roast_level']}",
        f"Origin: {product['origin']}",
        f"Process: {product['process_method']}",
        f"Weight: {product['weight_oz']} oz",
        f"Best brew methods: {brew_methods}",
        f"Flavor notes: {flavor_notes}",
        f"Acidity (1–5): {product.get('acidity', 'N/A')}",
        f"Body (1–5): {product.get('body', 'N/A')}",
        f"Sweetness (1–5): {product.get('sweetness', 'N/A')}",
        f"Bitterness (1–5): {product.get('bitterness', 'N/A')}",
        f"Roast intensity (1–5): {product.get('roast_intensity', 'N/A')}",
        f"Review framing: {product.get('review_framing', 'sensory')}",
    ]

    if product.get("amazon_asin"):
        lines.append(f"Amazon ASIN: {product['amazon_asin']}")
    if product.get("roaster_url"):
        lines.append(f"Roaster URL: {product['roaster_url']}")

    if context:
        lines += ["", "Additional context:", context]

    lines += ["", "Write the complete review now. Follow the format exactly."]
    return "\n".join(lines)


def print_mock_template(product: dict[str, Any]) -> None:
    """Print a template with product fields filled in but no generated text."""
    brew_methods = ", ".join(product.get("best_brew_methods", []))
    print(f"## {product['name']} Review")
    print()
    print("**One-line verdict**: [fill in]")
    print()
    print("| Spec | Detail |")
    print("|---|---|")
    print(f"| Roast | {product['roast_level']} |")
    print(f"| Origin | {product['origin']} |")
    print(f"| Process | {product['process_method']} |")
    print(f"| Best for | {brew_methods} |")
    print(f"| Price/oz | $X.XX |")
    print()
    print("### Tasting notes")
    for note in product.get("flavor_notes", []):
        print(f"- {note}")
    print()
    print("### Who it's for")
    print("[fill in]")
    print()
    print("### Who should skip it")
    print("[fill in]")
    print()
    print("### Price analysis")
    print("[fill in]")
    print()
    print("### Rating: X/10")
    print("[fill in]")


def main() -> None:
    """Parse arguments and generate a review draft."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    parser = argparse.ArgumentParser(
        description="Generate a coffee bean review using the ECC article-writing skill."
    )
    parser.add_argument(
        "--product",
        required=True,
        help="Product ID from scrapers/products.json",
    )
    parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Path to a plain-text RAG context file (optional)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Print a filled-in template without calling the API",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    products_path = repo_root / "scrapers" / "products.json"
    drafts_dir = repo_root / "drafts"

    try:
        product = load_product(products_path, args.product)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.mock:
        print_mock_template(product)
        return

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print(
            "Error: CLAUDE_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    skill_content = load_skill(ECC_SKILL_URL, SKILL_CACHE_PATH)
    context = load_context_file(args.context_file) if args.context_file else ""
    system_prompt = build_system_prompt(skill_content)
    user_prompt = build_user_prompt(product, context)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5-20251001",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    review_text = response.content[0].text.strip()

    drafts_dir.mkdir(parents=True, exist_ok=True)
    output_path = drafts_dir / f"{args.product}-review.md"
    output_path.write_text(review_text + "\n")

    print(str(output_path))


if __name__ == "__main__":
    main()
