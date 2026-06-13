# Taxonomy Hub Pages — Extension & Maintenance Notes

The five taxonomy **hub** roots are the index pages that sit ABOVE the term archives:

| Hub URL | Taxonomy (name) | Rewrite base | H1 |
|---|---|---|---|
| `/origin/`  | `origin`         | `origin`  | Coffee Origins |
| `/flavor/`  | `flavor-note`    | `flavor`  | Coffee Flavor Notes |
| `/brew/`    | `brew-method`    | `brew`    | Coffee Brewing Methods |
| `/process/` | `process-method` | `process` | Coffee Processing Methods |
| `/roast/`   | `roast-level`    | `roast`   | Coffee Roast Levels |

> The rewrite **base** is the URL slug and is NOT always the taxonomy name
> (`roast-level` serves at `/roast/`, `process-method` at `/process/`). Verified
> against `cbi_register_taxonomies()` in functions.php §3.

**How it works (functions.php §24):** a rewrite rule maps
`^(origin|flavor|brew|process|roast)/?$` to `?cbi_hub=<base>`; `template_include`
then loads `taxonomy-hub-base.php`, a single renderer driven by `cbi_hub_config()`.
A bare hub root resolves as the WordPress home query (no queried object), so a
`redirect_canonical` filter stops `/origin/` redirecting to the front page, and the
title/description/canonical are set for both core and RankMath.

**After any change to the rewrite rule you MUST flush:**
```bash
wp rewrite flush --hard --path=/var/www/coffeebeans --allow-root
```
The hub roots 404 until this runs.

---

## Section map (taxonomy-hub-base.php)

| # | Section | Renders when | Source |
|---|---|---|---|
| 1 | Hero + intro | always | intro HTML (before the `<!-- cbi:faq -->` marker) |
| 2 | Term grid | always | live `get_terms()` |
| 3 | Highest-rated beans | >=1 published `bean` in the taxonomy | `WP_Query` (tax EXISTS, rating desc) |
| 4 | Best-of rankings | >=1 matching roundup page | meta `cbi_hub_taxonomy` |
| 5 | Guides & explainers | >=1 matching guide page | meta `cbi_hub_taxonomy` |
| 6 | Machines / equipment | `post_type_exists('machine')` + match | meta `cbi_hub_taxonomy` |
| 7 | Accessories | `post_type_exists('accessory')` + match | meta `cbi_hub_taxonomy` |
| 8 | FAQ accordion | always | intro HTML (after the `<!-- cbi:faq -->` marker) |

Every conditional section runs its query **first** and emits nothing if empty. No
"coming soon" shells. Pages light up automatically as content lands.

---

## Activating Section 4 (Best-of rankings) and Section 5 (Guides)

These are live now. To surface a page on a hub, add ONE custom field to the page:

- **Field name:** `cbi_hub_taxonomy`
- **Field value:** the **taxonomy name** (NOT the base) — one of:
  `origin`, `flavor-note`, `brew-method`, `process-method`, `roast-level`

The page must also be using the right template:
- Section 4 pulls pages on **`template-roundup.php`** ("Best-of Roundup").
- Section 5 pulls pages on **`template-guide.php`** ("Origin / Brew Guide").

### Example (WP-CLI on the VPS)
Tag the "Best Dark Roast Coffee Beans" roundup onto the Roast hub:
```bash
# find the page ID
wp post list --post_type=page --fields=ID,post_title --path=/var/www/coffeebeans --allow-root
# tag it (value is the taxonomy name, roast-level, not the base 'roast')
wp post meta update <PAGE_ID> cbi_hub_taxonomy roast-level --path=/var/www/coffeebeans --allow-root
```
No template edit, no flush. Reload `/roast/` and the section appears (cache permitting).

### Example (in the editor, non-dev)
Edit the page → enable the **Custom Fields** panel (Options → Preferences → Panels)
→ add field `cbi_hub_taxonomy` with value `roast-level` → Update.

A single page can only carry one `cbi_hub_taxonomy` value, so it appears on one hub.
To feature the same roundup on two hubs, duplicate the meta is not supported by the
current `meta_query`; instead pick the hub where it belongs, or extend the query to
an `IN` comparison if multi-hub becomes a need.

---

## Activating Section 6 (Machines) and Section 7 (Accessories) — FUTURE

These no-op cleanly today: the template checks `post_type_exists('machine')` /
`post_type_exists('accessory')` and renders nothing until those post types exist. To
turn them on later with **zero edits to `taxonomy-hub-base.php`**:

