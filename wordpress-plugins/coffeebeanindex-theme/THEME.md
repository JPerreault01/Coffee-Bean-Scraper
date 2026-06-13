

# Coffee Bean Index — Theme Design System

## Art Direction: Dark Data-Driven Review Database (v3.0)

**Decision**: Roasted near-black base, cream text, oxblood accent, monospace display type.

**Why**: The site is a database, not a blog. The v3.0 dark direction (reference points: Fragrantica's interconnected profile pages, CamelCamelCamel's price-history utility, HouseFresh's independent-tester credibility, Wirecutter's CTA discipline) makes the data the hero — score badges, spec tables, price charts, and taxonomy chips read as instruments on a dark instrument panel. Monospace display type signals "structured data" the way a serif signaled "editorial" in v2.

**The score is a system, not a number.** `cbi_score_badge()` renders a banded badge (value + `/10` + band label). Bands: Exceptional 9.0+ (gold ring), Excellent 8.0+, Very good 7.0+ (oxblood fill), Good 6.0+, Mixed 5.0+ (neutral fill), Skip <5.0 (outline only). Weak scores never wear the brand color.

**Two accent roles.** Oxblood (`--cbi-accent` `#9e2b0e`) is for FILLED surfaces only (buttons, badges) with white text. `--cbi-accent-text` (`#e8714c`, ember) is the link/text accent — oxblood is too dark to pass WCAG AA as text on the dark background, ember clears it.

**Superseded**: the v2.0 warm-paper "print editorial" direction (Playfair Display, `#faf7f3` paper). Retired because the brief called for a serious data-driven database register; the light editorial look read as a recipe blog.

---

## Design Tokens (`style.css :root`)

### Palette (dark, v3.0)
| Token | Value | Use |
|---|---|---|
| `--cbi-bg` | `#14100c` | Page background (warm near-black) |
| `--cbi-bg-2` | `#1a1410` | Raised bands, hero gradient top, header/nav |
| `--cbi-bg-3` | `#241c15` | Deepest panels |
| `--cbi-surface` | `#1d1712` | Card surface |
| `--cbi-surface-2` | `#271f17` | Card headers, spec-table label column |
| `--cbi-border` | `#3a2e22` | Hairline borders |
| `--cbi-border-light` | `#2b2219` | Inner / lighter borders |
| `--cbi-text` | `#f0e9df` | Primary cream text |
| `--cbi-text-muted` | `#c7b9a8` | Body copy, descriptions (AA) |
| `--cbi-text-dim` | `#9d8e7d` | Metadata, captions, labels (AA) |
| `--cbi-accent` | `#9e2b0e` | Oxblood — FILLS only (buttons, badges) |
| `--cbi-accent-light` | `#c13a14` | Fill hover / border |
| `--cbi-accent-text` | `#e8714c` | Ember — link + text accent (AA) |
| `--cbi-accent-text-2` | `#f08a67` | Text accent hover |
| `--cbi-accent-bg` | `rgba(158,43,14,0.16)` | Tint for hover states |
| `--cbi-positive` | `#79c47e` | Price drops |
| `--cbi-negative` | `#e07a6d` | Price rises |
| `--cbi-gold` | `#d9a456` | Exceptional band ring, flavor chip tint |

Category chip tints: `--tint-flavor` gold, `--tint-origin` green, `--tint-roast` orange, `--tint-brew` blue (all ≥ 4.5:1 on the surface).

### Typography
| Token | Value |
|---|---|
| `--font-display` | DM Mono, ui-monospace, monospace |
| `--font-body` | DM Sans, system-ui, sans-serif |
| `--font-mono` | DM Mono, ui-monospace, monospace |

**Mono is the identity** (display headings + all data). Body prose uses DM Sans at a constrained measure (`--measure: 70ch`) for readability — mono is never used for long paragraphs. Playfair Display was removed from the font enqueue in v3.0.

**Fonts loaded** via `wp_enqueue_scripts()` in functions.php with `preconnect` hints — not @import in style.css (would be render-blocking).

**Tabular numerals**: Use `font-family: var(--font-mono)` or `font-variant-numeric: tabular-nums` for all prices, ratings, and numeric data.

### Type Scale
```
--text-2xs:  0.6875rem  (denominators, band labels, micro-meta)
--text-xs:   0.75rem    (labels, metadata, tags)
--text-sm:   0.875rem   (captions, card text)
--text-base: 1rem       (body text)
--text-md:   1.0625rem  (review/prose body)
--text-lg:   1.125rem   (larger body, leads)
--text-xl:   1.25rem    (h4, sub-headings)
--text-2xl:  1.5rem     (h3, section heads)
--text-3xl:  1.875rem   (h2, page sections)
--text-4xl:  2.375rem   (h2 large)
--text-5xl:  3rem       (h1, hero titles)
```

