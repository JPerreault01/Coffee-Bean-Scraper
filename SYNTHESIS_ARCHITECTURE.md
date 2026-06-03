# How Tier 1 and Tier 2 Synthesize

## The mental model: a skill is a folder, not a prompt

The two tiers don't get merged into one big prompt. They coexist as separate files
inside a single skill folder, loaded on demand at write time. This is the
[Anthropic Agent Skills](https://github.com/anthropics/skills) pattern — adopted
because months of community usage have proven it scales better than monolithic
prompts.

The key insight from researching Anthropic's own skill-creator and the community
literature (Voice DNA, custom voice skills, brand-voice skills): **skills are
pointers to knowledge, not containers of knowledge**. The skill's main file
(`SKILL.md`) tells Claude when to fire and how to navigate the folder. The actual
content lives in supporting files that load only when needed.

This means Tier 1 (voice) and Tier 2 (knowledge) end up as parallel subfolders
under the same skill, *not* as merged content.

## The final assembled structure

```
skills/coffee-review-writer/
├── SKILL.md                          ← entry point; YAML frontmatter + instructions
├── voice/                             ← Tier 1 output
│   ├── voice_profile.md              ← structured voice DNA (tone, patterns, tics)
│   ├── never_say.md                  ← off-voice phrases and AI-isms to avoid
│   └── exemplars/                    ← actual on-voice articles, full text
│       ├── lavazza_super_crema.md
│       └── [other Jackson articles].md
├── knowledge/                         ← Tier 2 output
│   ├── consensus_claims.md           ← what the community agrees on
│   ├── contested_claims.md           ← where the community disagrees
│   ├── vocabulary.md                 ← technical terms with definitions
│   ├── tasting_descriptors.md        ← sensory vocabulary inventory
│   ├── community_framing.md          ← how communities prioritize decisions
│   └── insights_by_category.md       ← per-topic insights
└── gotchas.md                         ← common mistakes to avoid
```

## How loading works at write time

This is the synthesis point. When Jackson asks Claude to write a review:

1. **Skill selection** — Claude reads only the `name` and `description` from
   every installed skill's frontmatter (this lives permanently in the system
   prompt, but is tiny). The description text is what triggers selection.

2. **Skill body loads** — Once Claude decides to use this skill, it reads the
   full `SKILL.md` body. This is where the instructions live: load voice first,
   load relevant knowledge sections, follow the format exemplars.

3. **Supporting files load on demand** — The SKILL.md tells Claude things like
   "before drafting, read `voice/voice_profile.md` and `voice/exemplars/[any]`"
   and "consult `knowledge/consensus_claims.md` for technique claims." Each
   file loads only when referenced.

This three-level loading is what makes it scalable. With a single
monolithic prompt, every piece of voice information and every digested source
would be in context every time, eating tokens. With the skill folder pattern, the
context loads in tiers as needed.

## Why voice and knowledge stay separate

The single biggest reason: **they answer different questions and have different
recency.**

- **Voice** answers "How does Jackson write?" It changes slowly. When you add a
  new published review, it gets folded into voice exemplars. Update once every
  few weeks.
- **Knowledge** answers "What does the coffee community know?" It changes
  whenever the corpus is refreshed. Update on a separate cadence as new sources
  come in.

If they were one file, every voice update would force a knowledge re-build (or
vice versa). Keeping them as parallel subfolders means each tier has its own
rebuild trigger and the assembler just stitches the latest of each together.

## The build flow

```
1. Drop voice materials into voice_materials/  ←  Jackson does this
   ├── articles/        (used as format exemplars)
   ├── reddit/          (voice signal only)
   └── podcasts/        (voice signal only)

2. python data_pipeline/build_voice_profile.py
   → writes skill_data/voice/voice_profile.md, never_say.md, exemplars/

3. python data_pipeline/build_skill_knowledge.py
   → writes skill_data/skill_knowledge.json + skill_knowledge.md
   (Tier 2 — already built, ~$1 in Sonnet calls)

4. python data_pipeline/assemble_skill.py
   → reads both above outputs
   → splits knowledge.json into per-section MD files
   → generates SKILL.md with proper YAML frontmatter
   → writes skills/coffee-review-writer/ (the final assembled skill)

5. Test by writing 5 reviews and judging output quality
   → If voice is off, edit voice_materials/, re-run step 2 + 4
   → If facts are thin, edit which sources are selected, re-run step 3 + 4
```

Steps 2 and 3 are independent. Step 4 is the synthesizer.

## What the assembler actually does

`assemble_skill.py` is the file that answers the original synthesis question.
Its job:

1. Read `skill_data/skill_knowledge.json` (Tier 2 output)
2. Read `skill_data/voice/` files (Tier 1 output)
3. Create `skills/coffee-review-writer/` from scratch
4. **Generate `SKILL.md`** with:
   - YAML frontmatter (name, description that triggers reliably)
   - Body that names every supporting file and says when to load each
   - A short "process" section: how to actually write a review using the skill
5. Split `skill_knowledge.json` into per-section markdown files under `knowledge/`
6. Copy voice files under `voice/`
7. Write a starter `gotchas.md` based on lessons from the fine-tune failure and
   general best practices — Jackson updates this iteratively as he sees the
   skill make mistakes

After step 7 the skill is installable in Claude desktop (or callable via the API
with the skill folder as input). The output is portable — same folder works for
chat, Cowork, Claude Code, or any other interface that supports the standard.

## Voice profile: what Tier 1 actually extracts

Based on the Voice DNA literature and Anthropic's own voice-skill guidance, the
voice profile is a structured document with these sections:

- **Tone** — the overall register and stance
- **Sentence patterns** — length preference, structure, rhythm
- **Vocabulary signature** — distinctive words and phrases this writer uses
- **Stance patterns** — how this writer asserts vs hedges vs qualifies
- **Opening / closing / transition patterns** — recurring structural moves
- **Specific tics** — quirks the writer doesn't notice but that mark the voice
- **Never-say list** — words and phrases that are off-voice
- **AI-isms to avoid** — the universal "delve into" / "it's worth noting" cliché
  list, flagged so the writer can suppress them
- **Topic-specific stances** — Jackson's positions on coffee-relevant subjects
  (e.g., "value over brand premium," "clean finishes over lingering bitterness")

Critically, the extractor distinguishes **articles** (written, used as format
templates) from **Reddit posts and podcast transcripts** (used only as voice
signal — vocabulary, stances, tics — never as structural templates). Mixing
these is exactly the trap that broke the fine-tune. Spoken and casual registers
poison the format if treated as exemplars.

## What's not in the skill folder (and why)

- **The full ~2,000-record substrate** stays out. That's Tier 3 (RAG), built
  later only if the skill alone produces thin reviews. RAG gets queried at
  write time and injected as additional context — it doesn't live in the skill.

- **Product specs** stay out. Those come from `products.json` and the SQLite
  database, fetched at write time per review.

- **The fine-tuned model** stays out. The skill is model-agnostic — it works
  with Haiku 4.5, Sonnet 4.6, or a future fine-tune. The voice and knowledge
  live in the skill content, not in the weights.

## Cost recap (still trivially cheap)

| Step | One-time | Per-review |
|---|---|---|
| Tier 1: voice extraction (Sonnet, all materials in one call) | ~$0.50–1.50 | — |
| Tier 2: knowledge digestion (60 sources, Sonnet) | ~$1.00 | — |
| Tier 4: write a review (Haiku 4.5, with prompt caching) | — | ~$0.015 |
| Tier 4: write a review (Sonnet 4.6, with prompt caching) | — | ~$0.04 |

A thousand published reviews still lands under $50 total all in.
