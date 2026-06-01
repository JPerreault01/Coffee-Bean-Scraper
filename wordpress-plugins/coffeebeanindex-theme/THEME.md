# Coffee Bean Index — Theme Design System

## Art Direction: Print-Inspired Editorial

**Decision**: Warm paper/off-white base, near-black espresso text, oxblood accent.

**Why**: The previous dark amber-on-near-black aesthetic read as a tech demo, not an editorial publication. The print editorial direction (inspired by Standart Magazine, NYT Cooking, Serious Eats) communicates trust, permanence, and editorial authority — the qualities that make a roaster want to be reviewed here and a reader trust the recommendations.

**Not chosen**: Refined dark mode — rejected because the existing dark implementation had a "tech demo" feel that would require the same effort to fix. The light editorial direction has a lower floor and a higher ceiling.

---

## Design Tokens (`style.css :root`)

### Palette
| Token | Value | Use |
|---|---|---|
| `--cbi-bg` | `#faf7f3` | Page background (warm paper) |
| `--cbi-bg-2` | `#f2ece3` | Hero sections, header |
| `--cbi-bg-3` | `#e8e0d5` | Deeper section backgrounds |
| `--cbi-surface` | `#ede8df` | Card surfaces, sidebar |
| `--cbi-border` | `#d4c9bb` | Hairline borders |
| `--cbi-border-light` | `#e2d8cc` | Lighter borders |
| `--cbi-text` | `#1c1410` | Near-black espresso text |
| `--cbi-text-muted` | `#5c5048` | Body copy, descriptions |
| `--cbi-text-dim` | `#9c8e82` | Metadata, captions, labels |
| `--cbi-accent` | `#9e2b0e` | Oxblood — primary accent |
| `--cbi-accent-light` | `#c03a18` | Hover state |
| `--cbi-accent-dark` | `#7a2008` | Active/pressed |
| `--cbi-accent-bg` | `#fdf1ee` | Very light tint for hover states |
| `--cbi-accent-glow` | `rgba(158,43,14,0.08)` | Subtle background tint |

### Typography
| Token | Value |
|---|---|
| `--font-display` | Playfair Display, Georgia, serif |
| `--font-body` | DM Sans, system-ui, sans-serif |
| `--font-mono` | DM Mono, Courier New, monospace |

**Fonts loaded** via `wp_enqueue_scripts()` in functions.php with `preconnect` hints — not @import in style.css (would be render-blocking).

**Tabular numerals**: Use `font-family: var(--font-mono)` or `font-variant-numeric: tabular-nums` for all prices, ratings, and numeric data.

### Type Scale
```
--text-xs:   0.75rem    (labels, metadata, tags)
--text-sm:   0.875rem   (captions, card text)
--text-base: 1rem       (body text)
--text-lg:   1.125rem   (larger body, card titles)
--text-xl:   1.25rem    (h4, sub-headings)
--text-2xl:  1.5rem     (h3, section heads)
--text-3xl:  2rem       (h2, page sections)
--text-4xl:  2.75rem    (h2 large)
--text-5xl:  3.75rem    (h1, hero titles)
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
| Rating badge | `.bean-rating`, `.cbi-rating-badge` | |
| Sensory bars | `cbi_sensory_bar()` PHP helper | |
| Spec table | `.bean-specs`, `.bean-specs__row` | |
| Tasting notes | `.tasting-notes` | List, dash before each item |
| Buy box | `.buy-box` | Sticky sidebar |
| Similar beans | `.similar-beans`, `.similar-bean-card` | |
| Bean card | `cbi_bean_card()` PHP helper | |
| Archive grid | `.bean-grid` | Auto-fill, min 280px |
| Sort bar | `.sort-bar` | URL-based, no JS required |
| FAQ accordion | `.cbi-faq`, `.cbi-faq__item` | `<details>/<summary>`, no JS |
| Comparison table | `.comparison-table`, `.vs-table` | |
| Roundup pick | `.roundup-pick` | |
| TOC | Built via JS in template-guide.php | Targets H2s |
| Pagination | `.cbi-pagination` | |

---

## GeneratePress Integration

**Approach**: Configure GP Customizer to use our paper-white background and remove default content padding on custom templates. We override specific GP elements with targeted selectors, not blanket !important blocks.

**GP settings required** (documented in DEPLOY_NOTES.md):
- Container: Full Width
- Content width: unconstrained on custom templates
- Default background color: `#faf7f3`
- Disable sidebar globally
- Disable default page header on bean/archive/taxonomy pages

**Hooks used**:
- `generate_footer` — custom footer HTML
- `generate_show_title` — hide GP page title on custom templates (we render our own H1)
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
