# Deploy Notes — Theme Rebuild v2.0

Steps to complete after merging and running `deploy-theme`.

---

## 1. GeneratePress Customizer Settings

> **Layout is now enforced in code.** As of the v2.1 layout rework, the `body_class` filter
> in `functions.php` adds `full-width-content cbi-app` to every custom template and
> `style.css` resets `.site-content` to block flow. This makes the heroes full-bleed and
> fixes the desktop column-squeeze **without any Customizer step**. The settings below are
> now optional cosmetic touches, not requirements — a fresh GP install renders correctly.

Go to **Appearance → Customize** only if you want to tune the cosmetic defaults:

### Layout (optional — code already forces full-width on our templates)
- **Container Width**: leave default; our templates override to full-width via body class
- **Content Layout**: "One Column" — no sidebar globally (we also force this per-template)
- **Separate Containers**: Disable if enabled — avoids stray box shadows
- **Boxed Layout**: Off

### Colors
- **Background Color**: `#faf7f3`
- **Text Color**: `#1c1410`
- **Link Color**: `#9e2b0e`
- **Link Hover Color**: `#c03a18`

### Header
- **Header Background**: `#faf7f3`
- **Navigation Background**: transparent
- **Navigation Link Color**: `#5c5048`
- **Navigation Link Hover Color**: `#9e2b0e`

### Footer
- **Footer Background**: `#f2ece3`

### Typography
- **Body Font**: DM Sans (or leave as system font — our CSS overrides it anyway)
- **Heading Font**: Playfair Display (or leave as default — our CSS overrides)

---

## 2. Menus

Create the following menus in **Appearance → Menus**:

### Primary Navigation
Assign to: **Primary Menu** location.

Suggested items:
- Beans → `/beans/`
- Reviews (dropdown): Espresso `/brew/espresso/`, Pour Over `/brew/pour-over/`, French Press `/brew/french-press/`
- Explore (dropdown): By Flavor `/flavor/`, By Origin `/origin/`, By Roast `/roast/`, By Roaster `/roaster/`
- Guides → `/guides/` (category page or a curated page)

### Footer (optional)
If GP has a footer menu location, assign a simple menu with: About, Editorial Standards, Affiliate Disclosure, Privacy Policy.

---

## 3. Pages to Create

Create these pages in **Pages → Add New** and assign the listed template via Page Attributes.

| Page Title | Slug | Template | Notes |
|---|---|---|---|
| About | `/about/` | Default (page.php) | See placeholder copy below |
| Editorial Standards / How We Review | `/editorial-standards/` | Default (page.php) | See placeholder below |
| Affiliate Disclosure | `/affiliate-disclosure/` | Default (page.php) | See placeholder below |
| Privacy Policy | `/privacy-policy/` | Default (page.php) | Use WP's built-in privacy page tool |
| Contact | `/contact/` | Default (page.php) | Add WPForms contact form |

### Placeholder copy — replace before going live

**About page** (`/about/`):
```
[PLACEHOLDER — replace with your own copy]

Coffee Bean Index reviews coffee beans using structured product data, price tracking, and editorial evaluation criteria. Founded in [YEAR].

We track prices on Amazon and from direct roasters daily. Our reviews use a standardised scoring system across sensory profile (acidity, body, sweetness, bitterness, roast intensity) and value for money.

Unless explicitly marked as personal reviews, content should be understood as analytical commentary rather than firsthand consumption experience.

Some content is generated or assisted by AI systems using structured product and review data. All reviews are reviewed and approved by the site editor before publication.

[Add contact information here]
```

**Editorial Standards** (`/editorial-standards/`):
```
[PLACEHOLDER — replace with your own copy]

## How We Review Coffee Beans

Reviews are generated using structured product data, public tasting notes, roast information, and editorial evaluation criteria. Unless explicitly marked as personal reviews, content should be understood as analytical commentary rather than firsthand consumption experience.

## Scoring

Beans are scored 1–10 across: overall quality, value for money, brew versatility, and consistency with stated flavor profile.

## Affiliate Links

This site participates in affiliate programs. We earn commissions on qualifying purchases. Affiliate income does not influence our ratings or recommendations — we note both strengths and weaknesses of every product.

## AI Disclosure

Some content on this site is generated or assisted by AI systems using structured product and review data.

## Price Data

Prices are scraped from Amazon and direct roasters daily. Prices shown may differ from current prices at time of purchase.
```

