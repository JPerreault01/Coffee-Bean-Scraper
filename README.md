# Coffee Bean Index — Reviews, Price Tracking & Reference Data

The code behind **coffeebeanindex.com**: a custom WordPress publication for coffee
bean reviews, backed by Python scrapers, a ~14k-coffee reference corpus, AI-assisted
review drafting, and a daily price tracker.

> **New to this repo? Read [ARCHITECTURE.md](ARCHITECTURE.md) first.** It documents how
> the system actually works today, component by component. [PROJECT_STATUS.md](PROJECT_STATUS.md)
> tracks what is live, in-flight, and broken.

---

## What this repo actually contains

This is larger than a single scraper. There are five subsystems:

| Subsystem | Where | What it does |
|---|---|---|
| **Price tracker** | `scrapers/price_scraper.py`, `alerts/send_alerts.py`, `scrapers/db.py` | Daily price scrape (Playwright) → SQLite (`data/prices.db`) → Beehiiv price-drop alerts |
| **Reference corpus** | `scrapers/waytocoffee_scraper.py`, `scrapers/reference_db.py` | ~14k coffees scraped from thewaytocoffee.com into a normalized SQLite entity graph (`data/coffee_reference.db`) used for verified-spec enrichment |
| **Review generation** | `scrapers/generate_review.py` + `skills/coffee-review-writer/` | Builds a draft review from product specs + price history + reference specs, via the Claude/MiniMax API or the portable Agent Skill |
| **WordPress site** | `wordpress-plugins/coffeebeanindex-theme/` (+ plugins) | GeneratePress child theme: `bean` CPT, six taxonomies, ACF fields, schema, custom templates |
| **Training-data pipeline** | `data_pipeline/` | Collects Reddit/web/YouTube coffee content and distils it into the voice + knowledge that back the review skill |

The publish path from draft → live page runs through WP-CLI scripts in `scrapers/`
(`create_beans.php`, `push_drafts.php`, `set_featured_images.php`).

---

## Repo layout

```
Coffee-Bean-Scraper/
├── scrapers/                       Price scraper, reference DB, review generator, WP-CLI importers
│   ├── price_scraper.py            Daily price scrape → prices.db
│   ├── db.py                       Shared SQLite schema + connection (prices.db)
│   ├── products.json               Tracked-product catalog (source of truth, 20 products)
│   ├── sync_products.py            products.json → prices.db `products` table
│   ├── generate_review.py          AI review draft generator (Claude / MiniMax / --mock)
│   ├── reference_db.py             Normalized reference corpus (coffee_reference.db)
│   ├── waytocoffee_scraper.py      Reference-corpus scraper (~14k coffees)
│   ├── select_products.py          Pick reference beans worth promoting to reviews
│   ├── build_flavors_json.py       products.json → data/flavors.json (flavor-explorer plugin)
│   ├── fetch_bean_images.py        Resolve a product image per bean (PA-API → roaster → manual)
│   ├── create_beans.php            WP-CLI: create bean CPT posts from products.json (canonical)
│   ├── push_drafts.php             WP-CLI: parse draft .md → ACF fields on bean posts
│   ├── set_featured_images.php     WP-CLI: set featured images from the image manifest
│   ├── reformat_origin_descriptions.py  Reformat origin term descriptions to HTML
│   └── style_guide.txt             Review voice/style guide (loaded by generate_review.py)
├── alerts/
│   └── send_alerts.py              Price-drop detector → Beehiiv broadcast
├── data_pipeline/                  Training-data collection + voice/knowledge skill build
├── skills/coffee-review-writer/    Assembled Agent Skill (voice + knowledge + format)
├── seeds/                          WP-CLI seed scripts (taxonomy terms, nav, homepage, roundups)
├── wordpress-plugins/
│   ├── coffeebeanindex-theme/      GeneratePress child theme (the live front end)
│   ├── coffee-price-chart/         Chart.js price-history shortcode (reads prices.db)
│   ├── coffee-bean-profile/        Radar/profile shortcode (superseded by theme — see AUDIT_FINDINGS)
│   └── coffee-flavor-explorer/     Filterable grid shortcode (superseded by theme — see AUDIT_FINDINGS)
├── tests/                          Local scraper/DB smoke tests + seed data
├── notebooks/                      Fine-tuning experiment (exploratory)
├── ARCHITECTURE.md  PROJECT_STATUS.md  AUDIT_FINDINGS.md  CLAUDE.md
├── SEO_PLAYBOOK.md  PREPUBLISH_CHECKLIST.md  CONTENT_REFRESH.md
├── SETUP_LOCAL.md   SYNTHESIS_ARCHITECTURE.md
├── requirements.txt  setup.sh  .env.example  .gitignore
```

