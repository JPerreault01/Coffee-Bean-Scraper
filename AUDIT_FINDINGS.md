# Audit Findings — Coffee Bean Index

Full architectural audit of the repository and the live system it deploys to, June 2026.
Every tracked file was read; the live SQLite databases, logs, and drafts were inspected.

This document has four parts:
1. [Headline conclusions](#1-headline-conclusions)
2. [Fixes applied in this pass](#2-fixes-applied-in-this-pass) (confident changes, already made)
3. [Flagged for your review](#3-flagged-for-your-review) (judgment-dependent — not changed)
4. [Docs-vs-reality contradictions](#4-docs-vs-reality-contradictions) and
   [Prioritized next steps](#5-prioritized-next-steps)

---

## 1. Headline conclusions

- **The repo is ~4x larger than its docs described.** `CLAUDE.md` and `README.md` described
  a simple "scraper + one WP plugin" project. The reality is five subsystems: a price
  tracker, a 14k-coffee reference corpus, two review generators, a full custom WordPress
  theme, and a training-data→skill pipeline. Both docs have been rewritten.

- **The live front end is a custom GeneratePress child theme**, not the loose plugins the
  old docs implied. The theme (`bean` CPT, six taxonomies, ACF, schema, custom templates)
  is the most mature part of the system and is well-documented in its own `THEME.md`.

- **The price subsystem produces no real data.** `prices.db` holds 161 rows, all
  `source='seed'`. The `products` table is empty. The last real scrape (2026-05-26) failed
  14 of 20 products because Amazon blocks headless Chromium. This is the biggest functional
  gap.

- **The alert sender was dead on arrival.** `send_alerts.py` referenced `sqlite3.Connection`
  in type hints without importing `sqlite3`, so it raised `NameError` at import on every
  cron run since it was written. Fixed.

- **A production server IP and root-SSH access are committed to a public repo.** Flagged,
  not auto-changed (it's load-bearing for the deploy workflow).

- **Several subsystems have duplicate/competing implementations** (two bean importers, two
  review-generation approaches plus three ECC-skill scripts, three visualization plugins
  partly superseded by the theme). None are broken, but they invite drift and confusion.

---

## 2. Fixes applied in this pass

These were made directly because they are unambiguous (bugs, dead code, missing deps, stale
docs). All are grouped into logical commits — see [§6](#6-commit-plan).

### Code

| File | Change | Why |
|---|---|---|
| `alerts/send_alerts.py` | Added `import sqlite3` | The module used `sqlite3.Connection` in four function signatures. Python evaluates annotations at def-time, so the import raised `NameError: name 'sqlite3' is not defined` — the alert sender crashed before doing anything, on every 06:15 cron run. Verified the module now imports cleanly. |
| `alerts/send_alerts.py` | Made `LOG_PATH` and `PRODUCTS_FILE` path-portable (and `mkdir` the log dir) | They were hardcoded to `/opt/...`, so the sender could never run locally (contradicting `SETUP_LOCAL.md`, which seeds data specifically to test alerts). Now mirrors the `/opt`-else-repo pattern used everywhere else. |
| `scrapers/generate_review.py` | `claude-sonnet-4-20250514` → `claude-sonnet-4-6` | **Verified against the Anthropic docs and the installed SDK** (`anthropic/types/model.py` lists `claude-sonnet-4-6` as a valid model literal): the old id (Claude Sonnet 4) is **deprecated and retires June 15, 2026** — it would have started 404-ing within ~9 days of this audit. `claude-sonnet-4-6` is the current pinned API id; from the 4.6 generation Anthropic uses the dateless form *as* the snapshot (no separate `-YYYYMMDD`). Other repo scripts already call `claude-sonnet-4-6` successfully (the assembled skill is proof). |
| `requirements.txt` | Added `tqdm`, `feedparser` | `tqdm` is imported by `waytocoffee_scraper.py` (a documented core workflow) and was missing — the reference scrape would `ImportError`. `feedparser` is imported by `podcast_scraper.py`, which `run_pipeline.py` runs by default. |
| `main.py` | Removed | A literal `greet("World")` Hello-World stub at the repo root, referenced by nothing. |

### Docs

| File | Change |
|---|---|
| `README.md` | Rewrote to describe the five real subsystems, the real repo layout, both databases, the real stack, and the manual deploy path. |
| `CLAUDE.md` | Rewrote the stack/models/paths/structure and the WordPress content model + publish path; de-duplicated the voice-rules sections. **Preserved verbatim:** the three required disclosures, the review format, the analytical/personal voice HARD RULES, standing preferences, and the em-dash ban. |
| `data_pipeline/README.md` | Corrected the source lists to match `config.json` (9 subreddits not 4, 9 web sites not 3, 7 YouTube channels not 2), fixed `max_videos_per_channel` (500 not 200), corrected "youtube-transcript-api" → `yt-dlp`, noted Reddit uses raw `requests` (no PRAW), and added the skill-build stage. |
| New: `ARCHITECTURE.md`, `PROJECT_STATUS.md`, `AUDIT_FINDINGS.md` | Created. |

---

## 3. Flagged for your review

Not changed — each needs a decision or carries risk. Grouped by theme with a recommendation.

### Security

**§S1 — Production IP + root SSH committed to a public repo. [PARTIALLY REMEDIATED]**
`scrapers/reformat_origin_descriptions.py` hardcoded a `root@<production-ip>` SSH host, and
`.claude/settings.json` (tracked) contained several `scp`/`ssh` commands to the same
`root@<ip>` plus the live domain. This is a public repo. It was not a credential leak (no
key/password committed), but it handed an attacker the exact host, the fact that root SSH is
the entry method, the WordPress path, and the domain — free reconnaissance. Side note: the
IP was in DigitalOcean's range (142.93.0.0/16), which **contradicts `CLAUDE.md`'s "Hetzner
CX23"** — confirm where the site actually runs.

*Done in this pass (code side — the IP/root no longer appear in the repo):*
- `reformat_origin_descriptions.py` now reads the host from `CBI_SSH_HOST`, defaulting to the
  SSH alias `cbi-prod`.
- `.claude/settings.json` deploy commands now use the `cbi-prod` alias instead of `root@<ip>`.
- Added [DEPLOY.md](DEPLOY.md): the server-hardening runbook + local `~/.ssh/config` alias
  (the real IP now lives only in your local config, never the repo).

*Still requires you to run on the server (see DEPLOY.md §0):* create a non-root `deploy`
user, install your SSH key, set `PasswordAuthentication no` + `PermitRootLogin no`, and
verify a new `deploy` session before closing root. Optional: scrub the IP from git history
(cleanup only — it's already public; host hardening is the real fix) and/or firewall SSH to
your own IP at the provider level.

### Price pipeline

**§P1 — Amazon scraping mostly fails; the price value-prop has no data.**
`scraper.log` shows the 2026-05-26 run: 6 succeeded / 14 failed, all failures "Could not
find price." Playwright with a desktop UA gets anti-bot interstitials from Amazon. Result:
`prices.db` has only seed rows, the price chart and homepage strip have nothing real to
show, and alerts have nothing to fire on.
*Recommended approach (pick one, in order of robustness):* (a) **Amazon PA-API GetItems**
for price+image — you already implement SigV4 signing in `fetch_bean_images.py`, so the
auth code exists; PA-API returns `Offers.Listings.Price`. This is the sanctioned path but
needs an approved Associates account with sales. (b) A paid price API (Keepa/Rainforest) if
PA-API approval is a blocker. (c) Harden Playwright (residential proxy, stealth plugin,
real-session cookies) — least reliable, highest maintenance. Roaster (Shopify/Woo) URLs
scrape fine today, so direct-roaster products are unaffected.

**§P2 — `products` table never synced.** `sync_products.py` exists and works but has never
run against the live DB (`products` = 0 rows). The `coffee-bean-profile` plugin reads that
table, so it would render empty. *Recommended:* run `sync_products.py` on the VPS and add it
to cron after the scraper (`coffee-bean-profile/README.md` already suggests `30 6 * * *`).

**§P3 — Homepage price-drop bridge not wired.** `cbi_price_drop_beans()`
(`functions.php` §20) returns `[]` until something feeds the `cbi_price_drop_beans` filter.
Nothing writes the expected JSON/transient. *Recommended:* have `price_scraper.py` (or a
small post-step) write a `wp_options` transient or a JSON snapshot the filter reads — the
function's docblock specifies the exact row shape. Low effort, lights up the homepage strip.

### Redundancy & potentially-orphaned code

**§R2 — Two bean importers that build different taxonomies. [RESOLVED]**
`create_beans.php` (canonical: consolidates origins via an `$origin_map`, maps flavor notes
to curated slugs, drops structural descriptors) vs `create_beans_wpcli.sh` (raw:
`--create-terms`, splits "Brazil, Colombia, Indonesia blend" into three origin terms and
creates flavor-note terms for structural descriptors like "bold"/"smooth"). Running the
wrong one — or both — pollutes the taxonomy. Git history shows `create_beans.php` got the
canonical mapping *after* the `.sh`, so the `.sh` was the older approach.
**Verdict: `create_beans.php` is canonical; `create_beans_wpcli.sh` has been removed.**
The canonical publish order is **seeds → `create_beans.php`** (it expects the curated
flavor-note slugs that `seeds/data/flavor-note-terms.php` creates, and warns "run seeds
first" if they're missing).

**§R3 — Three scripts depend on an external third-party skill repo.** `write_review.py`,
`market_research.py`, and `repurpose.py` fetch SKILL.md files from
`github.com/affaan-m/ECC` at runtime. This is a supply-chain and availability risk (if that
repo moves/changes, behaviour shifts silently; each has a fallback prompt, which softens but
doesn't remove the issue). They also overlap heavily with `generate_review.py` + the local
`coffee-review-writer` skill. *Recommended:* decide whether these are still used. If yes,
vendor the ECC skills into the repo (or your own skill) instead of fetching at runtime. If
no, remove them. `write_review.py` in particular duplicates `generate_review.py` with a
weaker feature set (no price history, no reference enrichment, no voice modes).

**§R4 — Two visualization plugins look superseded by the theme.**
`coffee-bean-profile` (radar + sensory + similar beans) and `coffee-flavor-explorer`
(filterable grid + radar) duplicate what the theme now renders natively (`single-bean.php`
radar/sensory/similar; `page-explore.php` + `explore-filters.js` grid). The theme is newer
(v2.1). **Verdict: the theme is canonical for radar/sensory/explore; `coffee-price-chart`
stays (it's the live DB→page price widget the theme enqueues Chart.js for);
`coffee-bean-profile` and `coffee-flavor-explorer` are the losers.**

*Not removed yet — one gating check first.* Deactivating a plugin whose shortcode sits on a
live page turns that shortcode into raw text. Before deleting, confirm nothing published
uses them:

```bash
ssh cbi-prod "sudo -u www-data wp post list --post_type=any --post_status=publish \
  --fields=ID,post_title --format=csv --path=/var/www/coffeebeans | head -1; \
  sudo -u www-data wp db query \"SELECT ID,post_title FROM wp_posts \
  WHERE post_status='publish' AND (post_content LIKE '%[coffee_bean_profile%' \
  OR post_content LIKE '%[coffee_profile%' OR post_content LIKE '%[flavor_explorer%')\" \
  --path=/var/www/coffeebeans"
```

If that returns no rows: deactivate both plugins in WP admin, confirm the pages still look
right, then delete the two plugin folders from the repo and the server. If it returns rows,
migrate those pages to the theme's native components first.

**§R5 — Committed binary build artifacts.** `coffee-bean-profile.zip` and
`coffee-price-chart.zip` sit at the repo root, duplicating the plugin source directories.
They're stale snapshots and shouldn't be version-controlled. *Recommended:* delete them and
add `*.zip` to `.gitignore`; build zips on demand for upload. (Not auto-deleted in case you
rely on them for manual plugin upload.)

### Code quality (lower severity, not changed)

**§C1 — `tests/test_local.py` structure.** It defines `main()` and calls
`sys.exit()` under `if __name__ == "__main__"`, then defines a `TestFlavorJSON(unittest
.TestCase)` class *after* that block. Running the file executes only `main()` (which runs the
real Playwright scraper against 3 products — an integration test, not a unit test); the
`unittest` class only runs under `python -m unittest`. It works but is confusing.
*Recommended:* split the integration smoke test and the unit tests into separate files.

**§C2 — `datetime.utcnow()` deprecation.** Used in `seed_test_data.py`, `test_local.py`, and
`build_flavors_json.py`. Deprecated in Python 3.12+ (the repo targets 3.13). Not breaking
yet; replace with `datetime.now(timezone.utc)` when convenient. Left alone to avoid changing
stored timestamp formats without your sign-off.

**§C3 — RankMath schema duplication risk.** The theme emits `Product`/`Article` JSON-LD and
RankMath may too. Already documented in `THEME.md` §SEO and `DEPLOY_NOTES.md` §8 — listed
here only so it's tracked. Verify in the live page source and disable RankMath's Product
schema on the `bean` CPT if duplicated.

**§C4 — `setup.sh` is a partial provisioner.** It installs the price-tracker baseline only
(`requests playwright anthropic`) and predates the reference corpus, the data pipeline, and
the custom theme. It does not `pip install -r requirements.txt`, so a server stood up purely
from `setup.sh` can't run `waytocoffee_scraper.py` (needs `tqdm`, `beautifulsoup4`) or the
pipeline. Not wrong, just incomplete. *Recommended:* either have `setup.sh` install from
`requirements.txt`, or document that it's intentionally the minimal baseline (the rewritten
README now says the latter).

---

## 4. Docs-vs-reality contradictions

The specific mismatches found (the rewrites in §2 resolve the doc side of each):

| # | Claim (where) | Reality |
|---|---|---|
| D1 | "Hetzner CX23 VPS" (`CLAUDE.md`, `README.md`, `setup.sh`) | The (now-removed) deploy IP was in a **DigitalOcean** range — confirm actual host (§S1) |
| D2 | "MiniMax M2.7 or Claude API" (`CLAUDE.md`) | Code uses `MiniMax-Text-01` and (pre-fix) `claude-sonnet-4-20250514` |
| D3 | Repo = scrapers + one `coffee-price-chart` plugin (`README.md`) | Five subsystems incl. a full custom theme, reference corpus, data pipeline |
| D4 | WP plugins: RankMath, WP Rocket, coffee-price-chart, WPForms (`CLAUDE.md`) | Add GeneratePress + custom theme + ACF; two extra plugins likely superseded |
| D5 | Reviews are WordPress posts via plugin | Reviews are a `bean` CPT with ACF fields, rendered by the theme |
| D6 | data_pipeline sources: 4 subreddits / 3 sites / 2 channels (`data_pipeline/README.md`) | `config.json`: 9 / 9 / 7 |
| D7 | "Transcripts fetched via youtube-transcript-api" (`data_pipeline/README.md`) | Code uses `yt-dlp` |
| D8 | `select_products.py` next-step cites `batch_build_products.py` and `waytocoffee_scraper.py --details-for/--tag` | Those don't exist — that script has no `--details-for`/`--tag` flags and `batch_build_products.py` is absent (stale in-code docs). **RESOLVED:** docstring rewritten to the real step (curate `promotion_candidates.json` → add to `products.json` → `generate_review.py <id>`) |
| D9 | README reference corpus "~14,000"; `select_products.py` "~17k" | DB has 14,386 — use 14k. **RESOLVED:** `select_products.py` now says ~14k |
| D10 | `.gitignore` / `CLAUDE.md` old gitignore block | Real `.gitignore` also ignores `training_data/*`, `skill_data/`, `voice_materials/`, `.tmp-shots/`, `data/*.json` — now reflected |

> Note: `SEO_PLAYBOOK.md`, `PREPUBLISH_CHECKLIST.md`, `CONTENT_REFRESH.md`, `THEME.md`,
> `DEPLOY_NOTES.md`, `SETUP_LOCAL.md`, and `SYNTHESIS_ARCHITECTURE.md` were found **accurate**
> and consistent with the code. The drift was concentrated in `CLAUDE.md`, `README.md`, and
> `data_pipeline/README.md` — the three top-level orientation docs.

---

## 5. Prioritized next steps

1. **Unblock price collection (§P1).** Nothing in the price value-prop works until this
   does. Try PA-API GetItems first (auth code already exists in `fetch_bean_images.py`).
2. **Run `sync_products.py` on the VPS (§P2)** and add it to cron after the scraper.
3. **Decide the security follow-up (§S1)** — move the host out of code, confirm SSH hardening.
4. **Publish the first 10 pages** with the existing tooling (`create_beans.php` →
   `generate_review.py` → `push_drafts.php` → images). All the machinery is built.
5. **Set `reference_slug` per product** (`reference_db.py map scrapers/products.json`) so
   review enrichment is deterministic, not fuzzy.
6. **Wire the homepage price-drop strip (§P3)** once real price data exists.
7. **Resolve duplicate tooling (§R2–R5):** keep `create_beans.php`, decide on the ECC
   scripts and the two extra plugins, and drop the committed `.zip`s.
8. **Housekeeping (§C1–C4):** split the test file, replace `utcnow()`, verify RankMath
   schema, and decide `setup.sh`'s scope.

---

## 6. Commit plan

The work is grouped into four commits:

1. `fix(alerts): import sqlite3 + portable paths so the price-drop sender runs`
2. `fix(deps,review): add missing tqdm/feedparser deps; refresh stale Claude model id; drop dead main.py`
3. `docs: rewrite README/CLAUDE/data_pipeline README to match reality; add ARCHITECTURE/PROJECT_STATUS/AUDIT_FINDINGS`
4. `security(§S1): remove hardcoded prod IP/root from repo; add DEPLOY.md hardening runbook; retire create_beans_wpcli.sh (§R2)`

Exact PowerShell commands are at the end of the audit hand-off.
