# scrapers/backfill_scores.py
"""
Backfill + verify the new scoring system.
=========================================
One-off tool to (1) seed the comparative rationale ledger from existing drafts,
(2) re-score existing drafts through the new anchored-rubric + ledger system, and
(3) print a BEFORE/AFTER score histogram so you can confirm the spread widened.

BEFORE  = the integer scores the old prompt produced, re-parsed from the drafts
          themselves (immutable, so this baseline never moves).
AFTER   = the decimal scores in the ledger after re-scoring.

Why re-scoring is cheap: it does NOT regenerate the review body. It feeds the
EXISTING review (its honest "who should skip it" critique) plus the rubric and the
comparable-bean ledger back to the model and asks only for the SCORE block. So the
score is still pressured by the critique (lever c) and anchored to real prior beans
(lever d), at a fraction of a full generation.

External critic scores are NOT used to set the score. After our score exists, the
shared divergence_check (score_ledger) flags large gaps for your review only.

Usage (local, free, uses the Claude Code CLI Pro tokens):
  python scrapers/backfill_scores.py --seed-from-drafts          # populate ledger from drafts (no API)
  python scrapers/backfill_scores.py --histogram                 # before/after, no API
  python scrapers/backfill_scores.py --rescore --api claude-code # re-score all (local, free)
  python scrapers/backfill_scores.py --rescore --api claude-code --limit 8   # a sample
  python scrapers/backfill_scores.py --rescore --only death-wish-coffee
  python scrapers/backfill_scores.py --rescore --api claude --web-calibrate  # VPS, paid key

Typical first run:
  python scrapers/backfill_scores.py --seed-from-drafts
  python scrapers/backfill_scores.py --rescore --api claude-code
  python scrapers/backfill_scores.py --histogram
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRAPERS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRAPERS_DIR))

import score_ledger as sl  # noqa: E402
import generate_review as gr  # noqa: E402

DRAFTS_DIR = gr.DRAFTS_DIR
_FNAME_RE = re.compile(r"^(.+)-(\d{4}-\d{2}-\d{2})\.md$")


# ---------------------------------------------------------------------------
# Draft discovery + parsing
# ---------------------------------------------------------------------------

def latest_draft_per_id() -> dict[str, Path]:
    """Return {product_id: newest draft Path} from the drafts dir."""
    latest: dict[str, tuple[str, Path]] = {}
    if not DRAFTS_DIR.exists():
        return {}
    for path in DRAFTS_DIR.glob("*.md"):
        m = _FNAME_RE.match(path.name)
        if not m:
            continue
        pid, date = m.group(1), m.group(2)
        if pid not in latest or date > latest[pid][0]:
            latest[pid] = (date, path)
    return {pid: p for pid, (_d, p) in latest.items()}


def _is_mock(text: str) -> bool:
    return "MOCK DRAFT" in text or "(mock, run scraper" in text


def _read_text(path: Path) -> str:
    """Read a draft tolerant of mixed encodings. Drafts written locally on Windows
    are cp1252; those written on the VPS are utf-8. Try utf-8, fall back to cp1252
    (which never errors), so non-ASCII chars survive instead of becoming U+FFFD."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def parse_draft_score(path: Path) -> tuple[float | None, str | None, bool]:
    """Return (score, rationale, is_mock) for a draft file."""
    text = _read_text(path)
    mock = _is_mock(text)
    score, rationale = sl.parse_score_from_text(text)
    return score, rationale, mock


def review_body_for_rescore(text: str) -> str:
    """Strip the SCORE trailer and the old '### Rating' section so the model
    re-derives the number from the critique rather than echoing the old score."""
    text = sl._TRAILER_RE.sub("", text)
    idx = re.search(r"###\s*Rating:", text, re.I)
    if idx:
        text = text[: idx.start()]
    return text.strip()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def cmd_seed(products: dict, verbose: bool = True) -> dict:
    """Parse the latest real (non-mock) draft per bean into the ledger as the
    starting baseline. Returns the ledger."""
    ledger = sl.load_ledger()
    seeded = skipped_mock = skipped_noscore = 0
    for pid, path in sorted(latest_draft_per_id().items()):
        score, rationale, mock = parse_draft_score(path)
        if mock:
            skipped_mock += 1
            continue
        if score is None:
            skipped_noscore += 1
            continue
        product = products.get(pid, {"id": pid, "name": pid})
        entry = sl.make_entry(product, score, rationale or "(seeded from existing draft)",
                              "seed-from-draft")
        sl.upsert_entry(ledger, entry)
        seeded += 1
    sl.save_ledger(ledger)
    if verbose:
        print(f"Seeded {seeded} beans into the ledger "
              f"(skipped {skipped_mock} mock, {skipped_noscore} unparseable).",
              file=sys.stderr)
    return ledger


