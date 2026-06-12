# Review Generation Runbook

> **What this is:** the batch pipeline for taking new beans from `products.json` to
> published WordPress reviews, written from the mistakes made generating the June 2026
> 100-bean batch. Every section exists because something broke or wasted time the first
> time. Run the **Phase 0 pre-flight** before generating anything — it catches the
> failures that otherwise only surface hours later at import or image-fetch time.
>
> This is the operational/pipeline doc. The per-draft final gate is
> [PREPUBLISH_CHECKLIST.md](PREPUBLISH_CHECKLIST.md); scoring rules live in
> [CLAUDE_content_standards_section.md](CLAUDE_content_standards_section.md). Don't
> duplicate those here — this is about getting 100 beans through the machine cleanly.

---

## The one rule

**Validate `products.json` against the importers BEFORE you generate a single draft.**
Generation is the expensive step (Opus tokens, Pro-window limits). Every defect found
after generation costs a regenerate or a manual server-side fix. The June batch lost time
to exactly three classes of defect, all of which were knowable from `products.json` alone:

1. **Encoding** — accented names (Cafés, Quindío, Hōlualoa) crashed Windows cp1252 I/O.
2. **Taxonomy-map gaps** — 73 origins and ~130 flavor strings weren't in `create_beans.php`,
   discovered only when the importer ran on the VPS.
3. **Bad source URLs** — duplicate placeholder `roaster_url`s (every Volcanica bean → one
   sumatra page) and affiliate redirects (Intelligentsia → awin1), discovered only when
   `fetch_bean_images.py` failed 100 times.

All three are static checks. Run them first.

---

## Phase 0 — Pre-flight (build `scrapers/preflight.py`)

There is no committed pre-flight script yet. **Build one and keep it** (the throwaway
`_qa.py`, `_build_additions.py`, `_normalize_names.py` from the June batch were never
committed, so the next batch starts blind). `preflight.py` should load `products.json` and
the two PHP maps and fail loudly on anything below. Until it exists, run these checks by
hand.

### 0.1 Required-field completeness
For every new product, these must be non-empty: `id`, `name`, `brand`, `origin`,
`roast_level`, `process_method`, `weight_oz`, and at least one of `amazon_asin` /
`roaster_url`. **Blank `roast_level` and blank `origin` were both present in the June
batch** (22 blank roasts backfilled from critic spec; Onyx Panama Finca Deborah shipped
with an empty origin and was only caught at import). A blank required field is a hard stop.

### 0.2 Origin-map coverage (against `create_beans.php`)
Extract the `$origin_map` keys from `create_beans.php` and assert **every** distinct
`products.json` origin string is a key. Any miss falls back to `sanitize_title()` on the
VPS, producing a garbage composite slug like `colombia-quindio-washed-lot-3`. The June
batch had 73 unmapped origins. This check turns a 30-minute server-side surprise into a
10-second local failure.

### 0.3 Flavor-map coverage (against `create_beans.php`)
Same idea for `$flavor_canonical_map` + `$flavor_structural_drops`. Every lowercased
`flavor_notes` string must be a key in one of them (mapping to a slug, `null`, or `false`).
Unknown strings get skipped silently with a warning and the bean loses that tag. ~130 were
unmapped in June. New exotic descriptors will always appear (haskap, calpis, buah bidara) —
the check forces a deliberate decision (curate a term vs. `null`-skip) instead of silent loss.

### 0.4 URL hygiene (the same logic `url_filters.py` already implements)
Import `scrapers/url_filters.py` and run both checks at pre-flight, not just at fetch time:
- `is_skippable_url(roaster_url)` — flag affiliate redirects / social (awin1, shareasale,
  pinterest, etc.). These can't yield a product image; the bean needs an ASIN or a real URL.
- `build_placeholder_urls(products)` — flag `(brand, url)` pairs shared by ≥3 products.
  These are copy-paste artifacts from catalog expansion (the Volcanica/Lily Willy's/
  Intelligentsia clusters). A flagged URL is **wrong data** — fix it in `products.json`,
  don't just let the fetcher skip it.

