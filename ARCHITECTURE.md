# Architecture — Coffee Bean Index

How the system actually works as of this audit (June 2026). This describes the **real
state of the code**, not the original plan. Where the live behaviour differs from older
docs, this file is the source of truth; see [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) for the
contradictions that were found and resolved.

---

## 1. The five subsystems

The repo is not one scraper. It is five loosely-coupled subsystems that share
`scrapers/products.json` as the common product catalog:

```
                         ┌─────────────────────────┐
                         │  scrapers/products.json  │  ← catalog (20 products, source of truth)
                         └────────────┬────────────┘
            ┌─────────────┬───────────┼────────────────┬──────────────────┐
            ▼             ▼           ▼                ▼                  ▼
   ┌──────────────┐ ┌──────────┐ ┌──────────────┐ ┌────────────┐ ┌────────────────┐
   │ PRICE TRACKER│ │ REFERENCE│ │   REVIEW     │ │  WORDPRESS │ │ TRAINING-DATA  │
   │              │ │  CORPUS  │ │ GENERATION   │ │   SITE     │ │   PIPELINE     │
   └──────────────┘ └──────────┘ └──────────────┘ └────────────┘ └────────────────┘
```

1. **Price tracker** — daily price scrape → SQLite → email alerts.
2. **Reference corpus** — ~14k coffees scraped once into a normalized entity graph.
3. **Review generation** — product specs + price history + reference specs → AI draft.
4. **WordPress site** — the GeneratePress child theme that renders everything.
5. **Training-data pipeline** — builds the voice/knowledge that backs the review skill.

Subsystems 1–4 are the product. Subsystem 5 is an upstream tooling pipeline that
produces the `coffee-review-writer` skill.

---

## 2. Subsystem 1 — Price tracker

### Data flow

```
products.json ──► price_scraper.py ──► prices.db (price_history) ──► send_alerts.py ──► Beehiiv
                  (Playwright)          (SQLite)                       (>10% drop)        (broadcast)
                                            ▲
                                            └── coffee-price-chart plugin reads it (PDO) on bean pages
```

### Components

- **`scrapers/price_scraper.py`** — iterates `products.json`, scrapes each product's
  Amazon page (by ASIN) or roaster URL with Playwright/Chromium, parses the price from a
  prioritized selector list, and inserts a `price_history` row. Random 3–8s delays between
  requests; per-product failures are logged and skipped, not fatal.
- **`scrapers/db.py`** — single source of the price schema (`price_history`, `products`,
  `alert_log`) and `get_connection()`. Auto-detects VPS vs local DB path: uses
  `/opt/data/prices.db` if `/opt` paths exist, else `data/prices.db` in the repo. Runs
  `init_db()` (idempotent `CREATE TABLE IF NOT EXISTS` + a small ALTER migration for the
  flavor-vector columns) on every connection.
- **`alerts/send_alerts.py`** — for each product, compares the latest price to the
  7-day average (excluding the latest row). On a drop ≥ `DROP_THRESHOLD` (10%) it sends a
  Beehiiv broadcast and records it in `alert_log` (deduped per price/day).
- **`scrapers/sync_products.py`** — upserts `products.json` into the `products` table.
  Independent of price scraping; safe to re-run.

### Schema (`data/prices.db`)

| Table | Purpose |
|---|---|
| `price_history` | one row per product per scrape (`price`, `price_per_oz`, `source`, `checked_at`) |
| `products` | denormalized copy of `products.json` for plugins/queries (populated by `sync_products.py`) |
| `alert_log` | sent price-drop alerts, for dedup |

### Automation

- **Automated (cron):** `price_scraper.py` at 06:00, `send_alerts.py` at 06:15 (see
  `setup.sh`). Both append to logs under `/opt/data/`.
- **Manual / not in cron:** `sync_products.py` (run after editing `products.json`).

### Known operational reality

