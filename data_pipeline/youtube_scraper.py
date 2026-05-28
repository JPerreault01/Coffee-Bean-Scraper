"""
YouTube transcript scraper.
Fetches video transcripts from coffee channels via youtube-transcript-api.
Optional: uses YouTube Data API v3 to enumerate channel videos if YOUTUBE_API_KEY is set.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

logger = logging.getLogger("youtube_scraper")

STATE_FILE = Path("training_data/state/youtube_state.json")


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


def clean_transcript(raw_parts: list[dict]) -> str:
    """Join transcript segments and remove auto-caption artifacts."""
    text = " ".join(part.get("text", "") for part in raw_parts)
    # Remove text in square brackets: [Music], [Applause], [Laughter], [Inaudible], [CC], etc.
    text = re.sub(r"\[.*?\]", "", text)
    # Remove filler transcription artifacts as standalone words
    text = re.sub(r"\b(um|uh|hmm)\b", "", text, flags=re.IGNORECASE)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_transcript(video_id: str, language_preference: list[str]) -> Optional[str]:
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        for lang in language_preference:
            try:
                transcript = transcript_list.find_transcript([lang])
                parts = transcript.fetch()
                return clean_transcript(parts)
            except NoTranscriptFound:
                continue

        # Fall back to any available transcript and translate
        try:
            transcript = transcript_list.find_generated_transcript(language_preference)
            parts = transcript.fetch()
            return clean_transcript(parts)
        except Exception:
            pass

    except TranscriptsDisabled:
        logger.debug(f"Transcripts disabled for video {video_id}")
    except NoTranscriptFound:
        logger.debug(f"No transcript found for video {video_id}")
    except Exception as e:
        logger.warning(f"Error fetching transcript for video {video_id}: {e}")

    return None


def get_channel_video_ids(channel_id: str, channel_name: str, max_videos: int, api_key: str) -> list[dict]:
    """Use YouTube Data API v3 to list all videos from a channel's uploads playlist."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        logger.error("google-api-python-client is not installed. Run: pip install google-api-python-client")
        return []

    try:
        youtube = build("youtube", "v3", developerKey=api_key)

        channels_resp = youtube.channels().list(
            part="contentDetails",
            id=channel_id,
        ).execute()

        items = channels_resp.get("items", [])
        if not items:
            logger.warning(f"No channel found for ID {channel_id}")
            return []

        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        videos = []
        next_page_token = None

        while len(videos) < max_videos:
            try:
                playlist_resp = youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_playlist_id,
                    maxResults=min(50, max_videos - len(videos)),
                    pageToken=next_page_token,
                ).execute()
            except HttpError as e:
                logger.error(f"YouTube API error listing playlist for {channel_name}: {e}")
                break

            for item in playlist_resp.get("items", []):
                snippet = item.get("snippet", {})
                video_id = snippet.get("resourceId", {}).get("videoId")
                if not video_id:
                    continue
                videos.append({
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", "")[:500],
                    "channel_name": channel_name,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                })

            next_page_token = playlist_resp.get("nextPageToken")
            if not next_page_token:
                break

        return videos

    except Exception as e:
        logger.error(f"Unexpected error fetching video list for {channel_name}: {e}")
        return []


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

    api_key = os.environ.get("YOUTUBE_API_KEY")
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

    if not api_key:
        logger.warning(
            "YOUTUBE_API_KEY is not set — skipping channel-level video fetching. "
            "Use --video-id <id> to scrape individual videos."
        )
        print("YouTube complete: 0 transcripts (no API key)")
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
        videos = get_channel_video_ids(channel_id, channel_name, max_videos, api_key)
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

                    # Update state after each video (success or skip)
                    scraped_ids_set.add(video_id)
                    state["scraped_video_ids"] = list(scraped_ids_set)
                    state["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
                    _save_state(state)

                except Exception as e:
                    logger.error(f"Error processing video {video_meta.get('video_id', '?')}: {e}")

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
