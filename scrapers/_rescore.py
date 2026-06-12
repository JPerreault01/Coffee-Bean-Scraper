# Temporary (not committed): cold rescore of the 100 NEW beans with the nudged rubric,
# patching the new score+rationale back into each draft. Resumable across Pro limits.
import json, os, re, sys, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scrapers"))
import score_ledger as sl
import backfill_scores as bf
import generate_review as gr

PRODUCTS = json.loads((ROOT/"scrapers"/"products.json").read_text(encoding="utf-8"))
BY_ID = {p["id"]: p for p in PRODUCTS}
EXISTING_IDS = [p["id"] for p in PRODUCTS[:71]]
NEW_IDS = [p["id"] for p in PRODUCTS[71:]]
DONE_FILE = ROOT/"drafts"/"_rescore_done.txt"
PROG = ROOT/"drafts"/"_rescore_progress.log"
config = sl.load_config()

def log(m):
    with open(PROG,"a",encoding="utf-8") as f: f.write(m+"\n")
    print(m, file=sys.stderr)

# Robust Opus claude-code call (bytes -> utf-8/cp1252), mirrors generate_review fix.
def call_opus(prompt: str) -> str:
    exe = shutil.which("claude")
    if not exe: raise RuntimeError("claude CLI not found")
    base = [exe, "-p", "--model", "opus"]
    args = (["cmd","/c"]+base) if os.name=="nt" else base
    r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, timeout=300)
    out = r.stdout or b""
    try: text = out.decode("utf-8")
    except UnicodeDecodeError: text = out.decode("cp1252", errors="replace")
    if r.returncode != 0 or not text.strip():
        raise RuntimeError(f"claude exit {r.returncode}; no output")
    return text

def patch_draft(text: str, score: float, rationale: str) -> str:
    s = f"{score:.1f}"
    # 1) Rating heading number
    text = re.sub(r"(###\s*Rating:\s*)[0-9]+\.[0-9]+(\s*/\s*10)",
                  lambda m: f"{m.group(1)}{s}{m.group(2)}", text, count=1)
    # 2) justification line directly under the heading
    text = re.sub(r"(###\s*Rating:\s*[0-9]+\.[0-9]+\s*/\s*10[ \t]*\n)([^\n]*\n)",
                  lambda m: f"{m.group(1)}{rationale}\n", text, count=1)
    # 3) SCORE block
    text = re.sub(r"<!--SCORE.*?-->",
                  lambda m: f"<!--SCORE\nscore: {s}\nrationale: {rationale}\n-->",
                  text, count=1, flags=re.S)
    return text

def latest():
    return bf.latest_draft_per_id()

def main():
    drafts = latest()
    # First run: back up ledger, rebuild a COLD ledger seeded ONLY from the existing 71.
    if not DONE_FILE.exists():
        if sl.LEDGER_PATH.exists():
            shutil.copy(sl.LEDGER_PATH, str(sl.LEDGER_PATH)+".prebackfill.bak")
        cold = {}
        seeded = 0
        for pid in EXISTING_IDS:
            p = drafts.get(pid)
            if not p: continue
            sc, ra, mock = bf.parse_draft_score(p)
            if mock or sc is None: continue
            cold[pid] = sl.make_entry(BY_ID.get(pid,{"id":pid,"name":pid}), sc,
                                      ra or "(existing-catalog baseline)", "cold-seed")
            seeded += 1
        sl.save_ledger(cold)
        DONE_FILE.write_text("", encoding="utf-8")
        log(f"[cold-seed] ledger reset to {seeded} existing-catalog anchors (backup written)")

    ledger = sl.load_ledger()
    done = set(x.strip() for x in DONE_FILE.read_text(encoding="utf-8").splitlines() if x.strip())
    todo = [i for i in NEW_IDS if i not in done]
    log(f"[start] {len(done)} already rescored, {len(todo)} to go")

    for n, pid in enumerate(todo, 1):
        path = drafts.get(pid)
        if not path:
            log(f"[{n}/{len(todo)}] SKIP {pid} (no draft)"); continue
        text = bf._read_text(path)
        product = BY_ID.get(pid, {"id": pid, "name": pid})
        body = bf.review_body_for_rescore(text)
        # RUBRIC-ONLY mode: drop the comparative context so the absolute rubric bands
        # govern the number (comparative gravity was compressing everything to ~7.1).
        if os.environ.get("RESCORE_RUBRIC_ONLY") == "1":
            ctx = ""
        else:
            ctx = sl.format_scoring_context(product, ledger, BY_ID, config)
        prompt = bf.build_scoring_prompt(product, body, ctx)
        try:
            out = gr.strip_dashes(call_opus(prompt))
            score, rationale = sl.parse_score_from_text(out)
            if score is None:
                raise ValueError(f"no parseable score: {out[:100]!r}")
            rationale = (rationale or "").strip()
            # patch the draft, then re-truncate any trailing junk just in case
            newtext = patch_draft(text, score, rationale)
            path.write_text(newtext, encoding="utf-8")
            # update ledger so later beans anchor to cold-rescored neighbours
            ext, div = sl.divergence_check(score, product, config)
            sl.upsert_entry(ledger, sl.make_entry(product, score, rationale, "cold-rescore",
                                                  external=ext, divergence=div))
            sl.save_ledger(ledger)
            with open(DONE_FILE,"a",encoding="utf-8") as f: f.write(pid+"\n")
            log(f"[{n}/{len(todo)}] OK {pid}: {score}")
        except Exception as e:
            log(f"[{n}/{len(todo)}] FAIL {pid}: {e}")
    remaining = [i for i in NEW_IDS if i not in set(x.strip() for x in DONE_FILE.read_text(encoding='utf-8').splitlines() if x.strip())]
    log(f"[end] remaining: {len(remaining)}")
    print("RESCORE_REMAINING="+str(len(remaining)))

if __name__ == "__main__":
    main()
