# Coffee Beans Price Tracker & Review Site

A niche affiliate website combining price tracking, AI-assisted reviews, and email price-drop alerts for coffee beans.

## What this repo contains

```
Coffee-Bean-Scraper/
├── scrapers/
│   ├── price_scraper.py      — Fetches prices from Amazon PA-API + roaster sites
│   ├── generate_review.py    — Generates AI review drafts via Claude or MiniMax
│   └── products.json         — 20-product starter catalog
├── alerts/
│   └── send_alerts.py        — Detects price drops and sends Beehiiv email alerts
├── wordpress-plugins/
│   └── coffee-price-chart/
│       ├── coffee-price-chart.php  — WP plugin: Chart.js price history widget
│       └── README.md
├── .env.example              — Environment variable template (copy to /opt/.env)
├── .gitignore
├── setup.sh                  — Full VPS setup script (Ubuntu 24)
└── README.md
```

## Quick start

### 1. Server setup

```bash
# On a fresh Ubuntu 24 Hetzner VPS, as root:
bash setup.sh yourcoffeebeans.com
```

This installs Nginx, PHP 8.2, MariaDB, WordPress, Certbot, Python 3, and creates all required directories.

### 2. Configure environment variables

```bash
cp .env.example /opt/.env
nano /opt/.env   # fill in your API keys
```

Required keys:
- `AMAZON_ACCESS_KEY` + `AMAZON_SECRET_KEY` + `AMAZON_PARTNER_TAG` — Amazon PA-API
- `BEEHIIV_API_KEY` + `BEEHIIV_PUBLICATION_ID` — Email alerts
- `CLAUDE_API_KEY` or `MINIMAX_API_KEY` — Review generation

### 3. Deploy scrapers

```bash
cp scrapers/price_scraper.py /opt/scrapers/
cp scrapers/generate_review.py /opt/scrapers/
cp scrapers/products.json /opt/scrapers/
cp alerts/send_alerts.py /opt/alerts/
```

### 4. Install Python dependencies

```bash
/opt/venv/bin/pip install requests playwright anthropic
/opt/venv/bin/python -m playwright install chromium
```

### 5. Install the WordPress plugin

```bash
cp -r wordpress-plugins/coffee-price-chart/ /var/www/coffeebeans/wp-content/plugins/
```

Then activate it in WordPress Admin → Plugins.

## Cron schedule

```
0 6 * * *  /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1
15 6 * * * /opt/venv/bin/python3 /opt/alerts/send_alerts.py >> /opt/data/alerts.log 2>&1
```

(The `setup.sh` script writes these to `/etc/cron.d/coffeebeans` automatically.)

## Usage

### Run the price scraper manually

```bash
/opt/venv/bin/python3 /opt/scrapers/price_scraper.py
```

### Generate a review draft

```bash
/opt/venv/bin/python3 /opt/scrapers/generate_review.py lavazza-super-crema
# Saves draft to /opt/drafts/lavazza-super-crema-YYYY-MM-DD.md
```

### Embed a price chart in WordPress

Add this shortcode to any post or page:

```
[coffee_price_chart product_id="lavazza-super-crema"]
```

## What is NOT in this repo

- `/opt/data/` — SQLite database and logs (gitignored)
- `/opt/drafts/` — AI-generated review drafts (gitignored)
- `/opt/.env` — API keys (gitignored — use `.env.example` as template)

## Monetization

| Source | Rate |
|---|---|
| Amazon Associates | 4% (grocery) |
| Stumptown affiliate | ~10% (via ShareASale) |
| Trade Coffee | 10% + $5/subscription |
| Blue Bottle | 10% (via CJ Affiliate) |
| Death Wish | 10% (via ShareASale) |