Report counts. A clean batch has zero affiliate `roaster_url`s feeding image resolution and
zero placeholder clusters.

### 0.5 Encoding + name casing
- Load `products.json` with `encoding="utf-8"` and assert it round-trips. Names legitimately
  contain accents and macrons — the fix is never to strip them, it's to make every reader
  UTF-8 clean (already done in `generate_review.py`; keep it that way).
- Normalize ALL-CAPS words in `name`/`brand` (title-case) while preserving grade codes (AA,
  PB, WBC, NX, WX, G1, SL28). The June batch shipped "KENYA GATURIRI PEABERRY" until
  normalized. Fold this into pre-flight so casing is fixed before generation, not after.

### 0.6 `reference_slug` presence
Every new bean should carry a `reference_slug` (the waytocoffee.com corpus slug). It is the
image fallback of last resort (`fetch_bean_images.py` source 4) and the spec cross-check key.
Flag any new bean missing it.

**Gate:** pre-flight must print `PREFLIGHT CLEAN` with zero hard failures before Phase 2.

---

## Phase 1 — Catalog prep

1. Select keepers via `select_products.py` (cross-DB critic enrichment, composite ranking).
   Remember the **scoring firewall**: `coffeereview.db` data may inform selection, ranking,
   and factual spec cross-check ONLY. It must never land in `products.json`, a draft, or any
   field `generate_review.py` reads. The review's score is formed independently.
2. Map each new bean's `reference_slug` from its corpus URL slug (deterministic).
3. Backfill blank `roast_level` from the critic factual `roast_level` (factual spec, not a
   score — firewall-safe).
4. Web-verify anything suspicious (the June batch corrected Stumptown Founder's Blend origin
   this way).
5. **Extend the PHP maps now, not at import.** Add the batch's new origin strings to
   `$origin_map` and new flavor strings to `$flavor_canonical_map` in `create_beans.php`.
   Then re-run Phase 0 until coverage is 100%.

---

## Phase 2 — Generation

### Environment (do this once per machine, verify every run)
- **VPS venv deps:** `beautifulsoup4`, `lxml` are required by `fetch_bean_images.py` and the
  resolver chain. Install with `sudo /opt/venv/bin/pip install beautifulsoup4 lxml` (the
  venv is root-owned; a bare `pip install` hits `Permission denied`).
- **Playwright is optional.** `fetch_bean_images.py` runs requests-first and only uses
  Playwright if the chromium binary exists. Don't install it unless requests-based
  resolution leaves too many beans unresolved. If you do: `/opt/venv/bin/python3 -m
  playwright install chromium`.
