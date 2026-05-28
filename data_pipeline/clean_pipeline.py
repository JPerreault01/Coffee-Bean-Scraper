"""
Data cleaning pipeline for coffee training data.

Reads raw JSONL from training_data/raw/, produces cleaned JSONL in training_data/cleaned/.
Raw files are never modified.

Usage:
    python data_pipeline/clean_pipeline.py
    python data_pipeline/clean_pipeline.py --source reddit
    python data_pipeline/clean_pipeline.py --source web
    python data_pipeline/clean_pipeline.py --source youtube
"""

import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import ftfy
from datasketch import MinHash, MinHashLSH
from langdetect import detect, LangDetectException

logger = logging.getLogger("clean_pipeline")

RAW_DIR = Path("training_data/raw")
CLEANED_DIR = Path("training_data/cleaned")

COFFEE_TECH_TERMS = {
    "espresso", "extraction", "grind", "roast", "origin", "brew", "barista",
    "acidity", "mouthfeel", "bloom", "drawdown", "puck", "channeling",
    "pressure", "yield", "ratio",
}

# Regex for URL stripping
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# Reddit markdown patterns
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(.+?)\*")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_QUOTE_RE = re.compile(r"^>.*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_SUBREDDIT_RE = re.compile(r"\br/\w+\b")
_USER_RE = re.compile(r"\bu/\w+\b")

# Bot detection
_BOT_PATTERNS = re.compile(r"_bot$|^bot_|CafeBot|PriceBot", re.IGNORECASE)
_BOT_BODIES = {"this", "same", "lol", "nice", "wow"}
_BOT_PREFIX = "i am a bot"

# Web nav/boilerplate line patterns
_NAV_PHRASES = re.compile(
    r"\b(subscribe|newsletter|sign up|read more|click here|share this|tags:|categories:|"
    r"filed under|posted in|leave a reply)\b",
    re.IGNORECASE,
)
_DATE_ONLY_RE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},?\s+\d{4}$|^\d{1,2}/\d{1,2}/\d{2,4}$|^\d{4}-\d{2}-\d{2}$",
    re.IGNORECASE,
)

# Emoji range (broad Unicode range for emoji)
_EMOJI_RE = re.compile(
    "[\U00010000-\U0010ffff"
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F9FF"
    "☀-⛿"
    "✀-➿]+",
    flags=re.UNICODE,
)

# Reddit title spam patterns
_SPAM_TITLE_RE = re.compile(
    r"^price check|^\[WTS\]|^\[WTB\]|where to buy|^ISO\b",
    re.IGNORECASE,
)

# YouTube bracket artifacts
_BRACKET_RE = re.compile(r"\[[^\]]*\]")
# Sentence boundary reconstruction — capitalize first letter after sentence-ending punctuation
_SENTENCE_BOUNDARY_RE = re.compile(r"([.!?])\s+([a-z])")


# ---------------------------------------------------------------------------
# Universal cleaning
# ---------------------------------------------------------------------------

