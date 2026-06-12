# scrapers/qa_drafts.py
"""
Draft-QA gate (RUNBOOK Phase 5.1). Scans generated drafts for the defect classes
that contaminated the June 2026 batch and prints the rating distribution. Promoted
from the throwaway _qa.py so the next batch does not start blind. Gate the batch on
this: zero issues on every dimension before import.

Checks each draft for:
  - em/en dashes or U+FFFD replacement chars (banned in output)
  - first-person consumption claims / crowd attribution (analytical-voice violations)
  - cross-bean comparison leaks in visible prose (anti-comparison rule)
  - missing PRICE_PENDING / price marker
  - agentic chatter (CLI trailers, "I've written", git commands, etc.)
  - duplicate H1 "... Review" headings
  - prose after the <!--SCORE--> block
  - incomplete review format (missing a required section)

Usage:
    python scrapers/qa_drafts.py --since 171                 # the 69-bean batch, today
    python scrapers/qa_drafts.py --since 171 --date 2026-06-12
    python scrapers/qa_drafts.py --ids-file batch.txt
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "scrapers" / "products.json"
DRAFTS = ROOT / "drafts"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

AGENTIC = re.compile(
    r"I tried to save|let me know|ready to paste|git command|needs your permission|"
    r"I've written|paste (it|this) into|written the review to spec|happy to|Would you like|"
    r"```|I'll |I have written|here is the review|here's the review",
    re.I)
FIRST_PERSON = re.compile(
    r"\b(I tried|I brewed|I tasted|I found|I drank|I've had|my cup|buyers say|"
    r"reviewers report|customers note|users find|verified buyers|customers say)\b", re.I)
# Comparison leak: "better/cleaner than <ProperName>" or "past X's 7.4" style
LEAK = re.compile(
    r"(better|cleaner|sharper|worse|smoother|brighter) than [A-Z][a-z]+|"
    r"past [A-Z][a-z]+'s [0-9]\.[0-9]|match(es)? [A-Z][a-z]+'s|"
    r"unlike (the )?[A-Z][a-z]+ [A-Z][a-z]+")
REQUIRED_SECTIONS = ["**One-line verdict**", "### Tasting notes", "### Who it's for",
                     "### Who should skip it", "### Price analysis", "### Rating:", "<!--SCORE"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=None)
    ap.add_argument("--ids-file", default=None)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    if args.ids_file:
        ids = [l.strip() for l in Path(args.ids_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.since is not None:
        ids = [p["id"] for p in products[args.since:]]
    else:
        print("Specify --since N or --ids-file FILE", file=sys.stderr)
        return 2

    T, missing = {}, []
    for pid in ids:
        f = DRAFTS / f"{pid}-{args.date}.md"
        if f.exists():
            T[pid] = f.read_text(encoding="utf-8")
        else:
            missing.append(pid)

    def hits(pred):
        return [pid for pid, t in T.items() if pred(t)]

    dash = hits(lambda t: "—" in t or "–" in t or "�" in t)
    fp = hits(lambda t: FIRST_PERSON.search(t))
    leak = hits(lambda t: LEAK.search(t))
    nomark = hits(lambda t: "PRICE_PENDING" not in t and "Price/oz | $" not in t)
    agent = hits(lambda t: AGENTIC.search(t))
    duph1 = hits(lambda t: len(re.findall(r"^##\s+.+Review\s*$", t, re.M)) > 1)

    aftsc = []
    for pid, t in T.items():
        m = re.search(r"<!--SCORE.*?-->", t, re.S)
        if m:
            tail = re.sub(r"<!--PRICE_PENDING.*?-->", "", t[m.end():], flags=re.S).strip()
            if len(tail) > 3:
                aftsc.append(pid)
    incomplete = [pid for pid, t in T.items() if any(s not in t for s in REQUIRED_SECTIONS)]

    print(f"drafts present: {len(T)} | missing: {len(missing)} {missing if missing else ''}")
    dims = [("dash/replacement", dash), ("first-person/crowd", fp), ("comparison leak", leak),
            ("missing price marker", nomark), ("agentic chatter", agent), ("duplicate H1", duph1),
            ("prose after SCORE", aftsc), ("incomplete format", incomplete)]
    total_issues = 0
    for label, lst in dims:
        total_issues += len(lst)
        print(f"  {label:<22}: {len(lst)} {lst if lst else ''}")

    dist, scores = collections.Counter(), []
    for t in T.values():
        m = re.search(r'###\s*Rating:\s*([0-9]+\.[0-9]+)', t)
        if m:
            s = float(m.group(1)); scores.append(s); dist[s] += 1
    if scores:
        print("\n=== rating distribution ===")
        for s in sorted(dist):
            print(f"  {s:>4}: {dist[s]:>2}  {'#' * dist[s]}")
        print(f"\n n={len(scores)} min={min(scores)} max={max(scores)} "
              f"median={statistics.median(scores)} mean={round(statistics.fmean(scores), 2)} "
              f"stdev={round(statistics.pstdev(scores), 2)}")
        print(f" >=8.0:{sum(1 for s in scores if s >= 8)} | 7.0-7.9:{sum(1 for s in scores if 7 <= s < 8)} | "
              f"5.0-6.9:{sum(1 for s in scores if 5 <= s < 7)} | <5:{sum(1 for s in scores if s < 5)}")

    print(f"\n{'QA CLEAN' if total_issues == 0 and not missing else 'QA ISSUES FOUND'}")
    return 0 if total_issues == 0 and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