### Spacing Scale
Based on 0.25rem units: `--space-1` through `--space-24` (0.25rem → 6rem).

### Layout
- `--max-width: 1200px` — site container
- `--content-width: 720px` — editorial text column
- `--radius: 3px`, `--radius-lg: 6px` — minimal, not bubbly

---

## Information Architecture

```
/ (homepage)
├── /beans/               → archive-bean.php (all-beans index)
│   └── /beans/[slug]/    → single-bean.php (full review)
├── /flavor/[slug]/       → taxonomy-bean-archive.php
├── /origin/[slug]/       → taxonomy-bean-archive.php
├── /roast/[slug]/        → taxonomy-bean-archive.php
├── /process/[slug]/      → taxonomy-bean-archive.php
├── /brew/[slug]/         → taxonomy-bean-archive.php
├── /roaster/[slug]/      → taxonomy-bean-archive.php
├── /best-espresso-beans/ → template-roundup.php (Page template)
├── /lavazza-vs-illy/     → template-comparison.php (Page template)
├── /ethiopia-coffee/     → template-guide.php (Page template)
├── /about/               → page.php
├── /affiliate-disclosure/→ page.php
├── /editorial-standards/ → page.php
├── /privacy-policy/      → page.php
└── /[slug]/              → page.php (default)
```

---

## Template Map

| Template File | When It Loads |
|---|---|
| `front-page.php` | Homepage (any Reading setting) |
| `single-bean.php` | Individual bean review (`post_type=bean`) |
| `archive-bean.php` | `/beans/` all-beans index |
| `taxonomy-bean-archive.php` | All six taxonomy archives |
| `template-roundup.php` | "Best of" pages (Page template) |
| `template-comparison.php` | "X vs Y" pages (Page template) |
| `template-guide.php` | Origin guides, brew guides (Page template) |
| `page.php` | All other WordPress pages |
| `single.php` | Standard blog posts |

---

## Component Inventory

| Component | Class(es) | Notes |
|---|---|---|
| Buttons | `.cbi-btn`, `--primary`, `--secondary`, `--ghost` | |
| Tags/chips | `.bean-tag`, `--flavor`, `--origin`, `--roast`, `--brew` | |
| Breadcrumb | `.cbi-breadcrumb` | Also outputs BreadcrumbList JSON-LD |
| Section heading | `.cbi-section__heading` | Label style, uppercase mono |
| Affiliate disclosure | `.cbi-disclosure-inline` | Inline, near affiliate links |
| Image placeholder | `cbi_coffee_placeholder()` | SVG coffee cup, no emoji |
| **Score badge** | `cbi_score_badge($rating, $size, $show_band)` + `cbi_score_band()` | Banded rating system. Sizes `xl`/`md`/`sm`. Bands map to `.cbi-score--{exceptional…skip}`. Use this, not raw numbers |
| Rating badge (legacy) | `.bean-rating`, `.cbi-rating-badge` | Pre-v3 fixed badge; kept for back-compat, prefer `cbi_score_badge()` |
| **Fit cards** | `.fit-cards`, `.fit-card`, `.fit-card--skip` | Buy it if / Skip it if, side by side (green/red left border) |
| **Price delta** | `.price-delta`, `--down`, `--up` | Pill for price vs 30-day avg |
| **Hero decision panel** | `.bean-hero__panel` | Score + price + CTA above the fold in the bean hero |
| **Sticky mobile CTA** | `.bean-ctabar` | Fixed bottom bar (price + buy) under 1025px |
| Sensory bars | `cbi_sensory_bar()` PHP helper | |
| Spec table | `.bean-specs`, `.bean-specs__row` | |
| Profile card | `.bean-profile`, `.bean-profile__col`, `.bean-profile__viz` | 2-col (specs \| sensory+radar); `--specs-only` collapses to 1 col; stacks <760px |
| At-a-glance | `.glance-card`, `.glance`, `.glance__row` | Sidebar quick-scan dl (rating/roast/origin/price) |
| Tasting notes | `.tasting-notes` | List, dash before each item |
| Buy box | `.buy-box` | Lives inside the sticky `.bean-sidebar` rail |
| Sticky rail | `.bean-sidebar` | `position:sticky` flex column: buy box → at-a-glance → similar → roaster/origin; static <1024px |
| Similar beans | `.similar-beans`, `.similar-bean-card` | |
| Bean card | `cbi_bean_card()` PHP helper | |
| Archive grid | `.bean-grid` | Auto-fill, min 280px |
| Sort bar | `.sort-bar` | URL-based, no JS required |
| FAQ accordion | `.cbi-faq`, `.cbi-faq__item` | `<details>/<summary>`, no JS |
| Comparison table | `.comparison-table`, `.vs-table` | |
| Roundup pick | `.roundup-pick` | |
| Card grid | `.cbi-card-grid` | Reusable 3/2/1 grid; wraps `cbi_bean_card()`. Used by homepage "Latest reviews" + guide "Related beans" |
| Bean card | `cbi_bean_card()` | Now renders rating **and** price/oz in the footer |
| Guide ToC | `js/guide-toc.js` | Scans `.guide-body h2,h3`; sticky left rail ≥1100px, tap-to-expand on mobile; active-section highlight + smooth scroll |
| Guide callout | `.guide-callout` (`--tip/--note/--warning`) | Via `[cbi_callout]` shortcode |
| Pull quote | `.guide-pullquote` | Via `[cbi_pullquote]` shortcode |
| Inline bean | `.cbi-bean-inline` | Via `[cbi_bean]` shortcode — works in guides and reviews |
| Pagination | `.cbi-pagination` | |

