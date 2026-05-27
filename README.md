# Coffee Bean Scraper

A niche affiliate website toolkit for tracking coffee bean prices and publishing AI-assisted reviews.

## What this does

- **Price tracking**: Scrapes Amazon (PA-API 5.0) and direct roaster websites daily
- **Price alerts**: Detects >10% price drops and notifies subscribers via Beehiiv
- **AI reviews**: Generates draft reviews using Claude or MiniMax, structured for SEO
- **WordPress plugin**: Embeds Chart.js price history charts via shortcode

## Repository structure

```
Coffee-Bean-Scraper/
├── scrapers/
│   ├── price_scraper.py       — Amazon PA-API + Playwright scraper
│   ├── generate_review.py     — AI draft generator
│   └── products.json          — product config (source of truth)
├── alerts/
│   └── send_alerts.py         — Beehiiv price drop alerts
├── wordpress-plugins/
│   └── coffee-price-chart/
│       ├── coffee-price-chart.php
│       └── README.md
├── .env.example               — env var template (copy to /opt/.env)
├── .gitignore
├── setup.sh                   — VPS setup script
└── README.md
```

## Quick start

### 1. VPS setup

```bash
bash setup.sh yourcoffeebeans.com
```

### 2. Configure environment

```bash
cp .env.example /opt/.env
nano /opt/.env  # fill in API keys
```

### 3. Deploy scrapers

```bash
cp -r scrapers /opt/scrapers
cp -r alerts /opt/alerts
```

### 4. Install Python dependencies

```bash
/opt/venv/bin/pip install requests playwright anthropic
/opt/venv/bin/python -m playwright install chromium
```

### 5. WordPress plugin

Copy `wordpress-plugins/coffee-price-chart/` to `/var/www/coffeebeans/wp-content/plugins/` and activate in WP Admin.

## Cron schedule

```
0 6 * * *  /opt/venv/bin/python3 /opt/scrapers/price_scraper.py
15 6 * * * /opt/venv/bin/python3 /opt/alerts/send_alerts.py
```

## Generating a review draft

```bash
/opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema
```

## Required API accounts

| Service | Purpose | URL |
|---|---|---|
| Amazon Associates + PA-API | Price data | affiliate-program.amazon.com |
| Beehiiv | Email alerts | beehiiv.com |
| Claude API | Review drafts | console.anthropic.com |
| MiniMax | Alternative LLM | minimaxi.com |

## Never commit

- `/opt/.env` — contains all API credentials
- `*.db` — SQLite price database
- `*.log` — scraper logs
- `/opt/drafts/` — AI-generated draft files
