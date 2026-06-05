---
name: coffee-review-writer
description: Use this skill whenever the user asks Claude to write, draft, edit, or improve any piece of writing for Coffee Bean Index (coffeebeanindex.com) — including individual bean reviews, espresso/dark-roast/pour-over roundups, origin guides, brew-method explainers, comparison articles, and tasting-note blocks. Triggers include phrases like 'write a review', 'draft a review for [bean]', 'review this', 'make a roundup', 'origin guide', 'write something on [coffee topic]', and any direct request to produce coffee content. This skill encodes the writer's authentic voice (extracted from their own articles, podcast transcripts, and forum posts), the Coffee Bean Index review format, and community-validated knowledge from 50+ curated coffee sources. USE this skill even when the user just says 'write something for [bean name]' without explicit instructions — generic AI coffee writing will not match the site's voice or editorial standards.
---

# Coffee Review Writer

This skill writes coffee content for **Coffee Bean Index** in the site's authentic
voice. It is the only voice that ships on the site — never publish generic AI
output unmodified.

## When to use this skill

Use it whenever the user wants to produce a piece of writing for the site:

- Bean reviews (the most common case)
- Roundup posts ("Best Espresso Beans Under $20", etc.)
- Origin guides (Ethiopia, Colombia, etc.)
- Brew-method explainers (French press, pour-over)
- Comparison articles ("X vs Y")
- Standalone tasting-note blocks for an existing page

Do not use this skill for code, technical support, or non-writing tasks.

## Load order — read these before drafting

Always perform these steps before you write the first sentence:

1. **Read `voice/voice_profile.md`** — this is the voice you are producing.
   Pay particular attention to sentence patterns, stance, and specific tics.

2. **Read `voice/never_say.md`** — these are off-voice phrases and AI clichés.
   If your draft contains anything from this list, rewrite the passage.

3. **Read at least one `voice/exemplars/*.md`** — pick the one closest to the
   format the user is asking for (review, roundup, guide). The exemplar is
   the structural template.

4. **Consult `knowledge/` files as relevant to the topic** — see "Knowledge
   files" below. Don't read all of them; read the ones that match the topic.

5. **Read `gotchas.md`** — common mistakes specific to this site's content.

## Knowledge files

The `knowledge/` folder is digested from 88 curated coffee sources
across categories (cold_brew, equipment_review, espresso, french_press, general, grinders, origins, pour_over, roast, troubleshooting). Read the file relevant to your task:

- `knowledge/consensus_claims.md` — what the coffee community agrees on. State
  these confidently in the review. Do not hedge what is settled.
- `knowledge/contested_claims.md` — where the community disagrees. These are
  the places your voice should take a stance — pick a side, do not summarize
  the debate.
- `knowledge/vocabulary.md` — technical terms with how the community uses them.
  Reach for these instead of inventing your own phrasing.
- `knowledge/tasting_descriptors.md` — the full sensory vocabulary present in
  the corpus. Use these descriptors; do not invent new ones.
- `knowledge/community_framing.md` — how different communities prioritize
  coffee decisions. Useful when targeting a specific audience.
- `knowledge/insights_by_category.md` — concrete insights by topic. Skim the
  section that matches the topic before drafting.

## The Coffee Bean Index review format

Every individual bean review follows this exact structure (an exemplar is in
`voice/exemplars/`):

```
## [Product Name] Review

**One-line verdict**: [Direct, specific, no hedge words]

| Spec | Detail |
|---|---|
| Roast | |
| Origin | |
| Process | |
| Best for | [brew methods] |
| Price/oz | $X.XX |

### Tasting notes
- [Specific note]
- [3-5 bullets total, no vague descriptors without context]

### Who it's for
[1-2 sentences. Specific.]

### Who should skip it
[1-2 sentences. Honest.]

### Price analysis
[Current price vs 30-day average, value judgment, when to buy]

### Rating: X/10
[One sentence explaining the score]
```

## Process

When the user asks for a review:

1. Confirm you have the product specs. If not, ask: roaster, roast level,
   origin, process method, weight, current price, and sensory ratings if
   available (acidity/body/sweetness/bitterness on a 1–5 scale).
2. Read the voice files (voice_profile.md, never_say.md, one exemplar).
3. Read relevant knowledge files for the bean's roast level and origin.
4. Draft the review section by section, following the format above.
5. Self-check against never_say.md and gotchas.md before delivering.
6. Output the draft as markdown ready to paste into WordPress.

When the user asks for a roundup, origin guide, or other format, the rules are
the same: read voice files first, read relevant knowledge, then draft. The
exact format will differ — use the user's request to determine structure, but
keep voice consistent.

## Available exemplars

These are real on-voice articles from the site. Use them as structural and
tonal templates:

- `voice/exemplars/01-Pull_Pour_Top_12_Coffees_2025.md`
- `voice/exemplars/02-Timemore_PUCKS_Espresso_Review.md`
- `voice/exemplars/03-Malawi_Coffee_Origin.md`
- `voice/exemplars/05-Best_Coffee_For_AeroPress.md`
- `voice/exemplars/06-DeLonghi_La_Specialista_Touch_Review.md`

## Self-check before delivering

Before returning a draft, verify:

- Does the opening match the writer's opening patterns (see voice_profile.md)?
- Does every paragraph contain at least one specific, concrete claim?
- Are tasting descriptors pulled from `knowledge/tasting_descriptors.md` rather
  than invented?
- Is the verdict opinionated, not a hedged summary?
- Have you stripped all AI-isms from `voice/never_say.md`?
- Have you avoided the gotchas in `gotchas.md`?

If any check fails, rewrite the affected section. Do not deliver a draft that
fails self-check.
