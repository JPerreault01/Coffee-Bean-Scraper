# Coffee Bean Index — SEO Playbook

> **This is the standing operating doc.** Update it when strategy changes. Run it before touching any content.

---

## 1. Two-Plugin Division of Labor

| Layer | Tool | Use for |
|---|---|---|
| **Technical SEO** | `claude-seo` (AgriciDaniel) | `seo-technical` (Core Web Vitals, crawlability, JS rendering), `seo-schema` (validate JSON-LD), `seo-page` / `seo-audit` (per-URL deep dive), `seo-sxo` (page type vs. intent), `seo-images`, `seo-sitemap`. Orchestrate via `seo-flow`. |
| **Strategy + content** | `rampstack-skills` (RampStack) | `editorial-qa` (pre-publish gate), `content-refresh-system`, `seo-onpage` (8-dimension pass), `pillar-content-architecture`, `programmatic-seo`, `information-architecture`, `cro-optimization`, `accessibility-audit`, `design-system`. |

**Rule:** `rampstack` decides *what* and *why*. `claude-seo` executes the technical *how* and validates markup. When both could audit the same thing, run `claude-seo seo-technical` for the machine pass and `rampstack seo-onpage` / `editorial-qa` for the human-judgment pass. Never run two overlapping keyword audits on the same page.

---

## 2. Per-Content-Type Requirements

### Individual Review (`single-bean.php`)
**Target intent:** `[brand] [product] review`, `[product] taste`, `buy [product]`

| Requirement | Detail |
|---|---|
| Schema | `Product` + `Review` + `AggregateRating` + `Offer` + `BreadcrumbList` + `FAQPage` |
| Internal links | ≥1 origin guide, ≥1 roast-level guide, roaster taxonomy archive |
| Meta title | `[Product] Review — [Roaster] \| Coffee Bean Index` |
| FAQ | 3 questions: taste, who it's for, who to skip |
| Price | Must show current price + price/oz in specs table |
| Affiliate disclosure | Near top (FTC requirement) |
| Update trigger | Price formulation change OR 12+ months since last review |

### "Best X for Y" Roundup (`template-roundup.php`)
**Target intent:** `best espresso beans under $20`, `best dark roast coffee`

| Requirement | Detail |
|---|---|
| Schema | `Article` + `ItemList` (one ListItem per pick) + `BreadcrumbList` + `FAQPage` |
| Internal links | Link each pick to its full individual review (`single-bean.php`) |
| Meta title | `Best [X] for [Y] (2025) — Coffee Bean Index` |
| Content ratio | ≥60% editorial judgment, ≤40% affiliate CTAs |
| Affiliate disclosure | Near top |
| Update trigger | Any pick drops in rating or goes out of stock; annually otherwise |

### Origin / Brew Guide (`template-guide.php`)
**Target intent:** `Ethiopian coffee taste`, `how to brew French press`

| Requirement | Detail |
|---|---|
| Schema | `Article` + `BreadcrumbList` |
| Internal links | ≥3 beans tagged with this origin/brew method |
| Meta title | `[Origin] Coffee: Flavor, Origins & Best Beans \| Coffee Bean Index` |
| Word count | ≥800 words (informational; protects 40% informational ratio) |
| Affiliate disclosure | Only if affiliate links appear (some guides have none) |
| Update trigger | Major taste-profile or supply-chain shift; 12 months otherwise |

### Comparison (`template-comparison.php`)
**Target intent:** `[Product A] vs [Product B]`

| Requirement | Detail |
|---|---|
| Schema | `Article` + `BreadcrumbList` |
| Internal links | Full review of each product; 1 origin guide |
| Meta title | `[A] vs [B]: Which Should You Buy? \| Coffee Bean Index` |
| Verdict | Must declare a clear winner; no hedging |
| Affiliate disclosure | Near top |

### Taxonomy Archive (`taxonomy-bean-archive.php`)
**Target intent:** `[flavor] coffee`, `[origin] coffee beans`, `[roast] roast coffee`

