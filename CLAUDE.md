# Project: Coffee Bean Index — Reviews & Price Tracker

## What this project is

A niche affiliate publication (**coffeebeanindex.com**) for coffee bean reviews, price
tracking, and email price-drop alerts. It combines a custom WordPress front end, Python
scrapers, a ~14k-coffee reference corpus, and AI-assisted review drafting.

**Live stack:**
- Ubuntu 24 VPS, Nginx + PHP 8.2 + WordPress
- WordPress: **GeneratePress** parent + **`coffeebeanindex`** child theme, **ACF (free)**,
  RankMath (SEO), WP Rocket (caching), WPForms (email capture), `coffee-price-chart` plugin
- Python scrapers in `/opt/scrapers/`, alerts in `/opt/alerts/`, venv at `/opt/venv`
- SQLite: `/opt/data/prices.db` (price history) and `coffee_reference.db` (reference corpus)
- Beehiiv for email alerts, Chart.js for the price widget
- Review drafts via **Claude (`claude-sonnet-4-6`)** or **MiniMax (`MiniMax-Text-01`)**;
  short-form/reformat tasks use `claude-haiku-4-5-20251001`
- Cloudflare for DNS and CDN

> For how the whole system fits together, read [ARCHITECTURE.md](ARCHITECTURE.md).
> For current progress and what's broken, read [PROJECT_STATUS.md](PROJECT_STATUS.md).

**Monetization:**
- Amazon Associates (4% — grocery category)
- Direct roaster affiliate programs (10–15%)
- Display ads via Mediavine (target: 50k+ monthly sessions)
- Email list price-drop alerts → affiliate clicks

---

## My role

I review and approve everything before it goes live. I am not a developer but I can run
commands and edit files when given exact instructions. I have basic familiarity with the
terminal.

---

## How to work with me

**When I describe a problem or task**, identify which subsystem it touches (price tracker,
reference corpus, review generation, WordPress/theme, or the training-data pipeline) and
give me the most direct solution — complete code, exact commands, or a specific action.
Don't give me options unless the decision genuinely requires my input.

**When I share code or errors**, diagnose before asking questions. If you can identify the
issue from what I've shared, tell me what's wrong and give me the fix. Only ask for more
info if you genuinely can't diagnose without it.

**When I ask for content**, generate it in the established review format and voice (below).
I will edit it — don't over-hedge or soften everything into vagueness.

**When I ask about strategy** (SEO, monetization, content planning), give me a direct
recommendation based on what's already built, not a list of generic options.

---

## Technical context

### GitHub repository

All code is version-controlled at **https://github.com/JPerreault01/Coffee-Bean-Scraper**

When producing any new file or code change:
1. State the correct path relative to the repo root.
2. End your response with the exact PowerShell git commands to commit and push:
```powershell
git add <file>
git commit -m "clear description of what changed and why"
git push
```
For multi-file changes, group them into one logical commit rather than committing file by file.

Never suggest committing `.env`, `*.db`, `*.log`, `/data/`, `/drafts/`, `training_data/`,
`skill_data/`, or `voice_materials/` — these are gitignored. If I accidentally ask for
something that would expose credentials, flag it. When I report an error and share code,
assume the fix needs to be committed after it works — include the git commands automatically.

### Repo structure