def _detect_language(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def _count_emoji(text: str) -> int:
    return len(_EMOJI_RE.findall(text))


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def universal_clean_text(text: str) -> str:
    """Apply encoding repair, URL stripping, Unicode normalization, whitespace normalization."""
    text = ftfy.fix_text(text)
    text = _URL_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    # Collapse 3+ repeated punctuation chars to 2
    text = re.sub(r"([!?.,;:\-_])\1{2,}", r"\1\1", text)
    # Collapse spaces/tabs to single space
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _flag_record(record: dict, reason: str) -> dict:
    record["flagged"] = True
    record.setdefault("flag_reasons", []).append(reason)
    return record


def apply_universal_fields(record: dict, primary_text: str, min_chars: int) -> dict:
    """Add is_english, flagged, duplicate fields and enforce minimum length."""
    lang = _detect_language(primary_text)
    record["language"] = lang
    record["is_english"] = lang == "en"
    if not record["is_english"]:
        record.setdefault("flagged", False)
    record.setdefault("flagged", False)
    record.setdefault("flag_reasons", [])
    record.setdefault("duplicate", False)
    record.setdefault("duplicate_of", None)

    if len(primary_text) < min_chars:
        record["quality_score"] = 0
        _flag_record(record, "below_min_length_after_clean")

    return record


# ---------------------------------------------------------------------------
# Reddit cleaning
# ---------------------------------------------------------------------------

def _clean_reddit_comment_body(body: str) -> str:
    body = _QUOTE_RE.sub("", body)
    body = _BOLD_RE.sub(r"\1", body)
    body = _ITALIC_RE.sub(r"\1", body)
    body = _STRIKE_RE.sub(r"\1", body)
    body = _LINK_RE.sub(r"\1", body)
    body = _SUBREDDIT_RE.sub("", body)
    body = _USER_RE.sub("", body)
    if _count_emoji(body) > 3:
        body = _strip_emoji(body)
    return body.strip()


def _is_bot_comment(author: str, body: str, score: int) -> bool:
    if author == "AutoModerator":
        return True
    if _BOT_PATTERNS.search(author):
        return True
    body_lower = body.strip().lower()
    if body_lower in _BOT_BODIES and len(body) < 15:
        return True
    if body_lower.startswith(_BOT_PREFIX):
        return True
    if score < 0:
        return True
    return False


def _is_spam_post(title: str, body: str, score: int) -> bool:
    if _SPAM_TITLE_RE.search(title):
        return True
    if not body and score < 200:
        return True
    stripped = _URL_RE.sub("", body).strip()
    if body and not stripped:
        return True
    return False


def clean_reddit_record(record: dict) -> dict:
    raw = record.get("raw", {})
    title = universal_clean_text(raw.get("title", ""))
    body = universal_clean_text(raw.get("body", ""))
    raw["title"] = title
    raw["body"] = body

    score = raw.get("score", 0)
    if _is_spam_post(title, body, score):
        _flag_record(record, "spam_post")

    cleaned_comments = []
    for comment in raw.get("comments", []):
        author = comment.get("author", "")
        cbody = comment.get("body", "")
        cscore = comment.get("score", 0)
        if _is_bot_comment(author, cbody, cscore):
            continue
        cbody = _clean_reddit_comment_body(universal_clean_text(cbody))
        comment["body"] = cbody

        cleaned_replies = []
        for reply in comment.get("replies", []):
            rbody = reply.get("body", "")
            if _is_bot_comment(reply.get("author", ""), rbody, reply.get("score", 0)):
                continue
            reply["body"] = _clean_reddit_comment_body(universal_clean_text(rbody))
            cleaned_replies.append(reply)
        comment["replies"] = cleaned_replies
        cleaned_comments.append(comment)

    raw["comments"] = cleaned_comments
    record["raw"] = raw

    primary_text = title + " " + body
    apply_universal_fields(record, primary_text, min_chars=50)
    return record


# ---------------------------------------------------------------------------
# Web cleaning
# ---------------------------------------------------------------------------

def _is_nav_line(line: str) -> bool:
    if len(line) < 40 and not line.rstrip()[-1:] in ".!?,;:":
        return True
    if _NAV_PHRASES.search(line):
        return True
    if _DATE_ONLY_RE.match(line.strip()):
        return True
    return False


def _is_tag_paragraph(para: str) -> bool:
    parts = [p.strip() for p in para.split(",")]
    return len(parts) >= 5 and all(len(p.split()) <= 3 for p in parts if p)


def clean_web_record(record: dict) -> dict:
    raw = record.get("raw", {})
    title = universal_clean_text(raw.get("title", ""))
    body = universal_clean_text(raw.get("body", ""))
    raw["title"] = title

    # Line-level filtering
    lines = body.splitlines()
    lines = [l for l in lines if l.strip() and not _is_nav_line(l.strip())]

    # Paragraph-level filtering
    paragraphs = "\n".join(lines).split("\n\n")
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    paragraphs = [p for p in paragraphs if len(p) >= 60 and not _is_tag_paragraph(p)]

    body = "\n\n".join(paragraphs)
    raw["body"] = body
    record["raw"] = raw

    # Content quality checks
    sentences = re.split(r"[.!?]+", body)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 5:
        _flag_record(record, "too_few_sentences")

    words = body.lower().split()
    if len(words) >= 500:
        tech_hits = sum(1 for w in words if w in COFFEE_TECH_TERMS)
        if tech_hits == 0:
            record["quality_score"] = max(0.0, round(record.get("quality_score", 0.5) - 0.3, 4))

    apply_universal_fields(record, body, min_chars=500)
    return record


# ---------------------------------------------------------------------------
# YouTube cleaning
# ---------------------------------------------------------------------------

def _apply_term_corrections(text: str, corrections: dict) -> str:
    """Apply find/replace for known mis-transcribed technical terms (whole word, case-insensitive)."""
    for wrong, right in corrections.items():
        text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text, flags=re.IGNORECASE)
    return text


def _reconstruct_sentences(text: str) -> str:
    """Capitalize first letter after sentence-ending punctuation followed by a space."""
    return _SENTENCE_BOUNDARY_RE.sub(lambda m: m.group(1) + " " + m.group(2).upper(), text)


