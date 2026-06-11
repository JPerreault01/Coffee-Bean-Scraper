# Content Standards: Review Scoring

> Source of truth for **how a bean is scored**. The rating rules here override the
> short "Rating: X/10" line in the review format in [CLAUDE.md](CLAUDE.md). The
> rubric text itself lives in code at [scrapers/score_ledger.py](scrapers/score_ledger.py)
> (`RATING_RUBRIC`); keep the two in sync. Tunables live in
> [scrapers/scoring_config.json](scrapers/scoring_config.json).

## The problem this fixes

AI-generated scores clustered at 6-7/10. The old prompt said only `Rating: X/10`
with no anchored rubric, so the model regressed to a safe middle. Baseline across
the 52 real drafts: range **4.0-7.0**, median **6.0**, stdev **0.81**, only 5
distinct values, nothing above 7 or below 4. That is bias, not judgment.

The fix has four levers plus an external-critic sanity check.

---

## 1. Anchored rubric (the score bands)

Every bean is scored against fixed, named bands. Use the **full 1.0-10.0 range in
0.1 increments**.

| Band | Meaning |
|---|---|
| **9.0-10.0** | EXCEPTIONAL. Rare. A bench-defining coffee with no real fault. Reserve it. |
| **8.0-8.9** | EXCELLENT. A standout in its category, clearly better than the field. |
| **7.0-7.9** | GOOD, AND IT MUST BE EARNED. Not the default. Name the specific thing that lifts it above average, or it is not a 7. |
| **5.0-6.9** | AVERAGE. Where MOST beans land. Competent, does its job, nothing distinguishing. |
| **3.0-4.9** | A NAMABLE FLAW. Something concrete drags it down: muddy finish, brand premium, one-dimensional, finicky, over-roasted, poor value. |
| **1.0-2.9** | AVOID. Actively bad or a clear rip-off. |

**Hard anti-clustering rules:**
- Do NOT default to 6-7. That cluster is the exact bias being corrected.
- Most beans are average: score them 5.0-6.9, not 7.
- A 7.0+ requires a specific, stated reason it beats the field. No reason means below 7.

**Use the top of the scale when earned (the rules above must not become a 7.x cap):**
- 7.x is NOT a ceiling. Compressing every good bean into 7.0-7.5 is the old 6-7 bias
  shifted up. A genuinely exceptional cup must score 8.0+.
- Competition-grade and benchmark single origins belong in the 8s: a clean, distinctive
  Geisha/Gesha; a top-tier washed Kenyan (SL28/SL34) with defined high-grown acidity; an
  exemplary, clearly-standout single-origin lot. Score these 8.0-8.9.
- Reserve 9.0+ for a near-flawless, bench-defining coffee, but place it there when the
  bean genuinely is that good.
- Suppressing a real standout into 7.x out of caution is the same bias as inflation,
  inverted. Judge the cup on its merits and use the full 1.0-10.0 range.

## 2. Decimals carry meaning

