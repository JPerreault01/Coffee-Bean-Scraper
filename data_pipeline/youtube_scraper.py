"""
YouTube transcript scraper.
Fetches video transcripts from coffee channels via yt-dlp subtitle download.
Uses yt-dlp to enumerate channel videos and fetch subtitles — no API key required.
"""

import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("youtube_scraper")

STATE_FILE = Path("training_data/state/youtube_state.json")


class TransientFetchError(Exception):
    """Raised when a transcript fetch fails due to a transient condition
    (IP block, network error) that may succeed on retry."""
    pass


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def setup_logging():
    logging.basicConfig(
        format="[youtube_scraper] [%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO,
        stream=sys.stdout,
    )


# --- State management ---

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "scraped_video_ids": [],
        "completed_channels": [],
        "in_progress": None,
        "last_run_at": None,
    }


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_domain_tags(text: str, config: dict) -> list[str]:
    text_lower = text.lower()
    return [tag for tag, keywords in config["domain_tags"].items()
            if any(kw.lower() in text_lower for kw in keywords)]


def compute_youtube_quality(transcript: str, channel_name: str, config: dict) -> float:
    ycfg = config["youtube"]
    qcfg = ycfg["quality"]
    tech_vocab = config["tech_vocabulary"]

    channel_cfg = ycfg["channels"].get(channel_name, {})
    authority = channel_cfg.get("authority_weight", ycfg["default_authority_weight"])

    length_score = min(len(transcript), qcfg["transcript_normalize_cap"]) / qcfg["transcript_normalize_cap"]

    text_lower = transcript.lower()
    tech_hits = sum(1 for term in tech_vocab if term.lower() in text_lower)
    keyword_score = min(tech_hits / 10, 1.0)

    quality = (
        length_score * qcfg["transcript_weight"]
        + keyword_score * qcfg["keyword_weight"]
        + authority * qcfg["authority_weight"]
    )
    return round(quality, 4)


def _parse_vtt(vtt_text: str) -> str:
    """Extract clean text from WebVTT subtitle format, deduplicating rolling captions."""
    lines = vtt_text.splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip header, NOTE blocks, numeric cue IDs, and timing lines
        if (line.startswith("WEBVTT") or line.startswith("NOTE")
                or "-->" in line or re.match(r"^\d+$", line)):
            continue
        # Strip inline tags like <00:00:01.000> and <c>...</c>
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            text_lines.append(line)

    # Deduplicate consecutive identical lines (rolling caption artifact)
    deduped = []
    for line in text_lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    return " ".join(deduped)