def clean_youtube_record(record: dict, term_corrections: dict) -> dict:
    raw = record.get("raw", {})
    transcript = raw.get("transcript", "")

    # Remove bracket artifacts
    transcript = _BRACKET_RE.sub("", transcript)
    # Remove standalone filler words
    transcript = re.sub(r"\b(um|uh|hmm)\b\s*", "", transcript, flags=re.IGNORECASE)
    # Apply term corrections from config
    transcript = _apply_term_corrections(transcript, term_corrections)
    # Universal cleaning
    transcript = universal_clean_text(transcript)
    # Sentence reconstruction
    transcript = _reconstruct_sentences(transcript)

    raw["transcript"] = transcript
    record["raw"] = raw

    apply_universal_fields(record, transcript, min_chars=300)
    return record


# ---------------------------------------------------------------------------
# MinHash near-duplicate detection
# ---------------------------------------------------------------------------

def _make_shingles(text: str, size: int = 5) -> set[str]:
    words = text.lower().split()
    if len(words) < size:
        return {" ".join(words)}
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def _make_minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for shingle in _make_shingles(text):
        m.update(shingle.encode("utf8"))
    return m


def deduplicate_records(records: list[dict], primary_text_fn) -> tuple[list[dict], int]:
    """
    Run MinHash LSH deduplication. Within each cluster, keep highest quality_score.
    Returns (deduped_records, duplicate_count).
    """
    NUM_PERM = 128
    THRESHOLD = 0.8

    lsh = MinHashLSH(threshold=THRESHOLD, num_perm=NUM_PERM)
    minhashes: dict[str, MinHash] = {}

    # Index all records
    for i, rec in enumerate(records):
        text = primary_text_fn(rec)
        if not text:
            continue
        m = _make_minhash(text, NUM_PERM)
        key = str(i)
        minhashes[key] = m
        try:
            lsh.insert(key, m)
        except ValueError:
            pass  # duplicate key edge case

    # Find duplicate clusters
    duplicate_of: dict[int, int] = {}
    visited: set[int] = set()

    for i, rec in enumerate(records):
        if i in visited:
            continue
        key = str(i)
        if key not in minhashes:
            continue
        neighbours = lsh.query(minhashes[key])
        neighbour_idxs = [int(n) for n in neighbours if int(n) != i]
        if not neighbour_idxs:
            continue

        cluster = [i] + neighbour_idxs
        # Keep the record with the highest quality_score
        best = max(cluster, key=lambda idx: records[idx].get("quality_score", 0))
        for idx in cluster:
            visited.add(idx)
            if idx != best:
                duplicate_of[idx] = best

    # Mark duplicates
    dup_count = 0
    for i, rec in enumerate(records):
        if i in duplicate_of:
            rec["duplicate"] = True
            rec["duplicate_of"] = duplicate_of[i]
            dup_count += 1

    return records, dup_count


# ---------------------------------------------------------------------------
# Source-specific pipeline runners
# ---------------------------------------------------------------------------

def _primary_text_reddit(rec: dict) -> str:
    raw = rec.get("raw", {})
    return raw.get("title", "") + " " + raw.get("body", "")


def _primary_text_web(rec: dict) -> str:
    return rec.get("raw", {}).get("body", "")


def _primary_text_youtube(rec: dict) -> str:
    return rec.get("raw", {}).get("transcript", "")


def process_reddit(config: dict) -> dict:
    raw_dir = RAW_DIR / "reddit"
    out_dir = CLEANED_DIR / "reddit"
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "input_records": 0,
        "output_records": 0,
        "flagged": 0,
        "non_english": 0,
        "duplicates_removed": 0,
        "comments_removed": 0,
    }

    if not raw_dir.exists():
        logger.warning(f"No reddit raw data at {raw_dir}")
        return stats

    all_records: list[dict] = []

    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    stats["input_records"] += 1

                    before_comments = len(rec.get("raw", {}).get("comments", []))
                    rec = clean_reddit_record(rec)
                    after_comments = len(rec.get("raw", {}).get("comments", []))
                    stats["comments_removed"] += before_comments - after_comments

                    all_records.append(rec)
                except Exception as e:
                    logger.warning(f"Error processing record in {jsonl_file}: {e}")

    logger.info(f"Reddit: {len(all_records)} records cleaned, running deduplication...")
    all_records, dup_count = deduplicate_records(all_records, _primary_text_reddit)
    stats["duplicates_removed"] = dup_count

    for rec in all_records:
        if rec.get("flagged"):
            stats["flagged"] += 1
        if not rec.get("is_english", True):
            stats["non_english"] += 1
        stats["output_records"] += 1

    # Write by subreddit
    by_subreddit: dict[str, list] = {}
    for rec in all_records:
        subreddit = rec.get("raw", {}).get("subreddit", "unknown")
        by_subreddit.setdefault(subreddit, []).append(rec)

    for subreddit, recs in by_subreddit.items():
        out_path = out_dir / f"{subreddit}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"Reddit cleaning done: {stats}")
    return stats


