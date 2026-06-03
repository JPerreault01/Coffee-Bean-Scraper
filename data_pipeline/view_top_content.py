"""
view_top_content.py

Reads training_data/raw/ JSONL files, ranks records by quality_score,
and writes the top N from each source to a readable Markdown file.

Run from the repo root:
    python data_pipeline/view_top_content.py
    python data_pipeline/view_top_content.py --top 5
    python data_pipeline/view_top_content.py --source reddit
    python data_pipeline/view_top_content.py --source web
    python data_pipeline/view_top_content.py --source youtube
    python data_pipeline/view_top_content.py --min-quality 0.6
    python data_pipeline/view_top_content.py --preview 1200
    python data_pipeline/view_top_content.py --output my_review.md
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ── Defaults ────────────────────────────────────────────────────────────────
RAW_DIR        = Path("training_data/raw")
DEFAULT_TOP    = 3          # items per source file
DEFAULT_PREV   = 800        # body/transcript preview chars
DEFAULT_OUTPUT = Path("training_data/top_content_preview.md")
COMMENT_PREV   = 250        # chars per top comment
TOP_COMMENTS   = 3          # number of top comments to show (reddit only)

# ── JSONL loader ─────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def top_records(records: list[dict], n: int, min_quality: float) -> list[dict]:
    filtered = [r for r in records if r.get("quality_score", 0.0) >= min_quality]
    return sorted(filtered, key=lambda r: r.get("quality_score", 0.0), reverse=True)[:n]


# ── Per-source formatters ────────────────────────────────────────────────────

def fmt_reddit(record: dict, preview: int) -> str:
    raw   = record.get("raw", {})
    title = raw.get("title", "(no title)")
    body  = raw.get("body", "").strip()
    score = raw.get("score", 0)
    n_com = raw.get("num_comments", 0)
    qual  = record.get("quality_score", 0.0)
    tags  = record.get("domain_tags", [])
    plink = raw.get("permalink", "")
    url   = f"https://reddit.com{plink}" if plink else ""

    lines = [
        f"**Quality score:** {qual:.3f}  |  **Upvotes:** {score:,}  |  **Comments:** {n_com:,}",
        f"**Tags:** {', '.join(tags) if tags else '—'}",
    ]
    if url:
        lines.append(f"**Link:** {url}")

    lines.append("")

    if body:
        preview_text = body[:preview]
        if len(body) > preview:
            preview_text += f"\n\n*… {len(body) - preview:,} more characters — open link to read full post*"
        lines.append(preview_text)
    else:
        lines.append("*(no body text — link-only post)*")

    comments = raw.get("comments", [])
    top = sorted(comments, key=lambda c: c.get("score", 0), reverse=True)[:TOP_COMMENTS]
    if top:
        lines.append("")
        lines.append(f"**Top {len(top)} comment(s):**")
        for c in top:
            c_body  = c.get("body", "").strip()[:COMMENT_PREV]
            c_score = c.get("score", 0)
            if c_body:
                lines.append(f"> **[{c_score} pts]** {c_body}")

    return "\n".join(lines)


def fmt_web(record: dict, preview: int) -> str:
    raw   = record.get("raw", {})
    title = raw.get("title", "(no title)")
    body  = raw.get("body", "").strip()
    url   = raw.get("url", "")
    qual  = record.get("quality_score", 0.0)
    tags  = record.get("domain_tags", [])

    lines = [
        f"**Quality score:** {qual:.3f}",
        f"**Tags:** {', '.join(tags) if tags else '—'}",
    ]
    if url:
        lines.append(f"**URL:** {url}")

    lines.append("")

    if body:
        preview_text = body[:preview]
        if len(body) > preview:
            preview_text += f"\n\n*… {len(body) - preview:,} more characters — open URL to read full article*"
        lines.append(preview_text)
    else:
        lines.append("*(no body text extracted)*")

    return "\n".join(lines)


def fmt_youtube(record: dict, preview: int) -> str:
    raw        = record.get("raw", {})
    title      = raw.get("title", "(no title)")
    channel    = raw.get("channel", "")
    vid        = raw.get("video_id", "")
    transcript = raw.get("transcript", "").strip()
    qual       = record.get("quality_score", 0.0)
    tags       = record.get("domain_tags", [])
    url        = f"https://www.youtube.com/watch?v={vid}" if vid else ""

    lines = [
        f"**Quality score:** {qual:.3f}",
        f"**Channel:** {channel}" if channel else "",
        f"**Tags:** {', '.join(tags) if tags else '—'}",
    ]
    lines = [l for l in lines if l]  # drop blank channel line if missing

    if url:
        lines.append(f"**URL:** {url}")

    lines.append("")

    if transcript:
        preview_text = transcript[:preview]
        if len(transcript) > preview:
            preview_text += f"\n\n*… {len(transcript) - preview:,} more characters — open URL for full video*"
        lines.append(preview_text)
    else:
        lines.append("*(no transcript)*")

    return "\n".join(lines)


# ── Markdown builder ─────────────────────────────────────────────────────────

def build_markdown(top_n: int, preview: int, source_filter: str | None, min_quality: float) -> str:
    sources = [source_filter] if source_filter else ["reddit", "web", "youtube"]

    header = [
        "# Coffee Training Data — Top Content Preview",
        "",
        f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **Top N per file:** {top_n}",
        f"- **Min quality score:** {min_quality}",
        f"- **Preview length:** {preview} chars",
        "",
        "---",
        "",
    ]

    body_lines: list[str] = []

    for source in sources:
        source_dir = RAW_DIR / source
        source_label = source.upper()

        body_lines.append(f"# {source_label}")
        body_lines.append("")

        if not source_dir.exists():
            body_lines.append(f"> ⚠️ Directory not found: `{source_dir}`")
            body_lines.append("> Run the pipeline first: `python data_pipeline/run_pipeline.py --{}`".format(source))
            body_lines.append("")
            continue

        jsonl_files = sorted(source_dir.glob("*.jsonl"))
        if not jsonl_files:
            body_lines.append("> No JSONL files found.")
            body_lines.append("")
            continue

        for path in jsonl_files:
            file_label = path.stem.replace("_", " ").title()
            body_lines.append(f"## {file_label}")
            body_lines.append("")

            records = load_jsonl(path)
            if not records:
                body_lines.append("*File is empty.*")
                body_lines.append("")
                continue

            top = top_records(records, top_n, min_quality)
            if not top:
                body_lines.append(
                    f"*No records with quality ≥ {min_quality} "
                    f"({len(records):,} total records in file).*"
                )
                body_lines.append("")
                continue

            body_lines.append(
                f"*{len(records):,} total records — showing top {len(top)} by quality score*"
            )
            body_lines.append("")

            for rank, record in enumerate(top, 1):
                raw       = record.get("raw", {})
                title     = raw.get("title", "(no title)")
                qual      = record.get("quality_score", 0.0)

                body_lines.append(f"### #{rank} — {title}")
                body_lines.append("")

                if source == "reddit":
                    body_lines.append(fmt_reddit(record, preview))
                elif source == "web":
                    body_lines.append(fmt_web(record, preview))
                elif source == "youtube":
                    body_lines.append(fmt_youtube(record, preview))

                body_lines.append("")
                body_lines.append("---")
                body_lines.append("")

    return "\n".join(header + body_lines)


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Preview top-ranked records from training_data/raw/"
    )
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP,
        help=f"Items to show per source file (default: {DEFAULT_TOP})"
    )
    parser.add_argument(
        "--source", choices=["reddit", "web", "youtube"], default=None,
        help="Show only one source (default: all three)"
    )
    parser.add_argument(
        "--min-quality", type=float, default=0.0,
        help="Skip records below this quality score (default: 0.0 — show everything)"
    )
    parser.add_argument(
        "--preview", type=int, default=DEFAULT_PREV,
        help=f"Characters of body/transcript to preview (default: {DEFAULT_PREV})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"Output path (default: {DEFAULT_OUTPUT})"
    )
    args = parser.parse_args()

    if not RAW_DIR.exists():
        print(
            f"ERROR: {RAW_DIR}/ does not exist.\n"
            "Run the pipeline first:\n"
            "  python data_pipeline/run_pipeline.py"
        )
        sys.exit(1)

    print(f"Reading from {RAW_DIR}/...")
    md = build_markdown(args.top, args.preview, args.source, args.min_quality)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    print(f"\n✓ Written to: {out}")
    print(f"  Open in VS Code: code {out}")
    print(f"\nQuick options:")
    print(f"  Show top 5 per file:    python data_pipeline/view_top_content.py --top 5")
    print(f"  Reddit only:            python data_pipeline/view_top_content.py --source reddit")
    print(f"  Web only:               python data_pipeline/view_top_content.py --source web")
    print(f"  Filter low quality:     python data_pipeline/view_top_content.py --min-quality 0.6")
    print(f"  Longer previews:        python data_pipeline/view_top_content.py --preview 1500")


if __name__ == "__main__":
    main()