The Amazon path **mostly fails** — the last live run logged 6 successes / 14 failures
("Could not find price"), because Amazon serves anti-bot pages to headless Chromium. The
only rows currently in `prices.db` are `source='seed'` test rows. The price chart and
homepage price strip therefore have no real data yet. See [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §P1.

---

## 3. Subsystem 2 — Reference corpus

A one-time (re-runnable) scrape of thewaytocoffee.com into a normalized SQLite entity
graph, used to enrich reviews with verified specs and to back the site's flavor/origin
entities.

```
waytocoffee_scraper.py ──► data/waytocoffee.json ──► reference_db.py load ──► coffee_reference.db
   (Playwright, 2-phase,        (~13MB)                                          (normalized)
    resumable, checkpoints)
```

### Components

- **`scrapers/waytocoffee_scraper.py`** — phase 1 collects listing URLs; phase 2 scrapes
  each detail page (origin, flavor notes, roast, processing, typology, roaster, buy URL).
  Resumable via `data/waytocoffee_stubs.json` + checkpointed output. `--pages N` /
  `--all` / `--roast`.
- **`scrapers/reference_db.py`** — loads the JSON into a normalized schema and exposes a
  CLI: `load`, `specs <slug>`, `find "<name>"`, `map products.json` (fuzzy-suggests a
  `reference_slug` for each tracked product).
- **`scrapers/select_products.py`** — filters/ranks reference beans worth promoting to
  full reviews, writing `data/promotion_candidates.json`.

### Schema (`data/coffee_reference.db`)

`roasters`, `coffees`, and the entity tables `origins` / `flavor_notes` / `processing` /
`varietals`, joined through `coffee_origins`, `coffee_flavor_notes`, `coffee_processing`,
`coffee_varietals`. Currently populated: **14,386 coffees, 1,033 roasters,
~3,600 flavor notes, ~2,300 origins.** This subsystem is built and complete.

### Connection to reviews

`generate_review.py` calls `reference_block()` → `reference_db.get_specs()`. If a product
has a `reference_slug` it uses it; otherwise it fuzzy-matches by name (`find_coffee`,
threshold 0.6). The verified specs are injected into the prompt as a "do not invent" block.
**All 20 products currently have `reference_slug: null`**, so matching is fuzzy-only.

---

## 4. Subsystem 3 — Review generation

Two interchangeable producers of the same review format. They are **not** wired together
into one pipeline; each is invoked independently.

### A. `scrapers/generate_review.py` (the programmatic generator)

```
products.json + prices.db (30-day history) + coffee_reference.db (verified specs)
        │
        ├─ build_prompt()  → style guide + voice mode + content-diversity rules
        │                     + SEO scaffolding (meta block, internal links, disclosure)
        ▼
   Claude (claude-sonnet-4-6) OR MiniMax (MiniMax-Text-01) OR --mock
        │
        ▼
   strip_dashes() ──► /opt/drafts/<id>-YYYY-MM-DD.md
```

- Voice modes: **analytical** (default) and **`--personal`** (unlocks first-person).
- `--mock` produces a deterministic draft with no API call (used by local testing).
- Emits a `<!--META ... -->` block and an `### Explore further` internal-links block that
  `push_drafts.php` later parses into RankMath fields and post content.
- Site rule: no em/en-dashes — enforced in the prompt and by `strip_dashes()`.
- Path resolution mirrors the rest of the repo (`/opt/...` if present, else repo tree).

### B. `skills/coffee-review-writer/` (the Agent Skill)

A portable Claude skill (built by subsystem 5) encoding the extracted voice, curated
knowledge, and review format. Used interactively (Claude Code / desktop / API) rather than
from a script. `SKILL.md` directs Claude to load `voice/`, `knowledge/`, and an exemplar
before drafting. This is the strategic direction for content; `generate_review.py` is the
batch/programmatic path.

### Auxiliary generators (`scrapers/`)

`write_review.py`, `market_research.py`, `repurpose.py` each fetch an **external** "ECC"
skill from `github.com/affaan-m/ECC` at runtime (cached in `.cache/`) and call Claude
(Haiku/Sonnet) for, respectively, a full review, a price-analysis paragraph, and
email/social repurposing. They overlap with the two producers above and depend on a
third-party repo — see [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §R3.

---

## 5. Subsystem 4 — WordPress site

The live front end is the **`coffeebeanindex` GeneratePress child theme**, not a set of
loose plugins. This is the single biggest divergence from the original plan.

### Content model

- **`bean` custom post type** (`functions.php` §2) — one post per reviewed coffee.
- **Six taxonomies** (`functions.php` §3): `flavor-note`, `origin`, `roast-level`,
  `process-method`, `brew-method`, `roaster`. Rewrite bases: `/flavor/`, `/origin/`,
  `/roast/`, `/process/`, `/brew/`, `/roaster/`.
- **ACF field group** (`acf-json/group_bean_specs.json`, ACF-free types only): verdict,
  rating, tasting_notes, whos_for, whos_not_for, price_analysis, sensory 1–5 scores,
  specs, affiliate URLs, `product_id` (links a post to `prices.db`), etc.

### Templates (`THEME.md` has the full map)

`front-page.php`, `single-bean.php`, `archive-bean.php`, `taxonomy-bean-archive.php`,
`template-roundup.php`, `template-comparison.php`, `template-guide.php`, `page.php`,
`single.php`. The theme owns its layout end-to-end via a `body_class` + CSS "layout
contract" that overrides GeneratePress's flex row (documented in `THEME.md`).

### Schema / SEO

`functions.php` emits JSON-LD directly: Product + Review + AggregateRating + Offer +
BreadcrumbList + FAQPage on bean pages, Organization + WebSite site-wide, ItemList on
taxonomy archives. RankMath also runs — there is a documented Product/Article duplication
risk to check (`THEME.md` §SEO, `DEPLOY_NOTES.md` §8).

### Supporting plugins

- **`coffee-price-chart`** (active) — `[coffee_price_chart product_id="…"]` renders a
  Chart.js price history by reading `/opt/data/prices.db` directly via PDO. This is the
  live bridge from the price DB to the page.
- **`coffee-bean-profile`**, **`coffee-flavor-explorer`** — radar/profile and filterable
  grid shortcodes. The theme now renders these natively (`single-bean.php` radar + sensory
  bars + similar beans; `page-explore.php` + `explore-filters.js` for the grid), so these
  two plugins appear superseded. See [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §R4.

### Publish path (draft → live page)

This is a chain of WP-CLI scripts run on the server with `wp eval-file`:

```
1. seeds/seed-phase*.php        seed taxonomy terms, nav, homepage, roundups (one-time)
2. create_beans.php             create draft bean posts from products.json (canonical
                                origin + curated flavor-note mapping)
3. generate_review.py           write draft .md into /opt/drafts/
4. push_drafts.php              parse drafts → ACF fields + RankMath meta on bean posts
5. fetch_bean_images.py         resolve images → manifest.json
   set_featured_images.php      set featured images from the manifest
6. (human) review + Publish
```

> `create_beans_wpcli.sh` is an **older, parallel** importer that maps taxonomies
> differently (raw split vs. canonical consolidation). Use `create_beans.php`. See
> [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §R2.

### Deploy

There is no automated deploy in-repo. Theme/plugin files are pushed with `scp` and caches
flushed via `wp cache flush` over SSH (these commands are allow-listed in
`.claude/settings.json`, which also exposes the production IP — see security note below).
`setup.sh` only provisions the price-tracker baseline.

---

## 6. Subsystem 5 — Training-data → skill pipeline

Upstream tooling that produces the `coffee-review-writer` skill. Output lands in
gitignored dirs (`training_data/`, `skill_data/`, `voice_materials/`); only the final
assembled skill is committed.

```
run_pipeline.py ─► training_data/raw/{reddit,web,youtube,podcasts}/*.jsonl
   (reddit/web/youtube/podcast scrapers, config-driven)
        │
clean_pipeline.py ─► training_data/cleaned/   (dedup via MinHash, langdetect, ftfy, boilerplate strip)
        │
        ├─ build_voice_profile.py  (voice_materials/ + Claude tool-use) ─► skill_data/voice/
        ├─ build_skill_knowledge.py (cleaned corpus + Claude)            ─► skill_data/skill_knowledge.json
        ▼
assemble_skill.py ─► skills/coffee-review-writer/  (SKILL.md + voice/ + knowledge/ + gotchas.md)
```

- All config lives in `data_pipeline/config.json` (9 subreddits, 9 web sites, 7 YouTube
  channels; podcasts off by default). Reddit uses the public API via `requests` (no PRAW);
  YouTube uses `yt-dlp`.
- `format_for_finetuning.py` + `notebooks/finetune_hermes.ipynb` are an **exploratory
  fine-tuning track** that the skill approach superseded (see `SYNTHESIS_ARCHITECTURE.md`).
- `rescore_raw.py`, `view_top_content.py`, `test_clean_quality.py`,
  `test_build_skill_knowledge.py` are utilities/tests around this pipeline.

---

## 7. Cross-cutting conventions

- **Path auto-detection.** Most Python scripts prefer `/opt/...` when present (VPS) and
  fall back to the repo tree, so the same code runs in both. `db.py` centralizes this for
  the price DB.
- **Env loading.** Each script parses `/opt/.env` (or repo `.env`) into a dict, then
  overlays real environment variables. Keys: `AMAZON_*`, `BEEHIIV_*`, `MINIMAX_API_KEY`,
  `CLAUDE_API_KEY`, `YOUTUBE_API_KEY`, plus `REDDIT_*` for the pipeline.
- **Models in use** (current as of this audit): review generator → `claude-sonnet-4-6`
  (or `MiniMax-Text-01`); short-form/reformat → `claude-haiku-4-5-20251001`; pipeline
  extraction → `claude-sonnet-4-6`.
- **Em/en-dash ban.** Enforced in review prompts and `strip_dashes()` (also in
  `reformat_origin_descriptions.py`).
- **Disclosures.** FTC affiliate + AI-content + methodology disclosures are mandatory and
  rendered by the theme footer and per-page (`PREPUBLISH_CHECKLIST.md` §B).

## 8. What is and isn't automated

| Step | Status |
|---|---|
| Daily price scrape | Cron (but Amazon path failing — see findings) |
| Price-drop alerts | Cron (was crashing pre-audit; fixed) |
| `products.json` → `products` table sync | Manual |
| Reference corpus build | Manual, one-time (done) |
| Review draft generation | Manual (per product) |
| Draft → WordPress ACF | Manual (`wp eval-file push_drafts.php`) |
| Bean post creation | Manual (`wp eval-file create_beans.php`) |
| Image resolution + featured images | Manual |
| Skill (voice/knowledge) build | Manual, on its own cadence |
| Theme/plugin deploy | Manual (scp + wp-cli over SSH) |

The system is best understood as **a set of manual, re-runnable tools with one automated
daily price loop** — not an end-to-end automated content factory.