def process_web(config: dict) -> dict:
    raw_dir = RAW_DIR / "web"
    out_dir = CLEANED_DIR / "web"
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "input_records": 0,
        "output_records": 0,
        "flagged": 0,
        "non_english": 0,
        "duplicates_removed": 0,
    }

    if not raw_dir.exists():
        logger.warning(f"No web raw data at {raw_dir}")
        return stats

    all_records: list[dict] = []

    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    stats["input_records"] += 1
                    rec = clean_web_record(rec)
                    all_records.append(rec)
                except Exception as e:
                    logger.warning(f"Error processing record in {jsonl_file}: {e}")

    logger.info(f"Web: {len(all_records)} records cleaned, running deduplication...")
    all_records, dup_count = deduplicate_records(all_records, _primary_text_web)
    stats["duplicates_removed"] = dup_count

    for rec in all_records:
        if rec.get("flagged"):
            stats["flagged"] += 1
        if not rec.get("is_english", True):
            stats["non_english"] += 1
        stats["output_records"] += 1

    # Write by site
    by_site: dict[str, list] = {}
    for rec in all_records:
        site = rec.get("raw", {}).get("site", "unknown")
        by_site.setdefault(site, []).append(rec)

    for site, recs in by_site.items():
        out_path = out_dir / f"{site}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"Web cleaning done: {stats}")
    return stats


def process_youtube(config: dict) -> dict:
    raw_dir = RAW_DIR / "youtube"
    out_dir = CLEANED_DIR / "youtube"
    out_dir.mkdir(parents=True, exist_ok=True)

    term_corrections = config.get("youtube", {}).get("term_corrections", {})

    stats = {
        "input_records": 0,
        "output_records": 0,
        "flagged": 0,
        "non_english": 0,
        "duplicates_removed": 0,
    }

    if not raw_dir.exists():
        logger.warning(f"No youtube raw data at {raw_dir}")
        return stats

    all_records: list[dict] = []

    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    stats["input_records"] += 1
                    rec = clean_youtube_record(rec, term_corrections)
                    all_records.append(rec)
                except Exception as e:
                    logger.warning(f"Error processing record in {jsonl_file}: {e}")

    logger.info(f"YouTube: {len(all_records)} records cleaned, running deduplication...")
    all_records, dup_count = deduplicate_records(all_records, _primary_text_youtube)
    stats["duplicates_removed"] = dup_count

    for rec in all_records:
        if rec.get("flagged"):
            stats["flagged"] += 1
        if not rec.get("is_english", True):
            stats["non_english"] += 1
        stats["output_records"] += 1

    # Write by channel
    by_channel: dict[str, list] = {}
    for rec in all_records:
        channel = rec.get("raw", {}).get("channel_name", "unknown")
        by_channel.setdefault(channel, []).append(rec)

    for channel, recs in by_channel.items():
        out_path = out_dir / f"{channel}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"YouTube cleaning done: {stats}")
    return stats


def write_clean_summary(reddit_stats: dict, web_stats: dict, youtube_stats: dict):
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "cleaned_at": datetime.now(tz=timezone.utc).isoformat(),
        "reddit": reddit_stats,
        "web": web_stats,
        "youtube": youtube_stats,
    }
    out_path = CLEANED_DIR / "clean_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Clean summary written to {out_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Coffee training data cleaning pipeline")
    parser.add_argument(
        "--source",
        choices=["reddit", "web", "youtube"],
        help="Clean a single source only (default: all)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[clean_pipeline] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )

    config_path = Path(__file__).parent / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    reddit_stats = {"input_records": 0, "output_records": 0, "flagged": 0, "non_english": 0, "duplicates_removed": 0, "comments_removed": 0}
    web_stats = {"input_records": 0, "output_records": 0, "flagged": 0, "non_english": 0, "duplicates_removed": 0}
    youtube_stats = {"input_records": 0, "output_records": 0, "flagged": 0, "non_english": 0, "duplicates_removed": 0}

    run_all = args.source is None

    if run_all or args.source == "reddit":
        logger.info("=== Cleaning Reddit data ===")
        reddit_stats = process_reddit(config)

    if run_all or args.source == "web":
        logger.info("=== Cleaning Web data ===")
        web_stats = process_web(config)

    if run_all or args.source == "youtube":
        logger.info("=== Cleaning YouTube data ===")
        youtube_stats = process_youtube(config)

    summary = write_clean_summary(reddit_stats, web_stats, youtube_stats)

    print("\n=== Cleaning Summary ===")
    for source in ["reddit", "web", "youtube"]:
        s = summary[source]
        print(f"{source}: {s['input_records']} in → {s['output_records']} out "
              f"| flagged: {s['flagged']} | non-english: {s['non_english']} "
              f"| duplicates: {s['duplicates_removed']}")


if __name__ == "__main__":
    main()
