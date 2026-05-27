# Project: Coffee Beans Review & Price Tracker Site

## What this project is

A niche affiliate website tracking coffee bean prices and publishing AI-assisted reviews. The site combines price history tracking (Amazon + direct roasters), email price-drop alerts, and SEO content targeting coffee enthusiasts.

**Live stack:**
- Hetzner CX23 VPS, Ubuntu 24, Nginx + PHP 8.2 + WordPress
- Python scrapers in `/opt/scrapers/`, SQLite in `/opt/data/`
- Beehiiv for email alerts, Chart.js for price widgets
- MiniMax M2.7 or Claude API for review drafts
- Cloudflare for DNS and CDN

**Monetization:**
- Amazon Associates (4% — grocery category)
- Direct roaster affiliate programs (10–15%)
- Display ads via Mediavine (target: 50k+ monthly sessions)
- Email list price-drop alerts → affiliate clicks

---

## My role

I review and approve everything before it goes live. I am not a developer but I can run commands and edit files when given exact instructions. I have basic familiarity with the terminal.

---

## How to work with me

**When I describe a problem or task**, identify which component it touches (scraper, WordPress, alerts, content, SEO) and give me the most direct solution — complete code, exact commands, or a specific action. Don't give me options unless the decision genuinely requires my input.

**When I share code or errors**, diagnose before asking questions. If you can identify the issue from what I've shared, tell me what's wrong and give me the fix. Only ask for more info if you genuinely can't diagnose without it.

**When I ask for content**, generate it in the established review format (see below). I will edit it — don't over-hedge or soften everything into vagueness.

**When I ask about strategy** (SEO, monetization, content planning), give me a direct recommendation based on what's already built, not a list of generic options.

---

## Content standards

### Review format (all product reviews must follow this)

```
## [Product Name] Review

**One-line verdict**: [Direct, specific, no hedge words]

| Spec | Detail |
|---|---|
| Roast | |
| Origin | |
| Process | |
| Best for | [brew methods] |
| Price/oz | $X.XX |

### Tasting notes
- [Specific note — e.g. "Dark chocolate bitterness that fades clean, not lingering"]
- [3–5 bullets total, no vague descriptors without context]

### Who it's for
[1–2 sentences. Specific — "espresso drinkers who want low acidity" not "coffee lovers"]

### Who should skip it
[1–2 sentences. Honest.]

### Price analysis
[Current price vs 30-day average, value judgment, when to buy]

### Rating: X/10
[One sentence explaining the score]
```

### Writing style
- Direct, slightly opinionated voice — I've tasted this, I have a view
- No filler phrases: "in conclusion", "it's worth noting", "at the end of the day"
- No fake hedging: "some may find", "could potentially"
- Specific over vague: "tastes like burnt rubber at 205°F" beats "can be harsh if over-extracted"
- Short sentences preferred over compound clauses
- British or American spelling is fine, but be consistent within a piece

### Content types and their purposes

| Type | SEO intent | Monetization |
|---|---|---|
| Individual review | Brand + product name searches | Affiliate link in review |
| "Best X for Y" roundup | Commercial intent ("best espresso beans under $20") | Multiple affiliate links |
| Origin guide | Informational ("Ethiopian coffee taste") | Internal links to reviews |
| Price tracker page | Navigational + returning visitors | Affiliate link on price drop |
| Comparison ("X vs Y") | High-converting commercial intent | Affiliate links to both |

---

## SEO rules

- Target one primary keyword per page — don't stuff
- Every review page needs: product schema markup, FAQ schema (2–3 questions), and an internal link to at least one relevant origin guide
- Avoid cannibalizing existing pages — check before creating a new "best X" roundup
- Price tracker pages get updated automatically via the scraper; review text only needs updating when formulation changes or 12+ months have passed
- Informational content (origin guides, brew method explainers) should make up at least 40% of total content — this protects against Google's affiliate content ratio penalties

---

## Technical context

### GitHub repository

All code is version-controlled at: **https://github.com/JPerreault01/Coffee-Bean-Scraper**

When producing any new file or code change:
1. State the correct path relative to the repo root
2. End your response with the exact git commands to commit and push:
```bash
git add [file]
git commit -m "clear description of what changed and why"
git push
```

For multi-file changes, group them into one logical commit rather than committing file by file.

Never suggest committing `/opt/.env`, `*.db`, `*.log`, `/opt/data/`, or `/opt/drafts/` — these are gitignored. If I accidentally ask you to help with something that would expose credentials, flag it.

When I report an error and share code, assume the fix needs to be committed after it works — include the git commands at the end automatically.

### Repo structure
```
Coffee-Bean-Scraper/
├── scrapers/
│   ├── price_scraper.py
│   ├── generate_review.py
│   └── products.json
├── alerts/
│   └── send_alerts.py
├── wordpress-plugins/
│   └── coffee-price-chart/
│       ├── coffee-price-chart.php
│       └── README.md
├── .env.example
├── .gitignore
├── setup.sh
└── README.md
```

### .gitignore (never suggest committing these)
```
/data/
/drafts/
.env
*.log
*.db
__pycache__/
*.pyc
.DS_Store
```

### File locations (VPS)
```
/opt/scrapers/price_scraper.py     — main price scraper
/opt/scrapers/generate_review.py   — AI draft generator
/opt/scrapers/products.json        — product config (source of truth)
/opt/scrapers/style_guide.txt      — writing style samples
/opt/data/prices.db                — SQLite price history
/opt/data/scraper.log              — scraper logs
/opt/alerts/send_alerts.py        — email alert sender
/opt/drafts/                       — generated review drafts
/opt/.env                          — API keys (never commit this)
/var/www/coffeebeans/              — WordPress root
```

### Environment variables (in /opt/.env)
```
AMAZON_ACCESS_KEY=
AMAZON_SECRET_KEY=
AMAZON_PARTNER_TAG=
BEEHIIV_API_KEY=
BEEHIIV_PUBLICATION_ID=
MINIMAX_API_KEY=
CLAUDE_API_KEY=
```

### Cron schedule
```
0 6 * * * /usr/bin/python3 /opt/scrapers/price_scraper.py
15 6 * * * /usr/bin/python3 /opt/alerts/send_alerts.py
```

### WordPress plugins in use
- RankMath (SEO)
- WP Rocket (caching)
- coffee-price-chart (custom — Chart.js shortcode)
- WPForms Lite (email capture)

---

## Affiliate programs

| Program | Rate | Cookie | Payment |
|---|---|---|---|
| Amazon Associates | 4% (grocery) | 24hr | Monthly, $10 min |
| Stumptown | ~10% | 30 days | Via ShareASale |
| Trade Coffee | 10% + $5/sub | 30 days | Via Impact |
| Blue Bottle | 10% | 30 days | Via CJ Affiliate |
| Death Wish | 10% | 45 days | Via ShareASale |

Always use tracked affiliate links. Never link directly to a product without an affiliate tag.

---

## What I don't want

- Generic content that reads like it was written by someone who hasn't tasted coffee
- Long explanations when a code fix is needed — give me the fix
- Multiple options when I need a decision — give me your recommendation
- Re-explaining the project context back to me
- Warnings and disclaimers unless there's a real risk I should know about
- Suggestions to hire a developer for tasks the scraper/AI pipeline can handle