# ---------------------------------------------------------------------------
# Model callers (quiet — return text, no streaming to stdout)
# ---------------------------------------------------------------------------

def _score_via_claude(prompt: str, env: dict) -> str:
    import anthropic
    key = env.get("CLAUDE_API_KEY") or env.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("CLAUDE_API_KEY not set")
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _score_via_minimax(prompt: str, env: dict) -> str:
    import requests
    key = env.get("MINIMAX_API_KEY", "")
    if not key:
        raise ValueError("MINIMAX_API_KEY not set")
    resp = requests.post(
        "https://api.minimaxi.chat/v1/text/chatcompletion_v2",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "MiniMax-Text-01",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 300, "temperature": 0.4},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _score_via_claude_code(prompt: str) -> str:
    import os
    import shutil
    import subprocess
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError("claude CLI not found")
    # Pass the prompt on stdin (avoids arg-length/quoting limits) and route .cmd
    # launchers through cmd.exe on Windows so CreateProcess can execute them.
    args = ["cmd", "/c", exe, "-p"] if os.name == "nt" else [exe, "-p"]
    result = subprocess.run(args, input=prompt, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=240)
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI exit {result.returncode}: {result.stderr[:200]}")
    return result.stdout


def call_model(prompt: str, api: str, env: dict) -> str:
    if api == "claude":
        return _score_via_claude(prompt, env)
    if api == "minimax":
        return _score_via_minimax(prompt, env)
    if api == "claude-code":
        return _score_via_claude_code(prompt)
    raise ValueError(f"unknown api {api}")


def build_scoring_prompt(product: dict, review_body: str, scoring_context: str) -> str:
    """Scoring-only prompt: rubric + comparative ledger + the existing review's
    critique. Returns ONLY the SCORE block. The external critic score is never here."""
    return f"""You are re-scoring a coffee for Coffee Bean Index using our anchored rubric.
Score it on its merits relative to the comparable beans below. Use the full decimal range.

{sl.RATING_RUBRIC}
{scoring_context}
Here is the finished review of this coffee. Use its honest critique, especially the
"Who should skip it" section, to pressure the score DOWN. Do not let the positive tasting
notes inflate it.

--- REVIEW ---
{review_body}
--- END REVIEW ---

Coffee: {product.get('name')} | Roast: {product.get('roast_level')} | Origin: {product.get('origin')}

Output ONLY this block, nothing before or after:
<!--SCORE
score: <one decimal, e.g. 6.4>
rationale: <15-25 words naming the exact thing that set this decimal>
-->"""


# ---------------------------------------------------------------------------
# Re-scoring
# ---------------------------------------------------------------------------