```
Coffee-Bean-Scraper/
├── scrapers/              price scraper, reference DB, review generator, WP-CLI importers
│   ├── price_scraper.py   db.py  sync_products.py  products.json  style_guide.txt
│   ├── generate_review.py reference_db.py  waytocoffee_scraper.py  select_products.py
│   ├── build_flavors_json.py  fetch_bean_images.py  reformat_origin_descriptions.py
│   ├── create_beans.php   push_drafts.php  set_featured_images.php   (WP-CLI)
│   └── write_review.py    market_research.py  repurpose.py           (ECC-skill variants)
├── alerts/send_alerts.py
├── data_pipeline/         training-data collection + voice/knowledge skill build
├── skills/coffee-review-writer/   assembled Agent Skill (voice + knowledge + format)
├── seeds/                 WP-CLI seed scripts (terms, nav, homepage, roundups)
├── wordpress-plugins/
│   ├── coffeebeanindex-theme/     GeneratePress child theme (the live front end)
│   ├── coffee-price-chart/        Chart.js price-history shortcode (reads prices.db)
│   ├── coffee-bean-profile/       (superseded by theme — see AUDIT_FINDINGS.md)
│   └── coffee-flavor-explorer/    (superseded by theme — see AUDIT_FINDINGS.md)
├── tests/                 local scraper/DB smoke tests + seed data
├── ARCHITECTURE.md  PROJECT_STATUS.md  AUDIT_FINDINGS.md  CLAUDE.md
├── SEO_PLAYBOOK.md  PREPUBLISH_CHECKLIST.md  CONTENT_REFRESH.md
├── SETUP_LOCAL.md   SYNTHESIS_ARCHITECTURE.md  README.md
├── requirements.txt  setup.sh  .env.example  .gitignore
```

### .gitignore (never suggest committing these)
```
/data/*  (except .gitkeep)   /drafts/   .env   *.log   *.db   __pycache__/   *.pyc
training_data/{raw,cleaned,processed,state,finetune}/   skill_data/   voice_materials/*
.tmp-shots/   scrapers/.image-cache/   data/*.json
```

### File locations (VPS)
```
/opt/scrapers/price_scraper.py     — main price scraper
/opt/scrapers/generate_review.py   — AI draft generator
/opt/scrapers/products.json        — product config (source of truth)
/opt/scrapers/style_guide.txt      — writing style samples
/opt/scrapers/reference_db.py      — reference corpus CLI
/opt/data/prices.db                — SQLite price history
/opt/data/coffee_reference.db      — ~14k-coffee reference corpus
/opt/data/scraper.log              — scraper logs
/opt/alerts/send_alerts.py         — email alert sender
/opt/drafts/                       — generated review drafts
/opt/.env                          — API keys (never commit this)
/var/www/coffeebeans/              — WordPress root
```

### Environment variables (in /opt/.env)
```
AMAZON_ACCESS_KEY=  AMAZON_SECRET_KEY=  AMAZON_PARTNER_TAG=
BEEHIIV_API_KEY=    BEEHIIV_PUBLICATION_ID=
MINIMAX_API_KEY=    CLAUDE_API_KEY=     YOUTUBE_API_KEY=  (optional, pipeline)
REDDIT_CLIENT_ID=   REDDIT_CLIENT_SECRET=                 (optional, pipeline)
```

### Cron schedule
```
0 6 * * *  /opt/venv/bin/python3 /opt/scrapers/price_scraper.py >> /opt/data/scraper.log 2>&1
15 6 * * * /opt/venv/bin/python3 /opt/alerts/send_alerts.py     >> /opt/data/alerts.log 2>&1
```
`sync_products.py` is **not** in cron — run it manually after editing `products.json`.

### WordPress: content model & publish path

- **`bean` custom post type** = one reviewed coffee. Six taxonomies: `flavor-note`,
  `origin`, `roast-level`, `process-method`, `brew-method`, `roaster`.
- **ACF field group** `group_bean_specs` holds verdict, rating, tasting notes, who-for /
  who-skip, price analysis, sensory 1–5 scores, specs, affiliate URLs, and `product_id`
  (links a post to `prices.db`).
- **Publish path:** seed terms (`seeds/*.php`) → `create_beans.php` (create draft beans) →
  `generate_review.py` (write draft .md) → `push_drafts.php` (parse drafts into ACF +
  RankMath meta) → `fetch_bean_images.py` + `set_featured_images.php` → human Publish.
  `create_beans.php` is the canonical importer (the older `create_beans_wpcli.sh` was
  removed in the June 2026 audit — see AUDIT_FINDINGS.md §R2).
