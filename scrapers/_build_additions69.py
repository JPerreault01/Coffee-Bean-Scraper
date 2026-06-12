# scrapers/_build_additions69.py
# One-off builder (batch-specific; not a permanent gate). Adds 69 new beans to
# products.json from data/promotion_candidates.json, deduped against the existing
# catalog, prioritizing beans that carry BOTH a reference-corpus slug AND a strong
# coffeereview critic match (verified specs + independent quality signal). Mirrors
# the June 2026 _build_additions.py sanitizers/roast logic so the new records match
# the catalog's shape exactly.
import json, re, sys, unicodedata
from pathlib import Path

TARGET = 69
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scrapers"))
import reference_db, coffeereview_db  # noqa: E402

CANDS = json.loads((ROOT / "data" / "promotion_candidates.json").read_text(encoding="utf-8"))
PRODUCTS_PATH = ROOT / "scrapers" / "products.json"
PRODS = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))

report = []
def log(*a): report.append(" ".join(str(x) for x in a))

# ---------- sanitizers (from _build_additions.py) ----------
def desmart(s):
    if not s: return s or ""
    for k, v in {"’":"'","‘":"'","“":'"',"”":'"',"–":" ","—":" ","…":"...","ʻ":"'","â€™":"'","|":" ","*":" ","�":""}.items():
        s = s.replace(k, v)
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()

def fix_caps(s):
    return re.sub(r"('|’)([A-Z])", lambda m: m.group(1) + m.group(2).lower(), s)

GRADE_CODES = {"AA","AB","PB","WBC","NX","WX","G1","G2","SL28","SL34","SHB","SHG"}
def title_brand(s):
    s = desmart(s)
    out = []
    for w in s.split():
        out.append(w if (w.upper() in GRADE_CODES or (w.isupper() and len(w) <= 4)) else w[:1].upper() + w[1:])
    return fix_caps(" ".join(out))

def title_words(s):
    s = desmart(s)
    out = []
    for w in s.split():
        out.append(w if w.upper() in GRADE_CODES else w[:1].upper() + w[1:])
    return fix_caps(" ".join(out))

