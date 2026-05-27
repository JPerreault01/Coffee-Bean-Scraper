"""
Data cleaning pipeline for coffee training data.
Reads raw JSONL from training_data/raw/, writes cleaned JSONL to training_data/cleaned/.
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

# Matches common bot author patterns
BOT_AUTHOR_RE = re.compile(r"(_bot$|^bot_|CafeBot|PriceBot)", re.IGNORECASE)

# Reddit post title patterns to flag
REDDIT_FLAG_TITLE_RE = re.compile(
    r"(^price check|^\[WTS\]|^\[WTB\]|where to buy|^ISO\b)",
    re.IGNORECASE,
)

# Web line noise patterns
WEB_LINE_NOISE_RE = re.compile(
    r"(^subscribe$|^newsletter$|^sign up$|^read more$|^click here$|^share this$"
    r"|^tags:|^categories:|^filed under|^posted in|^comments \(|^leave a reply)",
    re.IGNORECASE,
)

# Purely a date string (rough heuristic)
DATE_ONLY_RE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},?\s+\d{4}$"
    r"|^\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}$",
    re.IGNORECASE,
)

# YouTube artifact patterns
YT_FILLER_RE = re.compile(r"\b(um|uh|hmm)\b", re.IGNORECASE)
YT_BRACKET_RE = re.compile(r"\[.*?\]")

# Emoji detection (simplified: Unicode ranges covering most emoji)
EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


# ---------------------------------------------------------------------------
# Universal cleaning
# ---------------------------------------------------------------------------

def universal_clean(text: str) -> str:
    """Repair encoding, strip URLs, normalize unicode/whitespace."""
    text = ftfy.fix_text(text)

    # Strip URLs
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)

    # NFKC normalization
    text = unicodedata.normalize("NFKC", text)

    # Collapse repeated punctuation (3+ same char → 2)
    text = re.sub(r"([^\w\s])\1{2,}", r"\1\1", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def detect_language(text: str) -> str:
    try:
        return detect(text[:2000])
    except LangDetectException:
        return "unknown"


def apply_universal(record: dict, primary_field: str) -> dict:
    """Apply universal cleaning to all string fields in record['raw']."""
    raw = record.get("raw", {})

    for key, val in raw.items():
        if isinstance(val, str):
            raw[key] = universal_clean(val)
        elif isinstance(val, list):
            raw[key] = [universal_clean(v) if isinstance(v, str) else v for v in val]

    primary_text = raw.get(primary_field, "")
    lang = detect_language(primary_text)
    record["language"] = lang
    record["is_english"] = lang == "en"

    return record


# ---------------------------------------------------------------------------
# Reddit cleaning
# ---------------------------------------------------------------------------

def strip_reddit_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Remove block quotes
    text = re.sub(r"(?m)^>.*$", "", text)
    # [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Subreddit and user mentions
    text = re.sub(r"\br/\w+\b", "", text)
    text = re.sub(r"\bu/\w+\b", "", text)
    return text


def strip_excessive_emoji(text: str) -> str:
    emoji_count = len(EMOJI_RE.findall(text))
    if emoji_count > 3:
        return EMOJI_RE.sub("", text)
    return text


def is_bot_comment(author: str, body: str) -> bool:
    if author == "AutoModerator":
        return True
    if BOT_AUTHOR_RE.search(author):
        return True
    if body.lower().startswith("i am a bot"):
        return True
    return False


TRIVIAL_COMMENT_BODIES = {"this", "same", "lol", "nice", "wow"}


def is_trivial_comment(body: str) -> bool:
    stripped = body.strip().lower()
    return stripped in TRIVIAL_COMMENT_BODIES and len(stripped) < 15


def clean_comment(comment: dict) -> dict | None:
    """Return cleaned comment dict, or None to drop it."""
    author = comment.get("author", "")
    body = comment.get("body", "")
    score = comment.get("score", 0)

    if is_bot_comment(author, body):
        return None
    if is_trivial_comment(body):
        return None
    if score < 0:
        return None

    body = strip_reddit_markdown(body)
    body = strip_excessive_emoji(body)
    body = re.sub(r"[ \t]+", " ", body).strip()

    if not body:
        return None

    comment = dict(comment)
    comment["body"] = body

    if comment.get("replies"):
        cleaned_replies = [r for r in (clean_comment(r) for r in comment["replies"]) if r]
        comment["replies"] = cleaned_replies

    return comment


def clean_reddit_record(record: dict, min_length: int = 50) -> dict:
    record = apply_universal(record, primary_field="body")
    raw = record["raw"]
    title = raw.get("title", "")
    body = raw.get("body", "")

    flagged = False

    if REDDIT_FLAG_TITLE_RE.search(title):
        flagged = True

    if not body and raw.get("score", 0) < 200:
        flagged = True

    url_only = re.match(r"^\s*https?://\S+\s*$", body)
    if url_only:
        flagged = True

    cleaned_comments = []
    for comment in raw.get("comments", []):
        cleaned = clean_comment(comment)
        if cleaned:
            cleaned_comments.append(cleaned)
    raw["comments"] = cleaned_comments

    if len(body) < min_length:
        record["quality_score"] = 0.0
        flagged = True

    record["flagged"] = flagged
    record["duplicate"] = False
    record["duplicate_of"] = None
    return record


# ---------------------------------------------------------------------------
# Web cleaning
# ---------------------------------------------------------------------------

def clean_web_lines(text: str) -> str:
    lines = text.splitlines()
    kept = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if len(line) < 40 and not re.search(r"[.!?,:;]$", line):
            continue
        if WEB_LINE_NOISE_RE.search(line):
            continue
        if DATE_ONLY_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def clean_web_paragraphs(text: str) -> str:
    paragraphs = re.split(r"\n{2,}", text)
    kept = []
    for para in paragraphs:
        para = para.strip()
        if len(para) < 60:
            continue
        # Tag/category dump: mostly comma-separated short tokens
        tokens = [t.strip() for t in para.split(",")]
        if len(tokens) > 5 and all(len(t) < 30 for t in tokens):
            continue
        kept.append(para)
    return "\n\n".join(kept)


def clean_web_record(record: dict, min_length: int = 500) -> dict:
    record = apply_universal(record, primary_field="body")
    raw = record["raw"]
    body = raw.get("body", "")

    body = clean_web_lines(body)
    body = clean_web_paragraphs(body)
    raw["body"] = body

    flagged = False

    sentences = re.split(r"[.!?]", body)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 5:
        flagged = True

    if len(body.split()) >= 500:
        text_lower = body.lower()
        tech_hits = sum(1 for term in COFFEE_TECH_TERMS if term in text_lower)
        if tech_hits == 0:
            record["quality_score"] = max(0.0, round(record.get("quality_score", 0.0) - 0.3, 4))

    if len(body) < min_length:
        record["quality_score"] = 0.0
        flagged = True

    record["flagged"] = flagged
    record["duplicate"] = False
    record["duplicate_of"] = None
    return record


# ---------------------------------------------------------------------------
# YouTube cleaning
# ---------------------------------------------------------------------------

def reconstruct_sentences(text: str) -> str:
    """Capitalize word after sentence-ending punctuation followed by space."""
    def _cap_after(m):
        return m.group(1) + " " + m.group(2).upper()

    return re.sub(r"([.!?]) ([a-z])", _cap_after, text)


def apply_term_corrections(text: str, corrections: dict) -> str:
    for wrong, right in corrections.items():
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
        text = pattern.sub(right, text)
    return text


def clean_youtube_record(record: dict, corrections: dict, min_length: int = 300) -> dict:
    record = apply_universal(record, primary_field="transcript")
    raw = record["raw"]
    transcript = raw.get("transcript", "")

    # Remove bracket artifacts
    transcript = YT_BRACKET_RE.sub("", transcript)

    # Remove filler words as standalone tokens
    transcript = YT_FILLER_RE.sub("", transcript)

    # Collapse whitespace after removals
    transcript = re.sub(r"\s+", " ", transcript).strip()

    transcript = reconstruct_sentences(transcript)
    transcript = apply_term_corrections(transcript, corrections)

    raw["transcript"] = transcript

    flagged = len(transcript) < min_length
    if flagged:
        record["quality_score"] = 0.0

    record["flagged"] = flagged
    record["duplicate"] = False
    record["duplicate_of"] = None
    return record


# ---------------------------------------------------------------------------
# MinHash deduplication
# ---------------------------------------------------------------------------

def make_shingles(text: str, k: int = 5) -> set[str]:
    words = text.lower().split()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def minhash_dedup(records: list[dict], primary_field: str, threshold: float = 0.8) -> tuple[list[dict], int]:
    """Mark near-duplicates. Returns (records_with_flags, duplicate_count)."""
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    signatures: dict[int, MinHash] = {}

    for idx, record in enumerate(records):
        text = record.get("raw", {}).get(primary_field, "")
        shingles = make_shingles(text)
        m = MinHash(num_perm=128)
        for shingle in shingles:
            m.update(shingle.encode("utf8"))
        signatures[idx] = m
        try:
            lsh.insert(str(idx), m)
        except ValueError:
            pass

    duplicate_count = 0
    for idx, record in enumerate(records):
        if record.get("duplicate"):
            continue
        m = signatures[idx]
        neighbors = lsh.query(m)
        neighbors = [int(n) for n in neighbors if int(n) != idx]
        for neighbor_idx in neighbors:
            if records[neighbor_idx].get("duplicate"):
                continue
            # Keep the higher quality_score record
            if records[idx].get("quality_score", 0) >= records[neighbor_idx].get("quality_score", 0):
                records[neighbor_idx]["duplicate"] = True
                records[neighbor_idx]["duplicate_of"] = str(idx)
                duplicate_count += 1
            else:
                records[idx]["duplicate"] = True
                records[idx]["duplicate_of"] = str(neighbor_idx)
                duplicate_count += 1
                break

    return records, duplicate_count


# ---------------------------------------------------------------------------
# Per-source runners
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed line in {path}: {e}")
    return records


def write_jsonl(records: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_reddit(config: dict) -> dict:
    raw_dir = RAW_DIR / "reddit"
    out_dir = CLEANED_DIR / "reddit"
    stats = {"input_records": 0, "output_records": 0, "flagged": 0, "non_english": 0,
             "duplicates_removed": 0, "comments_removed": 0}

    if not raw_dir.exists():
        logger.warning(f"Reddit raw dir not found: {raw_dir}")
        return stats

    all_records = []
    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        records = load_jsonl(jsonl_file)
        stats["input_records"] += len(records)
        cleaned = []
        for record in records:
            before_comments = len(record.get("raw", {}).get("comments", []))
            record = clean_reddit_record(record, min_length=config["reddit"]["short_post_min_chars"])
            after_comments = len(record.get("raw", {}).get("comments", []))
            stats["comments_removed"] += max(0, before_comments - after_comments)
            if not record["is_english"]:
                stats["non_english"] += 1
            if record["flagged"]:
                stats["flagged"] += 1
            cleaned.append(record)
        all_records.extend(cleaned)

    all_records, dup_count = minhash_dedup(all_records, "body")
    stats["duplicates_removed"] = dup_count
    stats["output_records"] = sum(1 for r in all_records if not r.get("duplicate"))

    write_jsonl(all_records, out_dir / "reddit_cleaned.jsonl")
    logger.info(f"Reddit: {stats['input_records']} in → {stats['output_records']} out "
                f"({stats['flagged']} flagged, {stats['duplicates_removed']} dupes, "
                f"{stats['non_english']} non-English, {stats['comments_removed']} comments removed)")
    return stats


def run_web(config: dict) -> dict:
    raw_dir = RAW_DIR / "web"
    out_dir = CLEANED_DIR / "web"
    stats = {"input_records": 0, "output_records": 0, "flagged": 0, "non_english": 0,
             "duplicates_removed": 0}

    if not raw_dir.exists():
        logger.warning(f"Web raw dir not found: {raw_dir}")
        return stats

    all_records = []
    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        records = load_jsonl(jsonl_file)
        stats["input_records"] += len(records)
        for record in records:
            record = clean_web_record(record, min_length=config["web"]["min_article_chars"])
            if not record["is_english"]:
                stats["non_english"] += 1
            if record["flagged"]:
                stats["flagged"] += 1
            all_records.append(record)

    all_records, dup_count = minhash_dedup(all_records, "body")
    stats["duplicates_removed"] = dup_count
    stats["output_records"] = sum(1 for r in all_records if not r.get("duplicate"))

    write_jsonl(all_records, out_dir / "web_cleaned.jsonl")
    logger.info(f"Web: {stats['input_records']} in → {stats['output_records']} out "
                f"({stats['flagged']} flagged, {stats['duplicates_removed']} dupes, "
                f"{stats['non_english']} non-English)")
    return stats


def run_youtube(config: dict) -> dict:
    raw_dir = RAW_DIR / "youtube"
    out_dir = CLEANED_DIR / "youtube"
    stats = {"input_records": 0, "output_records": 0, "flagged": 0, "non_english": 0,
             "duplicates_removed": 0}

    if not raw_dir.exists():
        logger.warning(f"YouTube raw dir not found: {raw_dir}")
        return stats

    corrections = config.get("youtube", {}).get("term_corrections", {})

    all_records = []
    for jsonl_file in sorted(raw_dir.glob("*.jsonl")):
        records = load_jsonl(jsonl_file)
        stats["input_records"] += len(records)
        for record in records:
            record = clean_youtube_record(record, corrections, min_length=config["youtube"]["min_transcript_chars"])
            if not record["is_english"]:
                stats["non_english"] += 1
            if record["flagged"]:
                stats["flagged"] += 1
            all_records.append(record)

    all_records, dup_count = minhash_dedup(all_records, "transcript")
    stats["duplicates_removed"] = dup_count
    stats["output_records"] = sum(1 for r in all_records if not r.get("duplicate"))

    write_jsonl(all_records, out_dir / "youtube_cleaned.jsonl")
    logger.info(f"YouTube: {stats['input_records']} in → {stats['output_records']} out "
                f"({stats['flagged']} flagged, {stats['duplicates_removed']} dupes, "
                f"{stats['non_english']} non-English)")
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Coffee training data cleaning pipeline")
    parser.add_argument("--source", choices=["reddit", "web", "youtube"],
                        help="Clean only a specific source (default: all)")
    args = parser.parse_args()

    logging.basicConfig(
        format="[clean_pipeline] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )

    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        config = json.load(f)

    summary = {
        "cleaned_at": datetime.now(tz=timezone.utc).isoformat(),
        "reddit": {"input_records": 0, "output_records": 0, "flagged": 0,
                   "non_english": 0, "duplicates_removed": 0, "comments_removed": 0},
        "web": {"input_records": 0, "output_records": 0, "flagged": 0,
                "non_english": 0, "duplicates_removed": 0},
        "youtube": {"input_records": 0, "output_records": 0, "flagged": 0,
                    "non_english": 0, "duplicates_removed": 0},
    }

    if args.source in (None, "reddit"):
        summary["reddit"] = run_reddit(config)

    if args.source in (None, "web"):
        summary["web"] = run_web(config)

    if args.source in (None, "youtube"):
        summary["youtube"] = run_youtube(config)

    summary_path = CLEANED_DIR / "clean_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info(f"Clean summary written to {summary_path}")
    print(
        f"Cleaning complete — "
        f"Reddit: {summary['reddit']['output_records']} | "
        f"Web: {summary['web']['output_records']} | "
        f"YouTube: {summary['youtube']['output_records']}"
    )


if __name__ == "__main__":
    main()
