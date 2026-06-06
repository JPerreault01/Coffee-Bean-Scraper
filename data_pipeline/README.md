# Coffee Training Data Pipeline

Collects training data from Reddit, specialty coffee websites, and YouTube for a coffee-specialized AI assistant. Data collection only — no embedding, chunking, or fine-tuning logic.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required for Reddit scraping:
- `REDDIT_CLIENT_ID` — from [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` — defaults to `coffee-pipeline/1.0`

Optional for YouTube (enables channel-level video enumeration):
- `YOUTUBE_API_KEY` — from [console.cloud.google.com](https://console.cloud.google.com), YouTube Data API v3

Load your environment before running:

```bash
export $(grep -v '^#' .env | xargs)
```

### 3. Output directories

Output is written to `training_data/raw/` (gitignored), one `.jsonl` per source.
The exact set of files mirrors the sources configured in `config.json` (see
**Data sources** below), e.g.:

```
training_data/raw/
├── reddit/      Coffee.jsonl, espresso.jsonl, JamesHoffmann.jsonl, … (9 subreddits)
├── web/         sprudge.jsonl, coffee_ad_astra.jsonl, perfect_daily_grind.jsonl, … (9 sites)
├── youtube/     james_hoffmann.jsonl, lance_hedrick.jsonl, … (7 channels)
├── podcasts/    (only if feeds are configured — none by default)
└── run_summary.json
```

## Usage

Run all scrapers:

```bash
python data_pipeline/run_pipeline.py
```

Run individual scrapers:

```bash
python data_pipeline/run_pipeline.py --reddit
python data_pipeline/run_pipeline.py --web
python data_pipeline/run_pipeline.py --youtube
```

Scrape a single YouTube video by ID (no API key required):

```bash
python data_pipeline/run_pipeline.py --youtube --video-id dQw4w9WgXcQ
```

## Output format

Every record uses a consistent envelope across all scrapers:

```json
{
  "source": "reddit|web|youtube",
  "content_type": "discussion|article|transcript",
  "domain_tags": ["espresso", "grinders"],
  "quality_score": 0.73,
  "raw": { ... },
  "scraped_at": "2026-01-01T06:00:00+00:00"
}
```

`domain_tags` and `quality_score` are populated at scrape time from heuristics defined in `config.json`.

## Configuration

All thresholds and filters live in `config.json`. No values are hardcoded in the scrapers.

Key settings:

| Setting | Default | Description |
|---|---|---|
| `reddit.min_score` | 50 | Minimum post score to include |
| `reddit.min_comments` | 10 | Minimum comment count |
| `reddit.max_comments_per_post` | 25 | Top N comments per post |
| `web.min_article_chars` | 500 | Minimum article length after cleaning |
| `web.request_delay_seconds` | 2 | Delay between web requests |
| `youtube.min_transcript_chars` | 300 | Minimum transcript length |
| `youtube.max_videos_per_channel` | 500 | Cap per YouTube channel |

## Run summary

After every run, `training_data/raw/run_summary.json` is written:

```json
{
  "run_at": "2026-01-01T06:00:00+00:00",
  "reddit": { "posts": 1847, "comments": 34291, "subreddits": {} },
  "web": { "articles": 412, "by_site": {} },
  "youtube": { "transcripts": 287, "by_channel": {} }
}
```

## Data sources

The authoritative list is `config.json` — update it there, not here. As configured today:

### Reddit (9 subreddits)
`Coffee`, `espresso`, `JamesHoffmann`, `pourover`, `barista`, `mokapot`, `coffeegeek`,
`Coffee_Reviews`, `HomeBarista`.

Fetch strategy: `top_year`, `top_all`, `hot`, `new`. Deduplication by post ID.
Per-subreddit comment caps and tiered comment extraction (more comments on bigger
threads). Uses the public Reddit API via `requests` (no PRAW); needs
`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`.

### Web (9 sites)
`sprudge`, `coffee_ad_astra`, `perfect_daily_grind`, `home_barista`,
`barista_hustle_pro`, `christopher_feran`, `scott_rao`, `coffeegeek`, `pull_and_pour`.
Scraped with Playwright + BeautifulSoup; WordPress and link-collection pagination
strategies per site.

### YouTube (7 channels)
`james_hoffmann` (1.0), `lance_hedrick` (0.8), `matt_perger` (0.9), `sprometheus` (0.8),
`coffee_chronicler` (0.9), `brian_quan` (0.8), `european_coffee_trip` (0.9)
— numbers are authority weights.

Transcripts and channel enumeration are fetched via **`yt-dlp`**. Prefers English,
falls back to en-US/en-GB. `YOUTUBE_API_KEY` is optional (enables API-based channel
enumeration); without it, `yt-dlp` handles discovery.

### Podcasts
Off by default — `config.json` ships with an empty `feeds` map. Add RSS feeds there to
enable; requires `feedparser`.

## Beyond collection: the skill build

This README covers data **collection**. The collected corpus then feeds the
voice + knowledge skill build:

```
clean_pipeline.py        raw/ → cleaned/ (dedup, language filter, boilerplate strip)
build_voice_profile.py   voice_materials/ → skill_data/voice/   (Tier 1, Claude)
build_skill_knowledge.py cleaned/ → skill_data/skill_knowledge.json (Tier 2, Claude)
assemble_skill.py        skill_data/ → skills/coffee-review-writer/ (final skill)
```

See [../SYNTHESIS_ARCHITECTURE.md](../SYNTHESIS_ARCHITECTURE.md) for how the two tiers
combine. `format_for_finetuning.py` and `notebooks/` are an exploratory fine-tuning
track that the skill approach superseded.
