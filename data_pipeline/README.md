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

Output is written to `training_data/raw/` (gitignored):

```
training_data/raw/
├── reddit/
│   ├── Coffee.jsonl
│   ├── espresso.jsonl
│   ├── pourover.jsonl
│   └── CoffeePH.jsonl
├── web/
│   ├── barista_hustle.jsonl
│   ├── coffee_ad_astra.jsonl
│   └── perfect_daily_grind.jsonl
├── youtube/
│   ├── james_hoffmann.jsonl
│   └── lance_hedrick.jsonl
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
| `youtube.max_videos_per_channel` | 200 | Cap per YouTube channel |

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

### Reddit
Subreddits: `r/Coffee`, `r/espresso`, `r/pourover`, `r/CoffeePH`

Fetch strategy: `top` (year + all-time) and `hot`. Deduplication by post ID. Top 25 comments per post, 2 levels of replies.

### Web
- **Barista Hustle** (`baristahustle.com/blog/`) — science-forward coffee technique
- **Coffee Ad Astra** (`coffeeadastra.com`) — Jonathan Gagné's physics-of-coffee research
- **Perfect Daily Grind** (`perfectdailygrind.com`) — specialty coffee trade journalism

### YouTube
- **James Hoffmann** — specialty coffee educator (authority weight: 1.0)
- **Lance Hedrick** — espresso technique deep dives (authority weight: 0.8)

Transcripts are fetched via `youtube-transcript-api`. Prefers English, falls back to en-US/en-GB.