| Requirement | Detail |
|---|---|
| Schema | `BreadcrumbList` + `ItemList` (queried beans) |
| Term description | Should be ≥150 words of guide prose (fills `.guide-body`) |
| Internal links | Cross-taxonomy "Also browse" chips (auto-generated) |
| Update trigger | Term description goes stale; add when count ≥3 beans |

### Price Tracker Page
**Target intent:** Returning visitors, `[product] price drop`

| Requirement | Detail |
|---|---|
| Schema | Same as individual review (it IS the review + tracker) |
| Chart | Chart.js price history via `[coffee_price_chart]` shortcode |
| Update | Prices auto-update via scraper; review text only on formulation change |

---

## 3. New Bean Pre-Publish Checklist

Run **before** setting a bean page to Published. Full gate is in `PREPUBLISH_CHECKLIST.md`.

Quick checks:
- [ ] `verdict` field filled (required by ACF)
- [ ] `rating` field filled (required by ACF)
- [ ] At least one taxonomy term in each of: origin, roast-level, brew-method
- [ ] `amazon_affiliate_url` OR `roaster_url` filled (no buy links = no affiliate value)
- [ ] `product_id` matches a row in `products.json` (required for price chart)
- [ ] Featured image set
- [ ] RankMath meta title + description set

---

## 4. New Guide / Roundup Pre-Publish Checklist

- [ ] Term description or page content ≥400 words
- [ ] At least 3 internal links to bean review pages
- [ ] If roundup: each pick has a full review; `Article` + `ItemList` schema present
- [ ] If guide: `Article` schema present; `related_taxonomy_slug` ACF field set for sidebar
- [ ] Affiliate disclosure near top if any affiliate links present
- [ ] RankMath meta title + description set

---

## 5. Monthly Recurring Audit

**Cadence:** First week of each month. ~2 hours.

1. **Run `claude-seo seo-flow`** as orchestrator across all published bean pages and the top 10 guides.
2. **Run `claude-seo seo-technical`** on the homepage, `/beans/`, and any URL added in the previous 30 days: Core Web Vitals flags, mobile rendering, Chart.js not blocking render, `robots.txt` and sitemap reachable.
3. **Run `rampstack seo-onpage`** on the 3 pages with the largest traffic or ranking drops (check Search Console).
4. **Log findings** in a GitHub issue tagged `seo-audit`. Fix the top 3 by estimated impact × effort.
5. **Check scraper logs** (`/opt/data/scraper.log`) for failed price fetches — stale price data hurts trust.

If GitHub Actions is wired up: a scheduled job could open a monthly issue with this checklist pre-filled. That is not built yet; see §6.

---

## 6. Optional Tool Extensions (wire up when ready)

These are `claude-seo` optional integrations. Do not block on them.

| Tool | What it adds | Env var / key needed | Priority |
|---|---|---|---|
| **Unlighthouse** | Local Lighthouse CI across all URLs at once | npm install only (free) | **High** |
| **Google Search Console** | Real ranking, CTR, and impression data | `GSC_SITE_URL` + OAuth | **High** |
| DataForSEO | Keyword volume + SERP data | `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` | Medium |
| Ahrefs | Backlink profile + keyword difficulty | `AHREFS_API_KEY` | Medium |
| SE Ranking | Rank tracking | `SE_RANKING_API_KEY` | Low |
| Bing Webmaster | Bing-specific crawl data | `BING_WEBMASTER_API_KEY` | Low |

Set each key in `/opt/.env`. Never commit to repo.

---

## 7. Content Ratio Rule

Google's affiliate-content ratio signal: informational content (origin guides, brew explainers) must be ≥40% of total indexed pages. Track this quarterly.

Current content types by purpose:
- **Informational** (≥40% target): origin guides, brew method guides, process explainers
- **Commercial** (≤60%): individual reviews, roundups, comparisons, price tracker pages

If the ratio slips below 40% informational, publish the next guide before the next bean review.
