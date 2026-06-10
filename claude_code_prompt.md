# Claude Code Prompt — Bulk Bean Onboarding + Review Generation

Paste everything below into Claude Code (from the repo root, on `main`).
It is written so Claude Code does the merging, mapping, generation, and VPS deploy.
You only run the local git commands it gives you and approve drafts at the end.

---

You are working in the Coffee-Bean-Scraper repo. I am adding 60 new beans to
`scrapers/products.json` and want to generate review drafts for all of them plus the
existing 20. Follow these steps in order. Stop and show me output after each numbered
step before continuing.

## Context you need
- The 60 new beans are in `new_beans.json` at the repo root (I placed it there).
- Every new bean has `amazon_asin: null` and a marker field `_asin_status: "BACKFILL"`.
  These ASINs are intentionally empty — do NOT invent ASINs. The affiliate URL builder in
  `create_beans.php` already falls back to `roaster_url` when `amazon_asin` is empty, so
  reviews will link correctly via the roaster URL until I backfill real ASINs.
- `generate_review.py` enriches each review from `coffee_reference.db` via `reference_slug`,
  or fuzzy-matches by name when `reference_slug` is null. Where the reference DB has no
  match, the generator should proceed and write its best-effort tasting notes / origin /
  sensory bars from the product's own `flavor_notes`, `origin`, and `roast_level` fields —
  it must NOT block or prompt for clarification on missing reference data.

## Step 1 — Merge new beans into products.json
- Read `scrapers/products.json` (the existing 20) and `new_beans.json` (the 60).
- Append the 60 to the existing array. Before writing, verify there are no duplicate `id`
  values across the combined set; if any new id collides with an existing one, rename the
  new one by appending the roaster (e.g. `french-roast` -> `peets-french-roast`) and tell me.
- Strip the `_asin_status` helper field out before writing into products.json (keep it only
  in new_beans.json as my backfill checklist). products.json must stay schema-clean.
- Write the combined array back to `scrapers/products.json`. Confirm the new total count.

## Step 2 — Patch the origin_map in create_beans.php
Several new beans use origin strings not yet in the `$origin_map` in
`scrapers/create_beans.php`. Without map entries they fall through to `sanitize_title` and
create inconsistent taxonomy slugs. Add these keys to `$origin_map` (match the existing
`[ slug, display ]` format):

```php
'Chiapas, Mexico'                 => [ 'mexico',            'Mexico'             ],
'Kona, Hawaii'                    => [ 'hawaii',            'Hawaii'             ],
'Yirgacheffe, Ethiopia'           => [ 'ethiopia',          'Ethiopia'          ],
'Guji, Ethiopia'                  => [ 'ethiopia',          'Ethiopia'          ],
'Tarrazu, Costa Rica'             => [ 'costa-rica',        'Costa Rica'        ],
'Ethiopia, Latin America blend'   => [ 'multi-origin-blend', 'Multi-Origin Blend' ],
'Indonesia, South America blend'  => [ 'multi-origin-blend', 'Multi-Origin Blend' ],
```
`Central and South America blend`, `Latin America blend`, `Latin America, East Africa blend`,
`Latin America, Indonesia blend`, `Brazil, Colombia, Indonesia blend`, `9-country Arabica
blend`, `India, Peru blend`, `Colombia`, `Sumatra`, and `Nicaragua (single origin)` are
already in the map — leave them. Show me the diff for create_beans.php.

## Step 3 — Map reference slugs
Run the reference mapper to attach verified specs where the corpus has them:
```
python scrapers/reference_db.py map scrapers/products.json
```
This fuzzy-suggests a `reference_slug` per product. Apply the suggestions it returns with a
match score at or above 0.75 directly into products.json. For matches between 0.6 and 0.75,
list them for me to confirm — do not auto-apply those. Leave the rest as `reference_slug:
null` (the generator falls back to product fields, which is fine). Show me the summary:
how many got a confident slug, how many need my confirmation, how many stay null.

## Step 4 — Commit the data changes locally
Give me the exact git commands to commit products.json + create_beans.php. One commit.

## Step 5 — Deploy data to the VPS and sync
The VPS pulls scraper files via wget from raw GitHub (it is not a git checkout), then runs
WP-CLI from the WordPress root. Give me the exact SSH command block to:
1. wget the updated `products.json` and `create_beans.php` to `/opt/scrapers/scrapers/`
2. run `sync_products.py` with the venv python to populate the `products` table:
   `/opt/venv/bin/python3 /opt/scrapers/scrapers/sync_products.py`
3. confirm the products table row count matches 80.

## Step 6 — Batch-generate review drafts (this is the main event)
Generate analytical-voice drafts for all 80 beans into `/opt/drafts/`. Write a small bash
loop that reads every `id` from products.json and calls the generator with the venv python,
skipping any id that already has a draft file from today. Use this pattern:

```bash
cd /opt/scrapers/scrapers
for id in $(/opt/venv/bin/python3 -c "import json;print('\n'.join(b['id'] for b in json.load(open('products.json'))))"); do
  out="/opt/drafts/${id}-$(date +%F).md"
  if [ -f "$out" ]; then echo "SKIP $id (draft exists)"; continue; fi
  echo "=== generating $id ==="
  /opt/venv/bin/python3 /opt/scrapers/scrapers/generate_review.py "$id" || echo "FAILED $id"
  sleep 2
done
```
Notes:
- Default (analytical) voice for all of these — none are personally tasted, so do NOT pass
  `--personal`.
- The 2-second sleep spaces out API calls. If the Anthropic key in `/opt/.env` is missing,
  stop and tell me rather than running 80 failures.
- After the loop, report: how many drafts written, which ids FAILED, and the total file
  count in `/opt/drafts/`.

## Step 7 — Push drafts into WordPress as bean posts
Once drafts exist, create/populate the bean CPT posts:
```
cd /var/www/coffeebeans
wp eval-file /opt/scrapers/scrapers/create_beans.php --allow-root
wp eval-file /opt/scrapers/scrapers/push_drafts.php --allow-root
```
`create_beans.php` creates the posts and sets ACF spec/affiliate fields; `push_drafts.php`
parses the markdown drafts into the ACF content fields. Report the create/skip/fail summary
and surface any UNMAPPED ORIGINS or MISSING DB TERMS warnings it prints — those tell me if
Step 2's map or the flavor seeds need another entry.

## Step 8 — Leave everything as drafts for my review
Per project rule, bean posts stay as WordPress drafts after field population. Do NOT publish
anything. Give me a list of the post IDs/slugs created so I can review and publish the
priority 10 myself.

## Final
End with a single summary: beans added, slugs mapped, drafts generated, posts created,
and a clear list of which beans still need (a) ASIN backfill and (b) a 0.6-0.75 reference
slug confirmation from me.
