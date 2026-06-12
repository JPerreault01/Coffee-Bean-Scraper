# Temporary (not committed): normalize ALL-CAPS words in product names/brands to
# Title Case while preserving codes/acronyms (AA, PB, WBC, SL28, G1, AK-47, roman
# numerals). Reports every change. Run once against products.json.
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT/"scrapers"/"products.json"
prods = json.loads(P.read_text(encoding="utf-8"))

# Real coffee grades / abbreviations that must stay uppercase. Everything else that
# is all-caps gets title-cased (THE->The, CO->Co, KENYA->Kenya).
KEEP_UPPER = {"AA","AB","PB","AA+","A","WBC","FCS","SL","NX","WX","XO","SO","DR",
              "RFA","EU","US","USA","OMNI","II","III","IV","VI","G1","WP","CM"}

def fix_word(w):
    core = w.strip(".")               # treat "CO." like "CO"
    if any(ch.isdigit() for ch in w):
        return w                      # codes: SL28, G1, AK-47, 6NB, 18V
    if core.upper() in KEEP_UPPER:
        return w                      # keep grade/abbrev as written (already upper)
    if w.isupper():
        return w.capitalize()         # all-caps word -> Title (incl. THE->The, CO.->Co.)
    return w                          # preserve existing mixed case

def normalize(s):
    return " ".join(fix_word(w) for w in s.split())

changes = []
for p in prods:
    for field in ("name","brand"):
        old = p.get(field) or ""
        new = normalize(old)
        if new != old:
            changes.append((field, old, new))
            p[field] = new

P.write_text(json.dumps(prods, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Catalog size: {len(prods)} | fields changed: {len(changes)}")
for field, old, new in changes:
    print(f"  [{field}] {old!r} -> {new!r}")
