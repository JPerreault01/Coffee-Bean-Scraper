# Deploy Runbook — 69-Bean Specialty Batch (2026-06)

Copy-paste deploy for the 69 new beans (catalog 171 → 240). Run from the **repo root
on your Windows machine** (PowerShell). The VPS is reached via the `cbi-prod` SSH alias.

> **Order matters.** Seed the 4 new flavor terms **before** `create_beans.php`, or
> beans tagged `red-fruit` / `blueberry` / `floral` / `spice` lose those tags at import.

Run `python scrapers/preflight.py --since 171` first — it must print **PREFLIGHT CLEAN**
(2 grade-code warnings are fine). And confirm all 69 drafts exist:
`(Get-ChildItem drafts\*.md | Measure-Object).Count` should be 240 total, or check the
batch progress file shows `remaining: []`.

---

## 1. Copy files to the VPS

```powershell
# Updated importer + catalog + seed data (seed file needs its data/ subdir alongside it)
scp scrapers/products.json      cbi-prod:/opt/scrapers/products.json
scp scrapers/create_beans.php   cbi-prod:/opt/scrapers/create_beans.php
scp scrapers/push_drafts.php    cbi-prod:/opt/scrapers/push_drafts.php
scp scrapers/fetch_bean_images.py cbi-prod:/opt/scrapers/fetch_bean_images.py
scp scrapers/set_featured_images.php cbi-prod:/opt/scrapers/set_featured_images.php

# Seed script + its data file (preserve the seeds/ + seeds/data/ layout under /opt)
ssh cbi-prod "mkdir -p /opt/seeds/data"
scp seeds/seed-phase2-flavors.php      cbi-prod:/opt/seeds/seed-phase2-flavors.php
scp seeds/data/flavor-note-terms.php   cbi-prod:/opt/seeds/data/flavor-note-terms.php

# All drafts (idempotent: re-syncing the existing 171 is harmless; this avoids any
# date-rollover misses if generation finished after local midnight)
scp drafts/*.md cbi-prod:/opt/drafts/
```

## 2. Seed the 4 new flavor terms (idempotent — updates if present)

```powershell
ssh cbi-prod "cd /var/www/coffeebeans && wp eval-file /opt/seeds/seed-phase2-flavors.php --allow-root"
```
Expect: `Created flavor-note term: red-fruit / blueberry / floral / spice` (or `Updated`
if they already exist). No `Parent ... not found` warnings.

## 3. Create the 69 bean drafts (CPT + taxonomies + ACF stubs)

```powershell
ssh cbi-prod "cd /var/www/coffeebeans && wp eval-file /opt/scrapers/create_beans.php --allow-root"
```
Read the summary: `Created 69 / Skipped 171 / Failed 0`. The **only** warnings should be
the deliberate `NO CURATED TERM` skips (bubblegum, champagne candy, dried tomato, rice
pudding). **Any `UNMAPPED origin` or `UNKNOWN flavor` means a map drifted — stop and tell
me;** pre-flight says there should be none.

## 4. Hydrate ACF + body from the drafts

```powershell
ssh cbi-prod "cd /var/www/coffeebeans && wp eval-file /opt/scrapers/push_drafts.php --allow-root"
```
Expect `UPDATED <id> ... verdict, rating X/10, N tasting notes + internal links` for each.

## 5. Images

```powershell
ssh cbi-prod "/opt/venv/bin/python3 /opt/scrapers/fetch_bean_images.py 2>&1 | tee /opt/data/images.log"
ssh cbi-prod "cd /var/www/coffeebeans && wp eval-file /opt/scrapers/set_featured_images.php --allow-root"
```
Cached files are skipped, so this is incremental. Expect a residue of `null` entries in
`/opt/scrapers/.image-cache/manifest.json` — those are the 21 beans whose only source is
the reference-corpus page (`data/affiliate_link_pending.json`); they resolve via the
waytocoffee fallback (source 4) or land on the manual-upload worklist.

> If `fetch_bean_images.py` errors on missing deps:
> `ssh cbi-prod "sudo /opt/venv/bin/pip install beautifulsoup4 lxml"`

## 6. Publish

Drafts land as **WordPress drafts** — nothing auto-publishes. Review in WP admin
(Beans → filter by draft), run the per-draft [PREPUBLISH_CHECKLIST.md](PREPUBLISH_CHECKLIST.md)
gate, then Publish.

---

## Verify after import

```powershell
# 240 bean posts total, 69 of them new drafts
ssh cbi-prod "cd /var/www/coffeebeans && wp post list --post_type=bean --format=count --allow-root"
# spot-check one new bean's ACF rating + origin terms
ssh cbi-prod "cd /var/www/coffeebeans && wp post list --post_type=bean --name=lilo-coffee-roasters-ethiopia-yirgacheffe-idido-washed --field=ID --allow-root"
```

## Backfill later (tracked, not blocking)

- **Affiliate buy-links:** `data/affiliate_link_pending.json` — 21 beans with no ASIN /
  real roaster_url. Add a verified `roaster_url` or `amazon_asin` to `products.json`, then
  re-run `push_drafts.php` (and `fetch_bean_images.py` for the image).
- **Price analysis:** every draft carries `<!--PRICE_PENDING-->`. Once `prices.db` has
  history for these products, regenerate the Price analysis section.