- **Deploy** is manual: `scp` theme/plugin files to the VPS, then `wp cache flush`. There
  is no CI deploy. `setup.sh` provisions only the price-tracker baseline. Connect via the
  `cbi-prod` SSH alias — server-access + hardening runbook in [DEPLOY.md](DEPLOY.md).

### Databases

- `prices.db` — `price_history`, `products`, `alert_log`. Schema in `scrapers/db.py`.
  Read by the `coffee-price-chart` plugin via PDO. Currently holds only seed data.
- `coffee_reference.db` — normalized ~14k-coffee corpus. Built and complete. Used by
  `generate_review.py` for verified-spec enrichment.

---

## Content standards

### Required site disclosures — DO NOT REMOVE OR MODIFY

These three disclosures are non-negotiable. No review, roundup, or guide may be published
without the appropriate disclosure in place.

1. **Methodology** (About/Editorial Standards page, referenced in footer):
   > "Reviews are generated using structured product data, public tasting notes, roast
   > information, and editorial evaluation criteria. Unless explicitly marked as personal
   > reviews, content should be understood as analytical commentary rather than firsthand
   > consumption experience."

2. **Affiliate** (near the top of every page with affiliate links, not only the footer):
   > "This page contains affiliate links. We may earn commissions from qualifying purchases."

3. **AI** (sitewide footer / About):
   > "Some content on this site is generated or assisted by AI systems using structured
   > product and review data."

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