**Affiliate Disclosure** (`/affiliate-disclosure/`):
```
[PLACEHOLDER — customize for your affiliate programs]

Coffee Bean Index participates in the following affiliate programs:

- Amazon Associates (grocery/coffee category, 4% commission)
- Stumptown affiliate program via ShareASale
- Trade Coffee affiliate program via Impact
- Blue Bottle affiliate program via CJ Affiliate
- Death Wish Coffee affiliate program via ShareASale

We earn commissions on qualifying purchases made through our links, at no additional cost to you. Our reviews are not influenced by affiliate relationships. Products are evaluated on their merits.

All pages containing affiliate links display the disclosure: "This page contains affiliate links. We may earn commissions from qualifying purchases."
```

---

## 4. Homepage Settings

Go to **Settings → Reading**:
- Set "Your homepage displays" to **A static page**
- Homepage: create a blank page titled "Home" (content doesn't matter — front-page.php renders everything)
- Posts page: optional — can be any page or left unset

---

## 5. WPForms — Newsletter Form

1. Go to **WPForms → Add New** → create a simple email sign-up form (Name + Email fields)
2. Connect to Beehiiv via WPForms' email integration or use an embed code from Beehiiv directly
3. Note the form ID (shown in the form list)
4. Add this to your theme's `functions.php` child-theme config, or use a Code Snippets plugin:
   ```php
   add_filter( 'cbi_newsletter_form_id', function() { return '123'; } ); // replace 123
   ```
   Or simply replace the placeholder in `front-page.php` with your shortcode directly.

---

## 6. ACF — Sync Fields

1. After deploying, go to **Custom Fields → Field Groups**
2. If you see a "Sync Available" notice, click **Sync** to import `group_bean_specs.json`
3. Verify that "Tasting Notes" shows as type **Textarea** (not Repeater — the old broken version)

---

## 7. Flush Rewrite Rules

After activating the updated theme:
1. Go to **Settings → Permalinks**
2. Click **Save Changes** (no changes needed — just saving flushes rewrites)
3. Verify `/beans/` resolves, `/flavor/`, `/origin/`, `/roast/`, `/process/`, `/brew/`, `/roaster/` all resolve

---

## 8. RankMath — Schema Conflict Check

1. Go to **RankMath → Titles & Meta → Post Types → Beans**
2. Check the Schema tab — if RankMath is outputting `Product` schema on beans, disable it (our `cbi_bean_schema()` handles it correctly with `Review` and `Offer`)
3. For Pages: RankMath Article schema is fine — our page templates also output Article but confirm there's no duplication in the HTML source

---

## 9. WP Rocket / Caching

After deploy:
1. Clear all caches in your caching plugin
2. If using WP Rocket, check that it is not combining/minifying our Google Fonts URL (it should detect wp_enqueue_style)
3. Test Core Web Vitals in PageSpeed Insights on the homepage and one bean page

---

## 10. Visual Verification Checklist

Walk through these pages on the live site after deploy:

- [ ] Homepage: paper-white background, oxblood accent, two-column hero, stat blocks, browse chips, review cards with SVG coffee placeholder (no ☼ symbol)
- [ ] Single bean: breadcrumb, large title, verdict pull-quote, rating badge (oxblood, not dark), spec table, sensory bars in oxblood, radar chart (light colors), tasting notes with dash markers, buy box, similar beans list
- [ ] `/beans/` archive: sort bar works (rating, price, name, date sort), bean grid, pagination
- [ ] Taxonomy archive (e.g., `/flavor/dark-chocolate/`): archive hero, description, bean grid
- [ ] Generic page (About): centered column, editorial typography
- [ ] Header: paper-white background, nav links in warm grey, oxblood on hover
- [ ] Footer: four-column grid, disclosure at top, links in warm grey

---

## 11. Content to Add (first 10 pages per CLAUDE.md priority list)

1. Lavazza Super Crema — add as Bean CPT
2. Best Espresso Beans Under $20 — Page with template-roundup.php
3. Illy Classico — add as Bean CPT
4. Ethiopian Coffee taste guide — Page with template-guide.php
5. Death Wish Coffee — add as Bean CPT
6. Best Dark Roast Coffee Beans — Page with template-roundup.php
7. Stumptown Hair Bender — add as Bean CPT
8. French Press Coffee Beans guide — Page with template-guide.php
9. Peet's Major Dickason's — add as Bean CPT
10. Blue Bottle Hayes Valley — add as Bean CPT