def fetch_transcript(video_id: str, lang_pref: list) -> Optional[str]:
    """Fetch transcript via yt-dlp subtitle download.

    Returns:
        str: transcript text if found
        None: video has no subtitles (permanent — do not retry)
    Raises:
        TransientFetchError: network/IP issue (transient — retry next run)
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp is not installed. Run: pip install yt-dlp")
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": lang_pref,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(tmpdir, "%(id)s"),
            "subtitlesformat": "vtt",
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            err = str(e).lower()
            if any(term in err for term in ["blocked", "http error 429",
                                             "too many requests", "network",
                                             "connection", "timeout"]):
                raise TransientFetchError(f"Transient error for {video_id}: {e}") from e
            # Non-network errors (private video, deleted, etc.) → permanent
            logger.debug(f"yt-dlp non-transient error for {video_id}: {e}")
            return None

        for lang in lang_pref:
            for suffix in [f".{lang}.vtt", f".{lang}-orig.vtt"]:
                sub_path = os.path.join(tmpdir, f"{video_id}{suffix}")
                if os.path.exists(sub_path):
                    try:
                        raw = open(sub_path, encoding="utf-8").read()
                        text = _parse_vtt(raw)
                        if text:
                            return text
                    except Exception as e:
                        logger.debug(f"VTT parse error for {video_id}: {e}")

    # yt-dlp ran cleanly but found no subtitle files → no captions available
    return None


def get_channel_video_ids(channel_id: str, channel_name: str, max_videos: int) -> list:
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp is not installed. Run: pip install yt-dlp")
        return []

    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "playlist_end": max_videos,
        "ignoreerrors": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception as e:
        logger.error(f"yt-dlp failed to fetch channel {channel_name}: {e}")
        return []

    if not info or "entries" not in info:
        logger.warning(f"No videos found for channel {channel_name} ({channel_id})")
        return []

    videos = []
    for entry in (info["entries"] or []):
        if not entry:
            continue
        video_id = entry.get("id")
        if not video_id:
            continue
        upload_date = entry.get("upload_date", "")
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        videos.append({
            "video_id": video_id,
            "title": entry.get("title", ""),
            "published_at": upload_date,
            "description": (entry.get("description") or "")[:500],
            "channel_name": channel_name,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(videos) >= max_videos:
            break

    return videos


def scrape_video(video_meta: dict, channel_name: str, config: dict, output_file) -> bool:
    ycfg = config["youtube"]
    lang_pref = ycfg["transcript_language_preference"]
    min_chars = ycfg["min_transcript_chars"]

    video_id = video_meta["video_id"]
    transcript = fetch_transcript(video_id, lang_pref)

    if not transcript:
        logger.debug(f"No transcript for video {video_id}")
        return False

    if len(transcript) < min_chars:
        logger.debug(f"Transcript too short ({len(transcript)} chars) for video {video_id}")
        return False

    domain_tags = get_domain_tags(
        video_meta.get("title", "") + " " + video_meta.get("description", "") + " " + transcript,
        config,
    )
    quality_score = compute_youtube_quality(transcript, channel_name, config)

    raw = {
        "video_id": video_id,
        "title": video_meta.get("title", ""),
        "channel_name": channel_name,
        "published_at": video_meta.get("published_at", ""),
        "description": video_meta.get("description", "")[:ycfg["description_max_chars"]],
        "transcript": transcript,
        "url": video_meta.get("url", f"https://www.youtube.com/watch?v={video_id}"),
    }

    envelope = {
        "source": "youtube",
        "content_type": "transcript",
        "domain_tags": domain_tags,
        "quality_score": quality_score,
        "raw": raw,
        "scraped_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    output_file.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    return True


def run(config: dict, video_id_override: Optional[str] = None, fresh: bool = False) -> dict:
    setup_logging()
    ycfg = config["youtube"]
    output_dir = Path(ycfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {"transcripts": 0, "by_channel": {}}

    # Single video mode (--video-id flag) — no checkpointing needed for one-off
    if video_id_override:
        logger.info(f"Single video mode: {video_id_override}")
        video_meta = {
            "video_id": video_id_override,
            "title": "",
            "published_at": "",
            "description": "",
            "channel_name": "manual",
            "url": f"https://www.youtube.com/watch?v={video_id_override}",
        }
        out_path = output_dir / "manual.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            success = scrape_video(video_meta, "manual", config, f)
        if success:
            summary["transcripts"] += 1
            summary["by_channel"]["manual"] = summary["by_channel"].get("manual", 0) + 1
            logger.info(f"Scraped transcript for video {video_id_override}")
        else:
            logger.warning(f"No transcript available for video {video_id_override}")
        print(f"YouTube complete: {summary['transcripts']} transcripts (manual)")
        return summary

    # Load or reset state
    state = {"scraped_video_ids": [], "completed_channels": [], "in_progress": None, "last_run_at": None}
    if not fresh:
        state = _load_state()
        if state.get("scraped_video_ids") or state.get("completed_channels"):
            logger.info(
                f"Resuming from checkpoint: {len(state['scraped_video_ids'])} videos already scraped, "
                f"{len(state['completed_channels'])} channels complete"
            )
    else:
        logger.info("--fresh flag set — ignoring existing state")

    scraped_ids_set: set[str] = set(state.get("scraped_video_ids", []))
    completed_channels: set[str] = set(state.get("completed_channels", []))

    for channel_name, channel_cfg in ycfg["channels"].items():
        if channel_name in completed_channels:
            logger.info(f"{channel_name}: already completed, skipping")
            continue

        channel_id = channel_cfg["channel_id"]
        max_videos = ycfg["max_videos_per_channel"]

        state["in_progress"] = channel_name
        state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
        _save_state(state)

        logger.info(f"Fetching video list for {channel_name} ({channel_id})...")
        videos = get_channel_video_ids(channel_id, channel_name, max_videos)
        logger.info(f"{channel_name}: {len(videos)} videos found, fetching transcripts...")

        out_path = output_dir / f"{channel_name}.jsonl"
        open_mode = "a" if out_path.exists() and not fresh else "w"
        channel_count = 0

        with open(out_path, open_mode, encoding="utf-8") as f:
            for video_meta in videos:
                video_id = video_meta.get("video_id", "")
                if video_id in scraped_ids_set:
                    logger.debug(f"Skipping already-scraped video {video_id}")
                    continue

                try:
                    success = scrape_video(video_meta, channel_name, config, f)
                    if success:
                        channel_count += 1

                    # Permanent outcome (success or confirmed no-captions) — safe to checkpoint
                    scraped_ids_set.add(video_id)
                    state["scraped_video_ids"] = list(scraped_ids_set)
                    state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
                    _save_state(state)

                except TransientFetchError as e:
                    # Do NOT checkpoint — transient failure, retry on next run
                    logger.warning(f"Transient failure for {video_id}, will retry: {e}")

                except Exception as e:
                    # Unexpected error — checkpoint to avoid infinite retries on broken videos
                    logger.error(f"Unexpected error for {video_id}: {e}")
                    scraped_ids_set.add(video_id)
                    state["scraped_video_ids"] = list(scraped_ids_set)
                    _save_state(state)

                sleep_secs = ycfg.get("sleep_between_videos_seconds", 3)
                time.sleep(sleep_secs)

        summary["by_channel"][channel_name] = channel_count
        summary["transcripts"] += channel_count
        logger.info(f"{channel_name}: {channel_count} transcripts written → {out_path}")

        completed_channels.add(channel_name)
        state["completed_channels"] = list(completed_channels)
        state["in_progress"] = None
        _save_state(state)

    by_channel_str = ", ".join(f"{k}: {v}" for k, v in summary["by_channel"].items())
    print(f"YouTube complete: {summary['transcripts']:,} transcripts ({by_channel_str})")
    return summary
