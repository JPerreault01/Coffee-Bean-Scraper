# Content Refresh Program

> **Quarterly cadence.** Stale content decays in rankings. This doc defines what to refresh, when, and how to decide between refresh, merge, or delete.

---

## Cadence

| Cycle | When | What |
|---|---|---|
| **Quarterly** | First week of Jan, Apr, Jul, Oct | Full content audit (rankings, price staleness, thin pages) |
| **Ongoing** | When scraper triggers price-drop alert | Update `price_analysis` field if price has moved >15% |
| **On formulation change** | When roaster changes the product | Full review rewrite; update all ACF fields |
| **On ranking drop** | When Search Console shows >20% impressions drop over 28 days | Audit the page; may need refresh or merge |

---

## Signals That Trigger a Refresh

**Trigger a review TEXT refresh when:**
- 12+ months since `last_reviewed` date in ACF
- Product formulation has changed (different roast profile, new origin blend)
- Page has dropped >20% in impressions over 28 days (Search Console)
- A competitor review clearly outranks on the same query with better content depth

**Price data refreshes automatically** via the scraper cron (`0 6 * * *`) — no manual action needed unless the scraper fails. Check `/opt/data/scraper.log` for errors.

**Trigger a merge when:**
- Two pages target near-identical keywords (cannibalization) — e.g., two "best espresso beans" roundups
- One page has <500 sessions/month AND the other covers the same ground with better depth
- Merge: consolidate into the stronger URL, 301 the other

**Trigger a delete when:**
- Zero organic sessions in 90 days AND no internal links to the page AND no affiliate revenue
- Content is thin (<300 words, no ACF data) AND the product is discontinued
- Always 301 redirect deleted URLs to the most relevant remaining page

---

## Quarterly Audit Process

### Step 1 — Rank & Traffic Check (30 min)
Pull from Google Search Console:
- Pages with >20% impressions drop MoM
- Pages ranking position 11–20 for their primary keyword (easy wins to push to top 10)
- Pages with high impressions but low CTR (<2%) — meta description may need fixing

### Step 2 — Price Staleness Check (15 min)
In the WP admin, filter Beans by `last_reviewed` date:
- Flag any bean with `last_reviewed` > 12 months ago
- Check if the price has moved significantly (compare `current_price` to the scraper's 30-day average)
- Flag any bean where the scraper hasn't updated `current_price` in >48 hours (scraper failure)

### Step 3 — Thin / Cannibalized Page Check (15 min)
- Run `rampstack content-refresh-system` on the full URL list
- Check for pages with <300 words of unique editorial content (not counting boilerplate)
- Check for overlapping taxonomy archives targeting the same intent

### Step 4 — Fix Queue (variable)
Prioritize by: (ranking opportunity) × (effort to fix) × (affiliate revenue potential).

Top-tier fixes first:
1. Position 11–20 pages that need one on-page improvement (meta, heading, internal link)
2. Pages with stale `last_reviewed` AND ranking drop
3. Thin pages that need content depth or a merge decision

### Step 5 — Log
Open a GitHub issue tagged `content-refresh` with:
- List of refreshed pages
- List of merged pages (with 301 redirect confirmation)
- List of deleted pages (with 301 redirect confirmation)
- Any new signals to watch next quarter

---

## Refresh vs. Merge vs. Delete Decision Tree

```
Is the page getting any traffic or ranking for a real keyword?
├── No → Is the product discontinued or the topic permanently irrelevant?
│   ├── Yes → DELETE (301 to closest alternative)
│   └── No → Is the content thin but the keyword worth targeting?
│       ├── Yes → REFRESH (add depth)
│       └── No → HOLD for one more quarter; delete if still no traction
└── Yes → Is another page cannibalizing the same keyword?
    ├── Yes → MERGE (keep the stronger URL, 301 the weaker)
    └── No → Is the content stale (>12mo or formulation change)?
        ├── Yes → REFRESH
        └── No → No action needed this cycle
```

---

## Notes on Specific Content Types

**Price tracker pages (= individual reviews):**
The price chart auto-refreshes daily via scraper. Review *text* only needs updating when:
- The roaster changes the product's roast level, origin, or formulation
- 12+ months have passed since `last_reviewed`
- The page's ranking has significantly dropped

**Origin guides and brew method guides:**
These are informational content that protects the 40% informational content ratio. Do not delete these unless the taxonomy has zero beans. Refresh when the coffee landscape changes (new processing methods becoming mainstream, etc.) or when they drop in rankings.

**Taxonomy archives:**
These auto-populate as beans are added. Their `term description` is the guide body — refresh that description when:
- The term has ≥5 beans (worth investing in a good intro paragraph)
- The description is the `[Guide content coming soon]` placeholder

**Roundups and comparisons:**
High-value pages. Refresh annually at minimum. Check that each pick still:
- Has a live affiliate link
- Has an up-to-date price and rating
- Outranks the alternatives for its comparative query

---

## Price-Data vs. Review-Text Separation

**Never conflate these two refresh types:**

| Type | What refreshes it | When |
|---|---|---|
| Price data (`current_price`, `price_per_oz`) | Scraper cron (`0 6 * * *`) | Daily, automatic |
| Price chart data | Scraper populates `prices.db` | Daily, automatic |
| Review text (tasting notes, verdict, whos_for) | Manual update via WP admin | On trigger (see above) |
| `last_reviewed` date | Manual update via WP admin | When review text is updated |

A page can have today's price and 18-month-old review text simultaneously. The refresh program targets the *text*, not the *price data*.
