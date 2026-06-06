# scrapers/reformat_origin_descriptions.py
"""
Reformat origin taxonomy term descriptions from plain-text walls into clean HTML.

The taxonomy template (taxonomy-bean-archive.php) renders descriptions via
wp_kses_post(), so HTML is fully supported. This script fetches every `origin`
term, sends any plain-text description to Claude for HTML reformatting (no facts
added or removed), and writes the result back via WP-CLI.

Flow:
  1. SSH + WP-CLI to list all origin terms (term_id, slug, name, description).
  2. Skip empty descriptions and ones that already contain HTML tags.
  3. Reformat the rest with Claude (claude-haiku-4-5-20251001).
  4. SSH + WP-CLI to update each term's description.
  5. Print a summary (updated / skipped / failed).

Designed to run on the server via the venv python:
  /opt/venv/bin/python3 /opt/scrapers/reformat_origin_descriptions.py

  --dry-run  Reformat and print, but do not write back to WordPress.

When WordPress is present locally (i.e. running on the server) WP-CLI is invoked
directly; otherwise commands are wrapped in SSH so the script also works when run
from a workstation.

Dependencies: anthropic (already installed in /opt/venv).
"""

import argparse
import json
import os
import re
import subprocess
import sys

# --- Server / WordPress connection -----------------------------------------
SSH_HOST = "root@142.93.127.178"
WP_PATH = "/var/www/coffeebeans"
REMOTE_TMP = "/tmp/origin_desc.html"
# Term descriptions are run through restrictive kses (no <p>/<h2>/<ul>) unless
# the acting user has unfiltered_html. Run updates as the admin (ID 1) so the
# block-level HTML survives the write.
WP_USER = "1"

# --- Claude -----------------------------------------------------------------
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4000

# /opt/.env on the server, with a repo fallback so the script can be inspected
# locally. The reformat step needs CLAUDE_API_KEY from whichever exists.
ENV_PATHS = ["/opt/.env", ".env"]

SYSTEM_PROMPT = """You reformat plain-text coffee-origin guide descriptions into clean, semantic HTML.

You will be given the existing plain-text description of a coffee origin taxonomy term. Reformat it as HTML following this EXACT structure:

- Opening intro: 1-2 <p> tags. No heading. Go straight into the content.
- Each named section becomes: <h2>Section Title</h2> followed by <p> paragraphs or <ul><li> items as appropriate to the content.
- Brew/method sections (brewing tips, how to brew, preparation, etc.) use <ul><li> lists.
- FAQ section: <h2>Frequently Asked Questions</h2> followed by repeated <h3>Question text</h3><p>Answer text</p> pairs, one pair per question.

Hard rules:
- No <div> wrappers. No inline styles. No class attributes. No id attributes.
- Preserve all factual content EXACTLY. Do not add facts. Do not remove facts. Do not rewrite or reinterpret facts. Only restructure the existing text into HTML.
- Do not invent section headings that are not implied by the source text. If the source has no clear sections, use a sensible heading drawn from the content itself.
- Return ONLY the HTML. No preamble. No explanation. No markdown code fences."""

# Tags whose presence means a description has already been reformatted.
HTML_TAG_RE = re.compile(r"<(h[1-6]|p|ul|ol|li|div|section|article)\b", re.IGNORECASE)

# Running on the server? Then WordPress lives locally and we skip SSH-to-self
# (the server has no key to SSH back into its own public IP).
ON_SERVER = os.path.isdir(WP_PATH)