### Editor shortcodes (defined in functions.php §21, documented in its top comment)

| Shortcode | Purpose |
|---|---|
| `[cbi_callout type="tip\|note\|warning" title="…"]…[/cbi_callout]` | Styled tip/callout box |
| `[cbi_pullquote cite="…"]…[/cbi_pullquote]` | Emphasis pull quote |
| `[cbi_bean id="123"]` / `[cbi_bean slug="…"]` | Inline linked bean mention (live data) |

Matching **block patterns** ("Guide callout box", "Inline bean mention") are
registered under the "Coffee Bean Index" pattern category for visual insertion.

### Image drop-in points (placeholders — supply optimised JPG/WebP, never hotlink)

| Location | CSS hook | Recommended size |
|---|---|---|
| Homepage hero background | `.cbi-hero__bg` (injected by `cbi_hero_head()` from `cbi_home_image_ids`) | 2400×1200px (2:1) |
| Category cards | `.cbi-cat__img` (resolved via `cbi_home_image_url()`) | 600×400px (3:2) |
| Bean / guide thumbnails | WordPress featured image | 1200×900px (4:3 card crop) |

---

## GeneratePress Integration

**Approach**: Our custom templates own their layout end-to-end. Rather than depend on
manual GP Customizer settings, the layout contract is enforced in code so a fresh GP
install renders correctly with no Customizer steps.

### The layout contract (THE critical detail)

GeneratePress makes `#content.site-content` a flex container whose `flex-direction` is
**`row` on desktop** and only `column` at `<=768px`. GP assumes a *single* `.content-area`
child. Our custom templates `get_header()` then emit **several** direct children of
`.site-content` (full-bleed hero band, affiliate disclosure, content container). At desktop
GP squeezed those into cramped side-by-side columns — the bean page's spec/sensory/radar
collapsed into a ~280px column and the buy rail detached. (Confirmed via computed styles:
`#content.site-content { display:flex; flex-direction:row }`.)

The fix has two halves:
1. **`functions.php` `body_class` filter** adds two classes to every custom template:
   - `full-width-content` → triggers GP's own rules that drop the 1200px `.grid-container`
     cap and the 40px `.site-content` padding, so heroes render full-bleed.
   - `cbi-app` → the hook for our CSS reset.
2. **`style.css`** `.cbi-app #content.site-content { display:block; padding:0 }` — GP has no
   body class that unsets the flex row, so CSS does that half. `.cbi-app .site.grid-container
   { max-width:100% }` is the GP-internal-independent backstop (targets only `#page`, so the
   masthead keeps its contained measure).

With `.site-content` back to block flow, our own `.cbi-container` / hero `__inner`
(max-width 1200, centered) are the single source of width truth on every template.

**No GP Customizer changes are required.** Setting Container → Full Width in the Customizer
is now redundant (the body class does it); paper background + link colors there are cosmetic
nice-to-haves only.

**Stylesheet loading**: our `style.css` is enqueued once (handle `cbi-child`, depends on
`generate-style`) so it cascades after GP's `main.css`. GP's automatic duplicate child
enqueue (`generate-child`) is dequeued in `cbi_dequeue_duplicate_child_css()`.