### Rating: X.X/10
[One sentence explaining the score. Use a DECIMAL (e.g. 7.3) chosen against the
anchored rubric. The score is decided last, after the "Who should skip it" critique.]
```

> **Scoring is governed by an anchored rubric, not a free-form 1-10.** Score bands,
> the decimal mandate, the "score last" rule, the comparative rationale ledger, and
> the external-critic sanity check are all documented in
> [CLAUDE_content_standards_section.md](CLAUDE_content_standards_section.md). That
> file is the source of truth for how a bean is scored.

---

## Review voice system — HARD RULES

Every review is generated in one of two voice modes. These rules are non-negotiable and
apply to all AI-generated content on this site. The reader should not be able to tell which
mode they're reading based on confidence level — **only the presence or absence of "I"
language differs.**

### Default mode: Analytical voice
Used for all products unless `--personal` is passed to `generate_review.py`.

- NEVER write "I tried/brewed/tasted/found" or any first-person consumption claim for the
  product being reviewed.
- NEVER write "buyers say", "verified buyers report", "reviewers report", "customers note",
  "users find", or any crowd attribution. When referencing external opinion, use only
  "publicly available customer feedback", "published customer reviews", or "aggregated
  public review data".
- State what the coffee IS and DOES. The coffee is the subject, not a person.
- Second person ("you get", "you'll find") is allowed.
- Apply the site's standing preferences (below) as the critical lens — that is established
  voice, not a consumption claim.
- Confidence is absolute. No "may", "might", "could", "tends to", "can be".
- NEVER generate brew logs, ownership-duration claims, tasting-session descriptions,
  comparative testing histories, or exact workflow accounts in analytical mode.
- Frame absolute performance as tendency unless `--personal`: "Long extractions lose
  clarity fast" (safe), not "Every long extraction goes muddy" (risky).

Good: "The finish is clean. No linger." · "Long extractions lose clarity fast." · "Best
suited for filter brewing." · "You get dark chocolate up front, then a clean caramel fade."
Bad: "I found the finish clean." · "Buyers report it turns acrid." · "Some may find this too
intense." · "It could potentially work for espresso."

### Personal mode: `--personal` flag
Used only for products the site owner has personally tried.

- Unlocks first-person ("I", "my", "I've") for direct consumption claims about this product,
  absolute experiential statements ("Every long extraction goes muddy"), brew logs, and
  workflow histories.
- Does NOT change: confidence level (still absolute), sentence structure (short,
  declarative), the standing preferences, the ban on hedging, the analytical framing of
  price/value/specs, or the ban on fabricated data.

### Site's standing preferences (apply in both modes)
- Clean finishes over lingering bitterness
- Forgiving brew profiles over finicky ones
- Value-driven pricing over brand premiums
- Bright, defined flavors over muddy complexity
- Aggressive, high-intensity roasts are not early-morning coffees
- Espresso that works without a $2,000 machine is worth more than espresso that doesn't

### Writing style — HARD RULES
- Direct, confident voice. No softening, no flattery.
- No filler: "in conclusion", "it's worth noting", "at the end of the day", "overall".
- No fake hedging: "some may find", "could potentially", "tends to", "can be".
- Specific over vague: "turns acrid past 205°F" beats "can be harsh if over-extracted".
- Short sentences over compound clauses.
- No producer puffery — never repeat marketing language uncritically.
- British or American spelling is fine, but be consistent within a piece.
- **No em-dashes (—) or en-dashes (–) anywhere in output.** Use a period, comma, colon, or
  parentheses. This is enforced in the prompt and by `strip_dashes()`.
- No fabricated data: sensory scores, prices, origins must match verifiable specs. If
  unsure, leave the field blank rather than guess.

---

## SEO rules

The standing SEO operating doc is [SEO_PLAYBOOK.md](SEO_PLAYBOOK.md); the pre-publish gate
is [PREPUBLISH_CHECKLIST.md](PREPUBLISH_CHECKLIST.md); refresh cadence is
[CONTENT_REFRESH.md](CONTENT_REFRESH.md). Core rules:

- Target one primary keyword per page — don't stuff.
- Every review page needs Product + Review + AggregateRating + Offer + BreadcrumbList +
  FAQPage schema (auto-generated by the theme when ACF fields are filled), and an internal
  link to ≥1 origin guide and ≥1 roast-level guide.
- Meta title format for reviews: `[Product] Review — [Roaster] | Coffee Bean Index`.
- Avoid cannibalizing existing pages — check before creating a new "best X" roundup.
- Price tracker data updates via the scraper; review text updates only on formulation
  change or 12+ months.
- Informational content (origin guides, brew explainers) should be ≥40% of total content
  to protect against affiliate-ratio penalties.

### Content types and their purposes

| Type | SEO intent | Monetization | Template |
|---|---|---|---|
| Individual review | Brand + product name searches | Affiliate link in review | `single-bean.php` |
| "Best X for Y" roundup | Commercial ("best espresso beans under $20") | Multiple affiliate links | `template-roundup.php` |
| Origin guide | Informational ("Ethiopian coffee taste") | Internal links to reviews | `template-guide.php` |
| Price tracker | Navigational + returning visitors | Affiliate link on price drop | bean page widget |
| Comparison ("X vs Y") | High-converting commercial | Affiliate links to both | `template-comparison.php` |

### First 10 pages to publish (priority order)
1. Lavazza Super Crema review · 2. Best Espresso Beans Under $20 roundup · 3. Illy Classico
review · 4. Ethiopian Coffee taste guide · 5. Death Wish Coffee review · 6. Best Dark Roast
Coffee Beans roundup · 7. Stumptown Hair Bender review · 8. French Press Coffee Beans guide ·
9. Peet's Major Dickason's review · 10. Blue Bottle Hayes Valley review

---

## Affiliate programs

| Program | Rate | Cookie | Payment |
|---|---|---|---|
| Amazon Associates | 4% (grocery) | 24hr | Monthly, $10 min |
| Stumptown | ~10% | 30 days | ShareASale |
| Trade Coffee | 10% + $5/sub | 30 days | Impact |
| Blue Bottle | 10% | 30 days | CJ Affiliate |
| Death Wish | 10% | 45 days | ShareASale |

Always use tracked affiliate links. Never link directly to a product without an affiliate tag.

---

## What I don't want

- Generic content that reads like it was written by someone who hasn't tasted coffee
- Long explanations when a code fix is needed — give me the fix
- Multiple options when I need a decision — give me your recommendation
- Re-explaining the project context back to me
- Warnings and disclaimers unless there's a real risk I should know about
- Suggestions to hire a developer for tasks the scraper/AI pipeline can handle