## Live stack

- **Host:** Ubuntu 24 VPS, Nginx + PHP 8.2. Connect via the `cbi-prod` SSH alias —
  server access, the non-root deploy user, and SSH hardening are documented in
  [DEPLOY.md](DEPLOY.md).
- **WordPress:** GeneratePress parent + `coffeebeanindex` child theme, ACF (free),
  RankMath, WP Rocket, WPForms, `coffee-price-chart` plugin.
- **Python:** scrapers in `/opt/scrapers/`, alerts in `/opt/alerts/`, venv at `/opt/venv`,
  SQLite + drafts in `/opt/data/` and `/opt/drafts/`.
- **Services:** Beehiiv (email), Claude + MiniMax (drafting), Cloudflare (DNS/CDN).

## Local development

See [SETUP_LOCAL.md](SETUP_LOCAL.md) for the Windows/PowerShell workflow. Quick version:

```powershell
python -m venv venv; venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python tests/seed_test_data.py        # fake 30-day price history
python scrapers/generate_review.py lavazza-super-crema --mock   # draft, no API key
```

Paths auto-detect: scripts use `/opt/...` when those paths exist (VPS) and fall back
to the repo working tree locally, so the same code runs in both places.

## Server setup & cron

`setup.sh <domain>` provisions a fresh VPS (Nginx, PHP 8.2, MariaDB, WordPress,
Python venv, Certbot, firewall). It installs the price-tracker cron:

```
0 6 * * *  /opt/venv/bin/python3 /opt/scrapers/price_scraper.py  >> /opt/data/scraper.log 2>&1
15 6 * * * /opt/venv/bin/python3 /opt/alerts/send_alerts.py      >> /opt/data/alerts.log 2>&1
```

> `setup.sh` predates the custom theme and the reference/skill subsystems — it stands up
> the price-tracker baseline only. The theme, plugins, ACF, and content are deployed
> separately (scp + `wp eval-file`). See [ARCHITECTURE.md](ARCHITECTURE.md) for the full
> deploy path.

## The two databases

Both are SQLite and both are gitignored. Rebuild from a scrape on a new machine.

- **`data/prices.db`** — price history, the `products` table, and the alert log.
  Schema lives in `scrapers/db.py`. Read by the `coffee-price-chart` plugin via PDO.
- **`data/coffee_reference.db`** — ~14k-coffee normalized reference corpus.
  Build: `python scrapers/waytocoffee_scraper.py --all` then
  `python scrapers/reference_db.py load data/waytocoffee.json`.

## Monetization

| Source | Rate | Network |
|---|---|---|
| Amazon Associates | 4% (grocery) | Amazon |
| Stumptown | ~10% | ShareASale |
| Trade Coffee | 10% + $5/sub | Impact |
| Blue Bottle | 10% | CJ Affiliate |
| Death Wish | 10% | ShareASale |

Every page with affiliate links must carry the FTC + AI disclosures — see
[PREPUBLISH_CHECKLIST.md](PREPUBLISH_CHECKLIST.md).
