# scrapers/run_batch_generation.py
"""
Resumable batch driver for generate_review.py (RUNBOOK Phase 2). Generates drafts
for a set of product ids via the claude-code backend, one at a time, and
checkpoints progress so a Pro-window exhaustion (or any interruption) can be
resumed without re-running completed beans.

A draft is considered DONE if drafts/<id>-<DATE>.md already exists, so the run is
idempotent: re-invoking it picks up exactly where it stopped.

Usage:
    # generate every product from index 171 on (the 69-bean batch), today's date:
    CBI_CC_MODEL=opus python scrapers/run_batch_generation.py --since 171
    # or an explicit id list file (one id per line):
    CBI_CC_MODEL=opus python scrapers/run_batch_generation.py --ids-file batch.txt
    # stop after N successes this run (stay under the Pro window cap):
    CBI_CC_MODEL=opus python scrapers/run_batch_generation.py --since 171 --max 40
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "scrapers" / "products.json"
DRAFTS = ROOT / "drafts"
PROGRESS = ROOT / "data" / "_batch69_progress.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def draft_path(pid: str, date: str) -> Path:
    return DRAFTS / f"{pid}-{date}.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=None)
    ap.add_argument("--ids-file", default=None)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--max", type=int, default=None, help="Stop after this many successes this run")
    ap.add_argument("--stop-after-fails", type=int, default=4,
                    help="Abort the run after this many consecutive failures (likely Pro-window cap)")
    args = ap.parse_args()

    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    if args.ids_file:
        ids = [l.strip() for l in Path(args.ids_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.since is not None:
        ids = [p["id"] for p in products[args.since:]]
    else:
        print("Specify --since N or --ids-file FILE", file=sys.stderr)
        return 2

    done, failed, did = [], [], 0
    consecutive_fail = 0
    remaining = [pid for pid in ids if not draft_path(pid, args.date).exists()]
    already = len(ids) - len(remaining)
    print(f"Batch: {len(ids)} ids | already done: {already} | to generate: {len(remaining)}")

    for i, pid in enumerate(remaining, 1):
        if args.max is not None and did >= args.max:
            print(f"Reached --max {args.max} for this run; stopping (resume to continue).")
            break
        print(f"\n[{i}/{len(remaining)}] generating {pid} ...", flush=True)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scrapers" / "generate_review.py"), pid, "--api", "claude-code"],
            capture_output=True,
        )
        ok = proc.returncode == 0 and draft_path(pid, args.date).exists()
        if ok:
            done.append(pid); did += 1; consecutive_fail = 0
            # echo the ledger score line if present
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            score = next((l for l in reversed(tail) if "scored" in l), "")
            print(f"   OK  {score}")
        else:
            failed.append(pid); consecutive_fail += 1
            err = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
            print(f"   FAIL (exit {proc.returncode}): {' | '.join(err)}")
            if consecutive_fail >= args.stop_after_fails:
                print(f"\n{consecutive_fail} consecutive failures — likely Pro-window cap. "
                      f"Stopping. Re-run this script to resume the remainder.")
                break

    still = [pid for pid in ids if not draft_path(pid, args.date).exists()]
    PROGRESS.write_text(json.dumps(
        {"date": args.date, "total": len(ids), "done_this_run": done,
         "failed_this_run": failed, "remaining": still}, indent=2), encoding="utf-8")
    print(f"\n=== batch summary ===\n done this run: {len(done)} | failed: {len(failed)} | "
          f"remaining overall: {len(still)} -> {PROGRESS.name}")
    return 0 if not still else 1


if __name__ == "__main__":
    sys.exit(main())