def run_remote(remote_cmd: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Run a shell command against the WordPress host.

    On the server this is a local `bash -c`; from a workstation it is wrapped in
    SSH. Either way the command is parsed by a remote/local shell, so command
    substitution like $(cat ...) works identically.
    """
    if ON_SERVER:
        argv = ["bash", "-c", remote_cmd]
    else:
        argv = ["ssh", SSH_HOST, remote_cmd]
    return subprocess.run(argv, input=stdin, text=True, capture_output=True)


def load_env() -> dict:
    """Parse the first existing .env file into a dict; overlay real env vars."""
    import os

    env = {}
    for path in ENV_PATHS:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip().strip('"').strip("'")
            break
        except FileNotFoundError:
            continue
    env.update(os.environ)
    return env


def fetch_terms() -> list[dict]:
    """Return all origin terms as a list of dicts via WP-CLI over SSH."""
    remote = (
        f"wp --path={WP_PATH} term list origin "
        f"--fields=term_id,slug,name,description --format=json --allow-root"
    )
    result = run_remote(remote)
    if result.returncode != 0:
        print("ERROR: failed to fetch origin terms via WP-CLI:", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def is_html(description: str) -> bool:
    """True if the description already contains block-level HTML tags."""
    return bool(HTML_TAG_RE.search(description))


def reformat(description: str, env: dict) -> str:
    """Send plain text to Claude and return clean HTML."""
    import anthropic

    api_key = env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY not found in /opt/.env")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": description}],
    )
    html = "".join(block.text for block in message.content if block.type == "text").strip()

    # Strip accidental markdown fences if the model wrapped the output.
    if html.startswith("```"):
        html = re.sub(r"^```[a-zA-Z]*\n?", "", html)
        html = re.sub(r"\n?```$", "", html).strip()
    return strip_dashes(html)


def strip_dashes(text: str) -> str:
    """Site-wide ban on em/en-dashes in AI output. Mirrors generate_review.py."""
    return (
        text
        .replace(" — ", ". ")
        .replace(" – ", ", ")
        .replace("—", ", ")
        .replace("–", "-")
    )


def update_term(term_id: int, html: str) -> None:
    """Write reformatted HTML back to the term description via WP-CLI.

    Shell escaping is avoided entirely: the HTML is staged in a temp file, then
    read back into --description via command substitution inside double quotes
    (cat output is inserted verbatim, never re-parsed for quotes or $).
    """
    # 1. Stage the HTML in a temp file (local write on server, stdin->cat over SSH).
    if ON_SERVER:
        with open(REMOTE_TMP, "w") as f:
            f.write(html)
    else:
        write = run_remote(f"cat > {REMOTE_TMP}", stdin=html)
        if write.returncode != 0:
            raise RuntimeError(f"failed to stage description: {write.stderr.strip()}")

    # 2. Update the term, reading the description from the staged file.
    remote = (
        f'wp --path={WP_PATH} term update origin {term_id} '
        f'--description="$(cat {REMOTE_TMP})" --user={WP_USER} --allow-root'
    )
    update = run_remote(remote)
    if update.returncode != 0:
        raise RuntimeError(f"wp term update failed: {update.stderr.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reformat origin taxonomy descriptions from plain text to HTML"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Reformat and print, but do not write back to WordPress",
    )
    args = parser.parse_args()

    env = load_env()
    terms = fetch_terms()
    print(f"Fetched {len(terms)} origin terms.", file=sys.stderr)

    updated, skipped, failed = 0, 0, 0

    for term in terms:
        term_id = term["term_id"]
        name = term.get("name", "")
        description = (term.get("description") or "").strip()

        if not description:
            print(f"  skip  [{term_id}] {name}: empty description", file=sys.stderr)
            skipped += 1
            continue

        if is_html(description):
            print(f"  skip  [{term_id}] {name}: already HTML", file=sys.stderr)
            skipped += 1
            continue

        try:
            html = reformat(description, env)
        except Exception as exc:
            print(f"  FAIL  [{term_id}] {name}: reformat error: {exc}", file=sys.stderr)
            failed += 1
            continue

        if args.dry_run:
            print(f"\n===== [{term_id}] {name} (dry-run) =====")
            print(html)
            updated += 1
            continue

        try:
            update_term(term_id, html)
            print(f"  OK    [{term_id}] {name}: updated", file=sys.stderr)
            updated += 1
        except Exception as exc:
            print(f"  FAIL  [{term_id}] {name}: update error: {exc}", file=sys.stderr)
            failed += 1

    print("\n" + "=" * 50, file=sys.stderr)
    label = "would update" if args.dry_run else "updated"
    print(
        f"Summary: {updated} {label}, {skipped} skipped (empty/already HTML), "
        f"{failed} failed.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
