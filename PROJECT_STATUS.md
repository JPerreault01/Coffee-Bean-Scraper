# Project Status — Coffee Bean Index

Snapshot as of **June 2026**, from a full repo + live-data audit. Status reflects what the
code and databases actually show, not intent. Details and reasoning are in
[AUDIT_FINDINGS.md](AUDIT_FINDINGS.md); how it all fits together is in
[ARCHITECTURE.md](ARCHITECTURE.md).

Legend: ✅ done / working · 🟡 partial or needs attention · 🔴 broken / not started

---

## At a glance

| Subsystem | Status | One-line |
|---|---|---|
| Reference corpus | ✅ | 14,386 coffees loaded; complete and queryable |
| WordPress theme | ✅ | Custom GeneratePress child theme, CPT, taxonomies, schema all built |
| Review generation (programmatic) | ✅ | `generate_review.py` works (mock verified); model id refreshed |
| Review skill | ✅ | `coffee-review-writer` assembled from 88 sources + voice profile |
| Price-drop alerts | 🟡 | Crash bug **fixed in this audit**; still has no real price data to act on |
| Price scraper | 🔴 | Runs, but Amazon path mostly fails; DB holds only seed data |
| Price → WordPress (homepage) | 🔴 | `cbi_price_drop_beans` returns `[]`; bridge never wired |
| `products` table sync | 🔴 | Table is empty; `sync_products.py` never run against live DB |
| Published content | 🟡 | Pipeline + 1 draft exist; bulk publishing not yet done |

---

## What's done ✅

- **Reference corpus.** `coffee_reference.db` holds 14,386 coffees, 1,033 roasters,
  ~3,600 flavor notes, ~2,300 origins, fully normalized with join tables. `waytocoffee.json`
  (~13 MB) is present. `reference_db.py` CLI (`load`/`specs`/`find`/`map`) works.
- **WordPress front end.** The `coffeebeanindex` GeneratePress child theme is complete:
  `bean` CPT, six taxonomies, ACF field group, custom templates (home, single-bean,
  archives, roundup, comparison, guide), JSON-LD schema (Product/Review/Offer/Breadcrumb/
  FAQ/ItemList/Organization), editor shortcodes + block patterns, guide ToC, responsive
  layout contract over GeneratePress. Documented in `THEME.md` / `DEPLOY_NOTES.md`.
- **Review generation.** `generate_review.py` builds a full SEO-complete draft (meta block,
  internal links, disclosures, voice modes, reference-spec enrichment) and runs in `--mock`
  with no API key. The `coffee-review-writer` skill is assembled (voice profile + knowledge
  from 88 sources + format + gotchas).
- **Supporting docs.** `SEO_PLAYBOOK.md`, `PREPUBLISH_CHECKLIST.md`, `CONTENT_REFRESH.md`,
  `THEME.md`, `SETUP_LOCAL.md`, `SYNTHESIS_ARCHITECTURE.md` are current and accurate.
- **Publish tooling.** `create_beans.php`, `push_drafts.php`, `fetch_bean_images.py`,
  `set_featured_images.php`, and the `seeds/` scripts exist and cover the draft→page path.

## In flight / needs attention 🟡

- **Content publishing.** Only Lavazza is seeded as a bean; the other 19 products have
  draft-creation tooling but the bulk run + review copy + publish hasn't happened. Drafts
  dir holds one mock draft.
- **Price-drop alerts.** The import-time crash (`sqlite3` not imported) is fixed and the
  paths are now portable, so the sender runs — but it has no real price data to alert on
  until the scraper produces some, and `BEEHIIV_*` keys must be set.
- **Reference linkage.** All 20 products have `reference_slug: null`, so review enrichment
  relies on fuzzy name matching. Running `reference_db.py map` and pasting confirmed slugs
  would make enrichment deterministic.

## Broken / not started 🔴

- **Amazon price scraping.** Headless Chromium is served anti-bot pages; the last live run
  was 6/20 successful. `prices.db` contains only `source='seed'` rows. This is the central
  unsolved problem of the price subsystem.
- **`products` table is empty.** `sync_products.py` has never been run against the live DB,
  so the `coffee-bean-profile` plugin (which reads that table) would render nothing.
- **Homepage price-drop strip.** `cbi_price_drop_beans` returns `[]` by design until a
  producer feeds it; no script writes the JSON/transient it expects. The per-bean
  `coffee-price-chart` widget does read the DB directly, so that surface works once real
  data exists.
- **Mediavine / 50k sessions goal.** Not started — depends on published content + traffic.

---

## Fixed during this audit

- `alerts/send_alerts.py` — added missing `import sqlite3` (it crashed at import on every
  cron run); made `LOG_PATH`/`PRODUCTS_FILE` path-portable so it runs locally and on VPS.
- `requirements.txt` — added `tqdm` (imported by `waytocoffee_scraper.py`) and `feedparser`
  (imported by `podcast_scraper.py`); both were missing.
- `scrapers/generate_review.py` — updated stale Claude model id `claude-sonnet-4-20250514`
  → `claude-sonnet-4-6`.
- Removed `main.py` (a Hello-World stub, unreferenced).
- Rewrote `README.md`, `CLAUDE.md`, and `data_pipeline/README.md` to match reality.

## Top priorities (next steps)

1. **Fix or replace Amazon price collection** (it's the blocker for the entire price value
   prop). See [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §P1 for options (PA-API GetItems vs
   Keepa vs hardening Playwright).
2. **Run `sync_products.py`** on the VPS so the `products` table is populated.
3. **Publish the first 10 pages** using the existing tooling.
4. **Decide the security follow-up** for the committed production IP / root-SSH references
   (§S1).
5. **Resolve the duplicate tooling** (`create_beans_wpcli.sh`, `coffee-bean-profile` /
   `coffee-flavor-explorer` plugins, ECC-skill generators) — keep one path each (§R2–R4).