1. **Register the post type** (in functions.php, mirroring the `bean` CPT in §2):
   ```php
   register_post_type( 'machine', [
       'labels'      => [ 'name' => 'Machines', 'singular_name' => 'Machine' ],
       'public'      => true,
       'has_archive' => true,
       'rewrite'     => [ 'slug' => 'machines', 'with_front' => false ],
       'supports'    => [ 'title', 'editor', 'thumbnail', 'excerpt', 'custom-fields' ],
   ] );
   ```
   (Use `'accessory'` / slug `accessories` for Section 7.)

2. **Flush rewrites once** after registering:
   ```bash
   wp rewrite flush --hard --path=/var/www/coffeebeans --allow-root
   ```

3. **Tag each machine/accessory** with the same linkage field the roundups use:
   - Field `cbi_hub_taxonomy` = the taxonomy name (e.g. `brew-method` for an
     espresso machine on the `/brew/` hub).

That is it. The hub query (`post_type` = `machine`, meta `cbi_hub_taxonomy` = the
taxonomy) and the card layout already exist in Sections 6-7. The `sections` toggle in
`cbi_hub_config()` is already `true` for every hub, so the block appears the moment a
matching, published machine/accessory exists.

> **Alternative linkage (taxonomy instead of post type):** if you prefer to model
> equipment as a taxonomy on the `bean` CPT rather than its own post type, swap the
> `post_type_exists()` gate for `taxonomy_exists('equipment-type')` and adjust the
> query. The card render (`$render_doc_card`) is post-type agnostic and needs no change.

---

## Editing hub copy WITHOUT a redeploy

Hub copy and FAQ schema live in `wp_options`, so you can edit them over WP-CLI without
touching the theme files or re-running an scp deploy. Each hub has two options, keyed
by **base**:

| Option | Holds | Bundled fallback file |
|---|---|---|
| `cbi_hub_content_<base>`     | intro paragraphs + `<!-- cbi:faq -->` marker + `.cbi-faq` accordion | `hubs/<base>.intro.html` |
| `cbi_hub_faq_schema_<base>`  | standalone FAQPage JSON-LD | `hubs/<base>.faq.schema.json` |

If an option is empty, the template/head fall back to the bundled theme file, so a
fresh deploy is never blank. To edit copy live:
```bash
# replace the Origin hub intro + FAQ from an edited local file
wp option update cbi_hub_content_origin "$(cat origin.intro.html)" --path=/var/www/coffeebeans --allow-root
# and keep the JSON-LD answer text BYTE-FOR-BYTE identical to the accordion answers
wp option update cbi_hub_faq_schema_origin "$(cat origin.faq.schema.json)" --path=/var/www/coffeebeans --allow-root
```

**Hard rules when editing FAQ content:**
- The `<p>` answer text inside each `.cbi-faq__answer` must match the corresponding
  `acceptedAnswer.text` in the JSON-LD **byte for byte**, or Google treats it as schema
  spam. Edit both together.
- No em-dashes or en-dashes anywhere (house rule, also enforced by `strip_dashes()` in
  the Python pipeline). Use periods, commas, colons, or parentheses.
- The intro content must NOT contain an `<h1>` — the template emits the single H1.
- Allowed tags are limited to the kses set in `cbi_hub_kses_allowed()`
  (p, br, strong, em, a, h2, h3, ul, ol, li, table family, div, span, details, summary).

---

## Adding a sixth hub later

1. Confirm the taxonomy's rewrite base in `cbi_register_taxonomies()` (functions.php §3).
2. Add an entry to `cbi_hub_config()` keyed by that base (taxonomy, h1, eyebrow, title,
   description, sections).
3. The rewrite regex in `cbi_register_hub_rewrites()` is built from
   `array_keys( cbi_hub_config() )`, so it picks the new base up automatically.
4. Add `hubs/<base>.intro.html` and `hubs/<base>.faq.schema.json`, scp the theme, and
   `wp rewrite flush --hard`.
5. Seed the options and add the nav item pointing at `/<base>/`.

---

## Gotcha: the nav menu must point at the BASE, not the taxonomy name

The Phase 4 nav seed historically pointed "Roasts" at `/roast-level/` and "Process
Methods" at `/process-method/` — both 404, because those are the taxonomy NAMES, not the
rewrite bases. Hub (and term-archive) URLs use the base: `/roast/`, `/process/`. After
any nav rebuild, verify every dropdown parent resolves:
```bash
wp menu item list "Primary Navigation" --fields=db_id,title,url --path=/var/www/coffeebeans --allow-root
```
