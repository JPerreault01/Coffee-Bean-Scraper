git # Gotchas

*Common mistakes when writing for Coffee Bean Index. Update this file iteratively as you spot the skill making errors.*

## Voice mistakes

- **Generic openers.** Do not start a review with "Looking for a great espresso?" or "Coffee lovers, rejoice!" These are the AI-blog openers — they are not on voice. Use the patterns in `voice/voice_profile.md` instead.
- **Hedge-summary verdicts.** The one-line verdict must be a stance, not a summary. "A medium-roast Brazilian blend with chocolate notes" is a description, not a verdict. "Forgiving espresso for under-extraction, but no character" is a verdict.
- **Fake personal experience.** Do not claim "I drank this every morning" or "I pulled fifty shots" unless the user explicitly enables personal mode. Default voice describes the coffee, not Jackson's mornings.
- **Reddit register leakage.** Voice signal from Reddit/podcasts (vocabulary, opinions, tics) is fine. Reddit *structure* (run-on sentences, "tbh", "imo", lowercase opens) is not. The exemplars in `voice/exemplars/` are the structural target — match those.

## Format mistakes

- **Missing rating.** Every individual bean review ends with "Rating: X/10" plus a one-sentence explanation. Never omit.
- **Vague tasting notes.** "Smooth and chocolatey" is not a tasting note — it's two words with no context. "Dark chocolate bitterness that fades clean, not lingering" is a tasting note. Always pair the descriptor with a behavior or context.
- **No "Who should skip it" section.** Every review must have this. It is what differentiates the site from press-release content. Be honest.
- **Marketing language in the price analysis.** "Premium quality at an everyday price" is marketing copy. "Twenty percent above the category average; worth it if you want a forgiving espresso blend" is analysis.

## Knowledge mistakes

- **Invented specifics.** Do not make up percentages, prices, production volumes, elevation, or sensory ratings. If a number is not in the product specs you were given, leave it out.
- **Stating a contested claim as settled.** Check `knowledge/contested_claims.md`. If a claim appears there, treat it as a place to take a stance, not as fact. Do not present it neutrally.
- **Importing descriptors not in the corpus.** Only use tasting descriptors that appear in `knowledge/tasting_descriptors.md`. If a perfect descriptor exists outside the corpus, add it to the file rather than slipping it in.

## Process mistakes

- **Skipping the voice files.** Even on review #50, re-read `voice/voice_profile.md` and at least one exemplar before drafting. Voice drift happens silently.
- **Skipping self-check.** Always run the self-check listed in SKILL.md before delivering. The check catches more issues than the draft step does.