**Hooks used**:
- `body_class` — add `cbi-app` + `full-width-content` to custom templates (layout contract)
- `generate_footer` — custom footer HTML
- `generate_show_title` — hide GP page title on custom templates (we render our own H1)
- `generate_sidebar_layout` / `generate_content_width` — force no-sidebar + full width
- `template_include` — route taxonomy archives to our template

---

## ACF Fields

All fields use **ACF Free** types only. See `acf-json/group_bean_specs.json` for the full schema.

Key fix: `tasting_notes` changed from `repeater` (PRO-only) to `textarea` (one note per line). Templates split on `\n`.

---

## SEO / Schema

| Template | JSON-LD Types |
|---|---|
| All pages | `WebSite`, `Organization` (via `cbi_site_schema()`) |
| `single-bean.php` | `Product`, `Review`, `AggregateRating`, `Offer` |
| `archive-bean.php` | `ItemList` |
| `template-guide.php` | `Article` |
| `template-roundup.php` | `Article` |
| `template-comparison.php` | `Article` |
| `taxonomy-bean-archive.php` | `BreadcrumbList` (via `cbi_breadcrumb()`) |

**RankMath compatibility**: Our schema outputs are for types RankMath does not typically generate (`Product`, `ItemList`). Bean-level schema uses `Product` which RankMath may also generate — check RankMath schema settings on the bean CPT and disable its Product schema if there is a conflict. RankMath should continue to handle `Article` on guides; our `Article` schema is only in our page templates so check for duplicates.

---

## Performance Notes

- Fonts: enqueued via `wp_enqueue_scripts` with `preconnect` — not render-blocking @import
- Chart.js: loaded only on `single-bean.php` via conditional enqueue
- Images: `loading="lazy"` + explicit `width`/`height` on all `get_the_post_thumbnail()` calls to prevent CLS
- Bean card images: `aspect-ratio: 16/9` on the image container prevents layout shift for missing thumbnails
- `prefers-reduced-motion`: animation duration set to 0 in the radar chart JS + CSS media query kills all transitions

---

## Maintenance

**Adding a new taxonomy**: Register in `cbi_register_taxonomies()`. Add it to `$our_taxes` in `cbi_taxonomy_template()`. Add a body class to the `taxonomy-bean-archive.php` hero eyebrow map. No CSS changes needed.

**Adding a new ACF field**: Add to `acf-json/group_bean_specs.json` using only free field types. ACF will sync on next admin load. Update `single-bean.php` to render it.

**Updating colors**: Change the `--cbi-*` custom properties in `:root`. All components reference the tokens — one edit updates everywhere.

**New page templates**: Create `template-[name].php` with the WordPress `Template Name:` comment. Assign via Page Attributes in the editor. Add the template filename to `cbi_hide_title_on_custom_templates()` in functions.php.

---

## v2.1 — Guide system + homepage redesign

**Guide pages** (`template-guide.php`, selectable Page template):
- Assign via editor → Page panel → Template → "Origin / Brew Guide".
- Body class `.guide-page` (added in functions.php `cbi_template_body_classes`)
  scopes all guide CSS so it can't leak into reviews.
- ToC auto-builds from `.guide-body h2,h3` via `js/guide-toc.js` (enqueued only
  on the guide template). Sticky left rail ≥1100px; tap-to-expand on mobile;
  IntersectionObserver active-section highlight; smooth scroll (reduced-motion aware).
- **Related beans**: `cbi_guide_related_beans()` queries the Bean CPT for beans
  sharing a taxonomy term with the guide (auto-matched from the page slug/title,
  e.g. `/ethiopia-coffee/` → origin "ethiopia"; override with ACF text field
  `related_taxonomy_slug`, comma-separated term slugs). Cards, rating desc, max 6.
- **Related guides**: `cbi_get_guides()` lists sibling guide-template pages.

**Homepage** (`front-page.php`): 6 sections — full-bleed hero (search + 2 CTAs),
latest reviews (`.cbi-card-grid`), browse-by-category tiles (Roast/Origin/Brew —
the authority-distribution section), price-drop strip, guides grid, email band.
- **Price drops**: `cbi_price_drop_beans()` returns `[]` until the scraper feeds
  it; renders a placeholder meanwhile. Wire via the `cbi_price_drop_beans` filter
  returning rows `[ 'post_id'=>int, 'current'=>float, 'avg30'=>float, 'pct'=>int ]`.