- **Encoding:** generation is UTF-8 clean end to end. If you add a new reader of
  `products.json` or drafts, open with `encoding="utf-8"` and reconfigure stdio
  (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`). Never strip accents.

### Generate
```bash
# Local, free Pro tokens (Opus), batches of 10, resumable:
CBI_CC_MODEL=opus python scrapers/generate_review.py <id> --api claude-code
```
- **Write ID lists with `\n`, not `\r\n`.** A Windows CRLF ID file made a bash loop pass IDs
  with a trailing `\r` that matched no product, failing every generation in the June batch.
  If a list is generated on Windows, strip CR in the loop: `tr -d '\r'`.
- **Batch in 10s and checkpoint.** Pro caps at ~42 Opus generations per window. Track done
  IDs in a file; resume the remainder. Don't burn a window re-running completed beans.
- **`--mock` first** on one bean to confirm the prompt/format before spending tokens.

### Output hygiene (already enforced, don't regress)
`generate_review.py` ends drafts at the `<!--SCORE-->` block via `truncate_after_score()`
and the "review-only" prompt instruction. This kills the agentic chatter / duplicate-H1 /
"I've written the review" trailers that contaminated 13 drafts before the backstop existed.
If you change the prompt, keep both the instruction and the truncation.

---

## Phase 3 — WordPress import

```bash
# On the VPS, from /var/www/coffeebeans:
wp eval-file /opt/scrapers/create_beans.php --allow-root   # stub bean CPTs + taxonomies + ACF
wp eval-file /opt/scrapers/push_drafts.php  --allow-root   # hydrate ACF from draft .md files
```
- `create_beans.php` is idempotent — skips existing slugs, safe to re-run. Read its summary:
  `Created / Skipped / Failed`, then the `UNMAPPED ORIGINS`, `UNKNOWN FLAVOR`, and `NO CURATED
  TERM` sections. **If Phase 0 passed, the only warnings should be the deliberate `null`
  flavor skips.** Any `UNMAPPED origin` means the map drifted from `products.json` — fix and
  re-run.
- `push_drafts.php` matches drafts to posts by slug from the `<id>-YYYY-MM-DD.md` filename and
  overwrites ACF each run, so re-running after editing a draft re-syncs it.
- **SCP everything the scripts need.** `push_drafts.php` was forgotten in the first SCP and
  the run errored `does not exist`. The set: `create_beans.php`, `push_drafts.php`,
  `products.json` → `/opt/scrapers/`; all `drafts/*.md` → `/opt/drafts/`.

---

## Phase 4 — Images

`fetch_bean_images.py` resolves one image per bean through a priority chain (cached → PA-API
→ Amazon page scrape → roaster og:image → waytocoffee.com → Playwright → manual). It shares
SigV4 / scrape / URL-filter logic with the resolver chain in `scrapers/resolvers/` and
`scrapers/url_filters.py` — one implementation, used here and by `refresh_data.py`.

```bash
rm -f /opt/scrapers/.image-cache/manifest.json     # only if re-resolving prior failures
/opt/venv/bin/python3 /opt/scrapers/fetch_bean_images.py 2>&1 | tee /opt/data/images.log
cd /var/www/coffeebeans && wp eval-file /opt/scrapers/set_featured_images.php --allow-root
```
- Cached files (>10 KB) are skipped, so the run is incremental — only new/failed beans fetch.
- `set_featured_images.php` never overwrites an existing featured image (protects manual
  uploads) and is idempotent.
- The `manifest.json` `null` entries are your manual-upload worklist. Expect a residue:
  beans whose only source was an affiliate redirect or a placeholder URL (caught in Phase 0)
  will land here until their `roaster_url` is fixed or an ASIN is added.

### Prefer `refresh_data.py` for ongoing health
For maintenance (not the initial bulk backfill), `refresh_data.py` is the better entry point:
it resolves price/image/asin through the same chains and records `product_data_health` (stale
flags, fail counts, last-good retention — no failure crashes the run).
```bash
python scrapers/refresh_data.py --all                 # refresh everything
python scrapers/refresh_data.py --field image         # one field
python scrapers/refresh_data.py --health-report       # list stale/failing rows
python scrapers/refresh_data.py --validate-asins      # cross-check every ASIN
```
Run `--validate-asins` as part of pre-flight on any batch that ships ASINs — a dead/wrong
ASIN silently breaks both the affiliate link and the Amazon image path.

---

## Phase 5 — QA + publish

1. **Promote `_qa.py` to a committed `scrapers/qa_drafts.py`.** It scanned all 100 drafts for
   em/en-dashes, first-person/crowd attribution, cross-bean comparison leaks, missing price
   markers, agentic chatter, duplicate H1s, prose after the SCORE block, and incomplete
   format — and printed the rating distribution. It found the 13 contaminated drafts. It is
   too useful to keep throwing away. Gate the batch on it: **zero issues on all dimensions.**
2. Run the per-draft [PREPUBLISH_CHECKLIST.md](PREPUBLISH_CHECKLIST.md) gate.
3. Manual Publish in WP admin. Nothing auto-publishes.

---

## Scoring: what we learned (don't relitigate)

- **Keep the generation-time score. Do not cold-rescore a finished batch.** The comparative
  ledger pulls scores toward the catalog's central tendency (~7.1). Cold-rescoring the June
  batch against a ledger seeded from prior beans *compressed* the spread (max dropped 8.1 →
  7.8) even with the rubric nudged upward. The drafts were restored to their original scores.
  The rubric is the authority; the ledger is for *ordering*, and re-anchoring the *magnitude*
  to it reintroduces the exact bias the rubric exists to fix. This is documented in
  `CLAUDE_content_standards_section.md` §4 — believe it.
- The score is a **minor on-page signal**. It is not worth risking a QA-clean draft set or
  another Pro window to nudge a few elite lots up half a point.
- The anti-comparison rule (no "better than X", "past Koa's 7.4" in visible prose) is enforced
  in three places in `score_ledger.py` (`format_scoring_context`, `rating_section_instruction`,
  `SCORE_TRAILER_INSTRUCTION`). With the catalog heading past 1000 beans, naming a neighbour
  reads as arbitrary and dates the page. Keep all three.

---

## Quality levers (where review quality actually comes from)

Ranked by impact, given the pipeline is already firewall-clean and voice-clean:

1. **Verified specs in, quality out.** The single biggest quality determinant is the accuracy
   of `origin`, `roast_level`, `process_method`, and `flavor_notes` fed to the prompt. Garbage
   or generic specs → generic reviews. Spend the cross-check effort (corpus + critic spec) at
   Phase 1; it pays off in every section of every draft.
2. **Fix `roaster_url` data, then fetch images.** A real product image lifts a page more than
   a half-point score change. The placeholder/affiliate URL clusters caught in Phase 0 aren't
   just an image problem — a wrong `roaster_url` is also a broken "Buy Direct" link. Fixing
   them improves the page and the affiliate path at once.
3. **Curate the common exotic flavors instead of `null`-skipping them.** Several `null`-skipped
   strings recur across the batch (black tea ×9, peach-adjacent, citrus-adjacent). Adding a few
   curated `flavor-note` terms (e.g. a `black-tea`, `tropical`, `wine` term) to the seed data
   and the map captures real flavor signal that's currently dropped, improving on-site
   discovery and internal linking.
4. **Use `--personal` only where earned.** Personal mode unlocks first-person and brew logs for
   beans the owner has actually tried. It's the one lever that makes a review unmistakably
   first-hand. Don't fake it; do use it where it's real.
5. **Refresh `PRICE_PENDING` drafts once `prices.db` has data.** Every June bean shipped with a
   `<!--PRICE_PENDING-->` marker and is listed in `data/price_pending.json`. The Price analysis
   section is the weakest part of those drafts until real price history exists. When the scraper
   has data, regenerate just that section for the pending set.

---

## Known data-quality traps (June 2026 batch)

- **Volcanica** new beans shared one `roaster_url` (sumatra-mandheling). Placeholder cluster.
- **Lily Willy's** new beans shared one `roaster_url` (teddys-blend). Placeholder cluster.
- **Intelligentsia** new beans used awin1 affiliate redirects as `roaster_url`. Affiliate skip.
- **Blue Bottle, Atlas, Philz, Black Rifle, Caribou, Illy** block scraping via robots.txt at
  the page level. `fetch_bean_images.py` no longer consults robots.txt (one-off image fetch is
  not crawling), but these sites may still need an ASIN path or manual upload.
- These are fixed in `products.json` data, not in code. The code (`url_filters.py`) only
  *detects* them. Pre-flight surfaces them; a human corrects the URLs.

---

## Tooling debt to pay down (so the next batch is faster)

The June batch leaned on four uncommitted throwaway scripts. Promote the durable ones:

| Throwaway | Promote to | Why |
|---|---|---|
| `_qa.py` | `scrapers/qa_drafts.py` | Permanent draft-QA gate; found the 13 bad drafts |
| (none) | `scrapers/preflight.py` | Phase 0 gate; would have caught all 3 June defect classes |
| `_normalize_names.py` | fold into `preflight.py` | Casing fix belongs pre-generation |
| `_build_additions.py` | keep as one-off | Batch-specific; not reusable |
| `_rescore.py` | **delete** | Cold-rescore is a known-bad approach; don't keep the gun loaded |

Building `preflight.py` and `qa_drafts.py` converts the two slowest, most error-prone steps of
this batch (server-side import surprises, post-hoc draft contamination) into fast local gates.
That is the highest-leverage optimization available for the next run.