def cmd_rescore(products: dict, api: str, env: dict, limit: int | None,
                only: str | None, web_calibrate: bool, autoseed: bool) -> None:
    config = sl.load_config()

    # Ensure a baseline exists so even the first re-scored bean has comparables.
    ledger = sl.load_ledger()
    if autoseed and not only:
        ledger = cmd_seed(products)

    drafts = latest_draft_per_id()
    ids = [only] if only else sorted(drafts.keys())
    if limit:
        ids = ids[:limit]

    print(f"Re-scoring {len(ids)} bean(s) via --api {api} ...", file=sys.stderr)
    done = fail = flagged = 0
    for i, pid in enumerate(ids, 1):
        path = drafts.get(pid)
        if not path:
            print(f"[{i}/{len(ids)}] SKIP {pid} (no draft)", file=sys.stderr)
            continue
        text = _read_text(path)
        if _is_mock(text):
            print(f"[{i}/{len(ids)}] SKIP {pid} (mock draft)", file=sys.stderr)
            continue

        product = products.get(pid, {"id": pid, "name": pid})
        scoring_context = sl.format_scoring_context(product, ledger, products, config)
        body = review_body_for_rescore(text)
        prompt = build_scoring_prompt(product, body, scoring_context)

        try:
            out = gr.strip_dashes(call_model(prompt, api, env))
            score, rationale = sl.parse_score_from_text(out)
            if score is None:
                raise ValueError(f"no parseable score in model output: {out[:120]!r}")
            external, divergence = sl.divergence_check(
                score, product, config, web_calibrate=web_calibrate, env=env)
            entry = sl.make_entry(product, score, rationale or "", "backfill-rescore",
                                  external=external, divergence=divergence)
            sl.upsert_entry(ledger, entry)
            sl.save_ledger(ledger)  # checkpoint after each bean
            done += 1
            flag = ""
            if divergence:
                flagged += 1
                flag = f"  ** DIVERGENCE: {divergence}"
            print(f"[{i}/{len(ids)}] {pid}: {score}  {rationale or ''}{flag}", file=sys.stderr)
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(ids)}] FAIL {pid}: {e}", file=sys.stderr)

    print(f"\nRe-scored {done}, failed {fail}, divergences flagged {flagged}.", file=sys.stderr)
    print(f"Ledger: {sl.LEDGER_PATH}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Histogram (before/after)
# ---------------------------------------------------------------------------

def _before_scores(products: dict) -> list[float]:
    out = []
    for pid, path in latest_draft_per_id().items():
        score, _r, mock = parse_draft_score(path)
        if score is not None and not mock:
            out.append(score)
    return out


def _after_scores() -> list[float]:
    ledger = sl.load_ledger()
    return [e["score"] for e in ledger.values() if isinstance(e.get("score"), (int, float))]


def cmd_histogram(products: dict) -> None:
    before = _before_scores(products)
    after = _after_scores()
    print("\n================ BEFORE (scores parsed from existing drafts) ================")
    print(sl.histogram(before))
    print("\n================ AFTER (scores in the rationale ledger) =====================")
    print(sl.histogram(after))
    if before and after:
        import statistics as st
        print("\nSpread change: "
              f"stdev {st.pstdev(before):.2f} -> {st.pstdev(after):.2f}  | "
              f"range {max(before)-min(before):.1f} -> {max(after)-min(after):.1f}  | "
              f"distinct values {len(set(before))} -> {len(set(after))}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Backfill + verify the scoring system")
    p.add_argument("--seed-from-drafts", action="store_true",
                   help="Parse existing drafts into the ledger as the baseline (no API).")
    p.add_argument("--rescore", action="store_true",
                   help="Re-score existing drafts through the new system (uses --api).")
    p.add_argument("--histogram", action="store_true",
                   help="Print BEFORE (drafts) vs AFTER (ledger) histograms (no API).")
    p.add_argument("--api", choices=["claude", "minimax", "claude-code"], default="claude-code",
                   help="Backend for --rescore (default: claude-code, local free Pro tokens).")
    p.add_argument("--limit", type=int, default=None, help="Re-score only the first N beans.")
    p.add_argument("--only", default=None, help="Re-score a single product id.")
    p.add_argument("--web-calibrate", action="store_true", default=False,
                   help="Best-effort web critic lookup for the divergence check (advisory).")
    p.add_argument("--autoseed", action="store_true", default=False,
                   help="Seed the ledger from the OLD-prompt drafts before re-scoring. Off by "
                        "default: those scores are the biased baseline and would anchor the "
                        "re-score back toward 6-7. Cold start lets the rubric set scores fresh.")
    args = p.parse_args()

    if not (args.seed_from_drafts or args.rescore or args.histogram):
        p.error("nothing to do — pass --seed-from-drafts, --rescore, and/or --histogram")

    env = gr.load_env()
    products = gr.load_products()

    if args.seed_from_drafts:
        cmd_seed(products)
    if args.rescore:
        cmd_rescore(products, args.api, env, args.limit, args.only,
                    args.web_calibrate, autoseed=args.autoseed)
    if args.histogram:
        cmd_histogram(products)


if __name__ == "__main__":
    main()