Scores use any value 1.0-10.0 to **0.1 precision**. The one-sentence justification
must name the specific thing that set that exact decimal: why 7.3 and not 7.0 ("the
clean, fast finish edges it above the 7.0 tier, but a generic blend origin keeps it
short of 7.5"). A round number with no decimal reasoning is a tell that the model
defaulted instead of judging.

## 3. Score last, pressured by the critique

The number is decided **after** the honest "Who should skip it" section, not after
the positive tasting notes. In the review prompt the rating instruction comes last,
and the model must emit a machine-readable score block at the very end of its output:

```
<!--SCORE
score: 7.3
rationale: Clean, fast chocolate finish lifts it past 7.0, but a generic blend origin and brand-premium price keep it short of 7.5.
-->
```

This block is an HTML comment: invisible on the page and ignored by
`push_drafts.php` (which reads the visible `### Rating: X.X/10` heading for the ACF
`rating` field, decimal-aware). It is the robust parse target for the ledger.

## 4. Comparative anchoring: the rationale ledger

Scores are calibrated **relative to real prior beans**, not in a vacuum.

- **Where it lives:** `data/score_rationales.json` (`/opt/data/score_rationales.json`
  on the VPS). This is a derived artifact and is **gitignored** (`.gitignore:
  data/*.json`), exactly like `sensory_scores.json` and `coffeereview.json`. It is
  rebuilt from drafts by `backfill_scores.py`, so it never needs committing.
- **What each entry holds** (token-light):
  ```json
  {
    "product_id": "onyx-monarch",
    "name": "Onyx Coffee Lab Monarch",
    "roast_level": "Medium",
    "score": 6.5,
    "rationale": "Forgiving home-machine profile and clean chocolate lift it above the 6.0 field; premium pricing and a narrow range keep it short of 7.0.",
    "method": "backfill-rescore",
    "scored_at": "2026-06-08T...Z",
    "external": { "raw": 94, "scale_max": 100, "normalized": 8.8, "source": "coffeereview:...", "delta": -2.3, "status": "divergent" },
    "score_divergence": "ours 6.5 vs critic ~8.8 (raw 94/100, delta -2.3) - manual review"
  }
  ```
  Our score and any external score are **separate fields**. The external number
  never overwrites ours.
- **How it is used when scoring a new bean** (`format_scoring_context`):
  1. The ~15-20 closest comparables (same roast level / sensory profile / price
     tier) are injected with their score + rationale, so the model scores against
     real neighbours.
  2. A compressed whole-catalog view is injected for broad calibration: "across N
     beans: median 6.2, only 3 scored above 8.0", plus a band histogram.
  Token use stays low: full rationales only for the close set, summary stats for the
  broad set.

> **The rubric is the absolute authority; comparables are for ordering only.** This
> distinction matters. If you anchor the *number* to a biased baseline, you reinforce
> the bias: seeding the ledger from the old 6-7 scores and re-scoring against it
> produced correct ordering but **compressed every score back into 5-7** (the model
> obeyed the anchor over the rubric). The injected context now tells the model to
> treat the catalog's current range as suspect and take the magnitude from the rubric
> bands, using comparables only to rank a bean among its neighbours. For the same
> reason, `backfill_scores.py` re-scores from a **cold** ledger by default; pass
> `--autoseed` only if you understand it re-imports the old bias as anchors.

> **Comparables are INTERNAL calibration only - they must never surface in the review.**
> The comparables list is scaffolding for choosing the number; it is not material for the
> prose. The model must never name, reference, or compare to another specific coffee,
> roaster, or its score anywhere in the visible output (verdict, tasting notes, who-for /
> who-skip, price analysis, the `### Rating` sentence, or the `<!--SCORE` rationale).
> Each review must justify its score purely on that bean's own merits and the rubric
> bands. With a catalog heading past 1000 beans, naming a neighbour ("better than X",
> "past Koa's 7.4", "edges out <bean>") reads as arbitrary to a reader who never saw that
> bean and dates the page the moment the ledger shifts. This is enforced in the prompt
> (`format_scoring_context`, `rating_section_instruction`, `SCORE_TRAILER_INSTRUCTION`).
> The deliberate, owner-authored "X vs Y" comparison via a product's `comparison_anchors`
> is a separate, intentional feature and is unaffected by this rule.

---

## External critic scores: a sanity check, NOT an anchor

When a bean exists in the scraped CoffeeReview corpus (`data/coffeereview.db`, 100-pt
ratings) or is found via the optional web lookup, that score is used **only as a
divergence check** after our score already exists. It is never put into the scoring
prompt and never sets our number.

1. **Score independently first.** Our score and rationale come from our rubric, our
   product data, our style guide, and the comparative ledger, with no sight of the
   external score.
2. **Then compare** (`divergence_check`): the external score is normalized to our 1-10
   scale **for comparison only** (heuristic map in `scoring_config.json`; CoffeeReview's
   effective range is ~85-97, so a mainstream bean we score ~6 will usually diverge
   from a 90+ critic, and that flag is the point).
   - Within `agreement_threshold` (default 1.0): agree, keep ours, no flag.
   - Beyond `divergence_threshold` (default 1.5): do NOT auto-adjust. Add a
     `score_divergence` note to the ledger entry for manual review. A big gap might
     mean we are wrong, or that we caught something the critic missed. That is the
     owner's call, not the model's.
3. **Reasoning stays ours.** Tasting notes and rationale are written from our product
   data and style guide. Scraped notes may be cross-checked for factual claims
   (origin, process, roast) but never paraphrased or mirrored. If scraped notes
   contradict our product data, trust our data and flag the conflict.
4. **`critic_weight` toggle** (`scoring_config.json`, default `"advisory"`): controls
   how much external data may influence scoring. `advisory` flags divergences and
   changes nothing automatically. `low` additionally records a bounded
   `suggested_nudge` (capped at `max_nudge`) for manual review, but still never
   overwrites our score. Default is advisory-only.

The external score is **evidence, not a verdict**, and is stored alongside ours so
agreement can be audited over time.

---

## Operating it

**Normal generation** (score is written to the ledger automatically):
```
python scrapers/generate_review.py <id> --api claude
python scrapers/generate_review.py <id> --api claude-code     # local, free Pro tokens
python scrapers/generate_review.py <id> --web-calibrate        # optional external lookup
python scrapers/generate_review.py <id> --no-ledger            # skip ledger write
```

**Backfill + verify** (re-score existing drafts, print before/after spread):
```
python scrapers/backfill_scores.py --seed-from-drafts          # baseline from drafts (no API)
python scrapers/backfill_scores.py --rescore --api claude-code # re-score all (local, free)
python scrapers/backfill_scores.py --histogram                 # before vs after
```
Re-scoring does not regenerate the review body; it feeds the existing critique plus
the rubric and ledger back to the model and asks only for the score block. Cheap, and
still pressured by the critique.

**Tuning:** edit [scrapers/scoring_config.json](scrapers/scoring_config.json)
(`critic_weight`, thresholds, `comparable_k`, the critic normalization map). No code
change needed.