def slugify(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")

def norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def slug_from_url(url):
    m = re.search(r"/beans/([^/?#]+)/?", url or "")
    return m.group(1).lower() if m else ""

# origin artifact repair (accent-stripping left stray single letters / mojibake)
ORIGIN_FIX = {
    "quind o":"Quindio","tarraz":"Tarrazu","chirrip":"Chirripo","h lualoa":"Holualoa",
    "ka u":"Ka'u","hawai i":"Hawai'i","narino":"Narino","piendam":"Piendamo",
}
def clean_origin_token(t):
    t = desmart(t)
    low = t.lower().strip()
    if low in ORIGIN_FIX: return ORIGIN_FIX[low]
    t = re.sub(r"\s+([a-z])\b", lambda m: m.group(1), t)
    return title_words(t)

def cand_origin(c):
    toks = [clean_origin_token(o) for o in c.get("origins", []) if o]
    seen = []
    for t in toks:
        if t and t not in seen: seen.append(t)
    return ", ".join(seen)

# ---------- roast normalization ----------
ROAST_CANON = ["Light","Light-Medium","Medium","Medium-Dark","Dark"]
ROAST_ORD = {"light":1,"blonde":1,"light medium":2,"medium light":2,"light-medium":2,
             "medium":3,"medium dark":4,"medium-dark":4,"dark":5,"french":5,"italian":5,"extra dark":5}
def roast_title(r):
    if not r: return ""
    r = r.replace("�", "").strip()
    if not r: return ""
    for part in [p.strip().lower() for p in r.split(",")]:
        if part in ROAST_ORD:
            return ROAST_CANON[ROAST_ORD[part]-1]
        for t, o in ROAST_ORD.items():
            if t in part:
                return ROAST_CANON[o-1]
    return ""

CANON_TABLE = {"light":1,"blonde":1,"light medium":2,"medium light":2,"medium":3,
               "medium dark":4,"dark":5,"french":5,"italian":5,"extra dark":5}
def canon_roast(r):
    r = (r or "").replace("�", "").replace("-", " ").strip().lower()
    if not r or r in ("na","n a","none"): return ""
    for part in [p.strip() for p in r.split(",")]:
        for t in ["medium dark","medium light","light medium","extra dark","blonde","light","medium","dark","french","italian"]:
            if t in part: return ROAST_CANON[CANON_TABLE[t]-1]
    return ""

def roast_ord(r):
    r = (r or "").strip().lower().replace("-", " ")
    if not r: return None
    table = {"medium dark":4,"medium light":2,"light medium":2,"extra dark":5,"light":1,"blonde":1,"medium":3,"dark":5,"french":5,"italian":5}
    for t in ["medium dark","medium light","light medium","extra dark","blonde","light","medium","dark","french","italian"]:
        if t in r: return table[t]
    return None

def brew_methods(roast, name):
    n = (name or "").lower()
    if "espresso" in n: return ["espresso","moka pot"]
    rl = (roast or "").lower()
    if "light" in rl and "medium" not in rl: return ["pour over","aeropress","drip"]
    if "dark" in rl: return ["french press","drip","cold brew"]
    if not rl: return ["pour over","drip"]
    return ["drip","pour over","french press"]

# ---------- existing identity / dedup ----------
exist_ids = {p["id"] for p in PRODS}
exist_name = {norm(p["name"]) for p in PRODS}
exist_slug = {p.get("reference_slug") for p in PRODS if p.get("reference_slug") and p["reference_slug"] != "_skip"}
def is_dup(c):
    if norm(c["name"]) in exist_name: return True
    if norm(f"{c['roaster']} {c['name']}") in exist_name: return True
    rs = slug_from_url(c.get("url", ""))
    if rs and rs in exist_slug: return True
    return False

# ---------- tiered selection (quality-first) ----------
# Tier 1: monetizable >= 7 AND has critic match AND completeness >= 5  (best: verified + monetizable + quality signal)
# Tier 2: has critic match AND completeness >= 5                       (verified + quality signal)
# Tier 3: completeness >= 5, monetizable >= 4                          (verified specs, listable)
# Roaster diversity cap so the batch is not dominated by one catalog.
ROASTER_CAP = 5
def rb_of(c): return c.get("rank_breakdown", {})
def has_critic(c): return c.get("coffeereview_match") is not None

keepers, seen, roaster_count = [], set(), {}
def consider(pool):
    for c in pool:
        if len(keepers) >= TARGET: break
        if is_dup(c): continue
        key = (norm(c["roaster"]), norm(c["name"]))
        if key in seen: continue
        rk = norm(c["roaster"])
        if rk and roaster_count.get(rk, 0) >= ROASTER_CAP: continue
        seen.add(key); roaster_count[rk] = roaster_count.get(rk, 0) + 1
        keepers.append(c)

byrank = sorted(CANDS, key=lambda c: c["rank_score"], reverse=True)
# Tier 1
consider([c for c in byrank if rb_of(c).get("monetizable",0) >= 7 and has_critic(c) and rb_of(c).get("completeness",0) >= 5])
t1 = len(keepers)
# Tier 2
consider([c for c in sorted(CANDS, key=lambda c:(has_critic(c), rb_of(c).get("completeness",0), c["rank_score"]), reverse=True)
          if has_critic(c) and rb_of(c).get("completeness",0) >= 5])
t2 = len(keepers) - t1
# Tier 3
consider([c for c in byrank if rb_of(c).get("completeness",0) >= 5 and rb_of(c).get("monetizable",0) >= 4])
t3 = len(keepers) - t1 - t2

log(f"Tier 1 (monetizable>=7 + critic + complete): {t1}")
log(f"Tier 2 (critic + complete): {t2}")
log(f"Tier 3 (complete + listable): {t3}")
log(f"TOTAL keepers: {len(keepers)}")
if len(keepers) < TARGET:
    log(f"WARNING: only {len(keepers)} keepers found (< {TARGET}). Widen the pool / lower a tier gate.")

# ---------- spec cross-check (meaningful conflicts only) ----------
STOP = {"province","district","region","county","growing","department","central","southern",
        "northern","western","eastern","south","north","zone","village","island",
        "highlands","valley","coffee","arabica","species","all","of","the","not","disclosed",
        "na","blend","grande","de","la","el","los","las","du",
        "states","united","america","americas","africa","asia","latin"}
def words(strs):
    out = set()
    for s in strs:
        for w in re.findall(r"[a-z]{4,}", norm(s)):
            if w.startswith("hawai"): w = "hawaii"
            if w not in STOP: out.add(w)
    return out

cr_conn = coffeereview_db.get_conn(str(ROOT / "data" / "coffeereview.db"))
roast_conflicts, origin_conflicts = [], []
critic_roast_by_slug = {}
for c in keepers:
    m = c.get("coffeereview_match")
    if not m: continue
    specs = coffeereview_db.get_specs(cr_conn, m["slug"]) or {}
    cr_roast = canon_roast(specs.get("roast_level", ""))
    if cr_roast:
        critic_roast_by_slug[slug_from_url(c.get("url",""))] = cr_roast
    ro, co = roast_ord(c.get("roast_level","")), roast_ord(specs.get("roast_level",""))
    if ro and co and abs(ro-co) >= 2:
        roast_conflicts.append((c["name"], c["roaster"], c.get("roast_level"), specs.get("roast_level")))
    rw, cw = words(c.get("origins",[])), words(specs.get("origins",[]))
    if rw and cw and not (rw & cw):
        origin_conflicts.append((c["name"], c["roaster"], sorted(rw), sorted(cw)))
cr_conn.close()

# ---------- build product records ----------
new_records = []; used = set(exist_ids)
def uid(base):
    i = base or "bean"; n = 2
    while i in used: i = f"{base}-{n}"; n += 1
    used.add(i); return i

unknown_roast = []; roast_filled = []
for c in keepers:
    brand = title_brand(c["roaster"]) or "Unknown"
    raw = desmart(c["name"])
    bw = norm(brand).split()[0] if norm(brand) else ""
    full = raw if (bw and norm(raw).startswith(bw)) else f"{brand} {raw}"
    full = desmart(full)
    ref_slug = slug_from_url(c.get("url", ""))
    rt = roast_title(c.get("roast_level", ""))
    if not rt:
        cr_fill = critic_roast_by_slug.get(ref_slug, "")
        if cr_fill:
            rt = cr_fill; roast_filled.append((full, cr_fill))
        else:
            unknown_roast.append(full)
    rec = {
        "id": uid(slugify(f"{brand}-{raw}")[:58].strip("-")),
        "name": full,
        "brand": brand,
        "roast_level": rt,
        "origin": cand_origin(c),
        "process_method": title_words(", ".join(c.get("processing", []))),
        "weight_oz": 12,
        "amazon_asin": None,
        "roaster_url": desmart(c.get("roaster_url","")) or None,
        "affiliate_tag": None,
        "best_brew_methods": brew_methods(rt, c["name"]),
        "flavor_notes": [desmart(f).lower() for f in c.get("flavor_notes", [])[:5]],
        "acidity": None, "body": None, "sweetness": None, "bitterness": None, "roast_intensity": None,
        "review_framing": None,
        "comparison_anchors": [],
        "reference_slug": ref_slug or None,
    }
    new_records.append(rec)

new_with_slug = sum(1 for r in new_records if r["reference_slug"])
new_with_critic = sum(1 for c in keepers if c.get("coffeereview_match"))

merged = PRODS + new_records
PRODUCTS_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

log("")
log(f"New records: {len(new_records)} | reference_slug: {new_with_slug} | critic match: {new_with_critic}")
log(f"== ROAST BACKFILLED FROM CRITIC SPEC: {len(roast_filled)} ==")
for nm, rv in roast_filled: log(f"  [filled->{rv}] {nm}")
log(f"Still blank after backfill: {len(unknown_roast)}")
for nm in unknown_roast: log(f"  [blank] {nm}")
log("")
log(f"== ROAST CONFLICTS (ref vs critic >=2 bands): {len(roast_conflicts)} ==")
for nm, r, a, b in roast_conflicts: log(f"  - {nm} [{r}]: corpus='{a}' vs critic='{b}'")
log(f"== ORIGIN CONFLICTS (no shared word): {len(origin_conflicts)} ==")
for nm, r, a, b in origin_conflicts: log(f"  - {nm} [{r}]: corpus={a} vs critic={b}")
log("")
log("New records (id | brand | roast | origin | #flavors | critic):")
for c, r in zip(keepers, new_records):
    log(f"  {r['id'][:46]:<46} | {r['brand'][:16]:<16} | {(r['roast_level'] or '(blank)'):<11} | {r['origin'][:30]:<30} | {len(r['flavor_notes'])} | {'CR' if c.get('coffeereview_match') else '--'}")

(ROOT / "data" / "_additions69_report.txt").write_text("\n".join(report), encoding="utf-8")
print(f"REPORT WRITTEN; new records: {len(new_records)}; total now: {len(merged)}")
