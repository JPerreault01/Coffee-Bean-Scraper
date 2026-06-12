# Temporary builder (not committed): select 100 keepers, derive product records,
# spec-cross-check against coffeereview matches, conservatively map reference_slug
# for the existing catalog. Writes merged products.json + a UTF-8 report.
import json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scrapers"))
import reference_db, coffeereview_db

CANDS = json.loads((ROOT/"data"/"promotion_candidates.json").read_text(encoding="utf-8"))
PRODUCTS_PATH = ROOT/"scrapers"/"products.json"
PRODS = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))

report = []
def log(*a): report.append(" ".join(str(x) for x in a))

# ---------- sanitizers ----------
def desmart(s):
    if not s: return s or ""
    for k,v in {"’":"'","‘":"'","“":'"',"”":'"',"–":" ","—":" ","…":"...","ʻ":"'","â€™":"'","|":" ","*":" ","�":""}.items():
        s = s.replace(k,v)
    s = s.replace(" "," ")
    return re.sub(r"\s+"," ", s).strip()

def fix_caps(s):
    # lowercase a letter that was capitalized right after an apostrophe (Hawai'I -> Hawai'i)
    return re.sub(r"('|’)([A-Z])", lambda m: m.group(1)+m.group(2).lower(), s)

def title_brand(s):
    s = desmart(s)
    out=[]
    for w in s.split():
        out.append(w if (w.isupper() and len(w)<=4) else w[:1].upper()+w[1:])
    return fix_caps(" ".join(out))

def title_words(s):
    s = desmart(s)
    return fix_caps(" ".join(w[:1].upper()+w[1:] for w in s.split()))

def slugify(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii","ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+","-",value).strip("-")

def norm(s): return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()

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
    # collapse a stray single trailing/standalone letter that came from a dropped accent
    t = re.sub(r"\s+([a-z])\b", lambda m: m.group(1), t)  # "quind o" handled above; this catches others
    return title_words(t)

def cand_origin(c):
    toks = [clean_origin_token(o) for o in c.get("origins",[]) if o]
    seen=[];
    for t in toks:
        if t and t not in seen: seen.append(t)
    return ", ".join(seen)

# ---------- roast normalization ----------
ROAST_CANON = ["Light","Light-Medium","Medium","Medium-Dark","Dark"]
ROAST_ORD = {"light":1,"blonde":1,"light medium":2,"medium light":2,"light-medium":2,
             "medium":3,"medium dark":4,"medium-dark":4,"dark":5,"french":5,"italian":5,"extra dark":5}
def roast_title(r):
    if not r: return ""
    r = r.replace("�","").strip()
    if not r: return ""
    # multi-value like "medium dark, medium light" -> take the first token that maps
    for part in [p.strip().lower() for p in r.split(",")]:
        if part in ROAST_ORD:
            o = ROAST_ORD[part]
            return ROAST_CANON[o-1]
        for t,o in ROAST_ORD.items():
            if t in part:
                return ROAST_CANON[o-1]
    return ""  # unknown/corrupt -> blank (safer than guessing)
CANON_TABLE={"light":1,"blonde":1,"light medium":2,"medium light":2,"medium":3,
             "medium dark":4,"dark":5,"french":5,"italian":5,"extra dark":5}
def canon_roast(r):
    """Canonicalize any roast string (incl. hyphenated critic values) to the site's
    5-band vocabulary, or '' if unknown/na."""
    r=(r or "").replace("�","").replace("-"," ").strip().lower()
    if not r or r in ("na","n a","none"): return ""
    for part in [p.strip() for p in r.split(",")]:
        for t in ["medium dark","medium light","light medium","extra dark",
                  "blonde","light","medium","dark","french","italian"]:
            if t in part: return ROAST_CANON[CANON_TABLE[t]-1]
    return ""

def roast_ord(r):
    r=(r or "").strip().lower().replace("-"," ")
    if not r: return None
    table={"medium dark":4,"medium light":2,"light medium":2,"extra dark":5,
           "light":1,"blonde":1,"medium":3,"dark":5,"french":5,"italian":5}
    for t in ["medium dark","medium light","light medium","extra dark",
              "blonde","light","medium","dark","french","italian"]:
        if t in r: return table[t]
    return None

def brew_methods(roast, name):
    n=(name or "").lower()
    if "espresso" in n: return ["espresso","moka pot"]
    rl=(roast or "").lower()
    if "light" in rl and "medium" not in rl: return ["pour over","aeropress","drip"]
    if "dark" in rl: return ["french press","drip","cold brew"]
    if not rl: return ["pour over","drip"]   # unknown roast -> safe filter-forward default
    return ["drip","pour over","french press"]

# ---------- existing identity / dedup ----------
exist_ids = {p["id"] for p in PRODS}
exist_name = {norm(p["name"]) for p in PRODS}
def is_dup(c):
    if norm(c["name"]) in exist_name: return True
    if norm(f"{c['roaster']} {c['name']}") in exist_name: return True
    return False

# ---------- tiered selection ----------
tier1, seen = [], set()
for c in sorted(CANDS, key=lambda c: c["rank_score"], reverse=True):
    rb=c.get("rank_breakdown",{})
    if rb.get("monetizable",0) < 7 or rb.get("completeness",0) < 5: continue
    if is_dup(c): continue
    key=(norm(c["roaster"]),norm(c["name"]))
    if key in seen: continue
    seen.add(key); tier1.append(c)

tier2=[]
for c in sorted(CANDS, key=lambda c:(c.get("coffeereview_match") is not None, c["rank_breakdown"].get("completeness",0), c["rank_score"]), reverse=True):
    if len(tier1)+len(tier2) >= 100: break
    rb=c.get("rank_breakdown",{})
    if c in tier1 or is_dup(c) or rb.get("completeness",0) < 5: continue
    key=(norm(c["roaster"]),norm(c["name"]))
    if key in seen: continue
    if sum(1 for x in tier2 if norm(x["roaster"])==norm(c["roaster"])) >= 4: continue
    seen.add(key); tier2.append(c)

keepers = tier1 + tier2
log(f"Tier 1 (monetizable>=7): {len(tier1)}")
log(f"Tier 2 (informational fill): {len(tier2)}")
log(f"TOTAL keepers: {len(keepers)}")

# ---------- spec cross-check (meaningful conflicts only) ----------
STOP = {"province","district","region","county","growing","department","central","southern",
        "northern","western","eastern","south","north","zone","village","island","district",
        "highlands","valley","coffee","arabica","species","all","of","the","not","disclosed",
        "na","blend","district","grande","de","la","el","los","las","du",
        # too-generic to anchor a country match
        "states","united","america","americas","africa","asia","latin"}
def words(strs):
    out=set()
    for s in strs:
        for w in re.findall(r"[a-z]{4,}", norm(s)):
            if w.startswith("hawai"): w="hawaii"   # hawaii/hawai'i variants
            if w not in STOP: out.add(w)
    return out

cr_conn = coffeereview_db.get_conn(str(ROOT/"data"/"coffeereview.db"))
roast_conflicts, origin_conflicts = [], []
critic_roast_by_slug = {}   # reference-corpus slug -> critic's canonical roast (for backfill)
for c in keepers:
    m=c.get("coffeereview_match")
    if not m: continue
    specs=coffeereview_db.get_specs(cr_conn, m["slug"]) or {}
    cr_roast = canon_roast(specs.get("roast_level",""))
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
new_records=[]; used=set(exist_ids)
def uid(base):
    i=base or "bean"; n=2
    while i in used: i=f"{base}-{n}"; n+=1
    used.add(i); return i

unknown_roast=[]; roast_filled=[]
for c in keepers:
    brand=title_brand(c["roaster"]) or "Unknown"
    raw=desmart(c["name"])
    bw=norm(brand).split()[0] if norm(brand) else ""
    full = raw if (bw and norm(raw).startswith(bw)) else f"{brand} {raw}"
    full=desmart(full)
    ref_slug = slug_from_url(c.get("url",""))
    rt=roast_title(c.get("roast_level",""))
    if not rt:
        # Decision 2: backfill blank corpus roast from the critic's FACTUAL roast_level
        # (spec cross-check, inside the firewall — never touches the score).
        cr_fill = critic_roast_by_slug.get(ref_slug, "")
        if cr_fill:
            rt = cr_fill
            roast_filled.append((full, cr_fill))
        else:
            unknown_roast.append(full)
    rec={
        "id": uid(slugify(f"{brand}-{raw}")[:58].strip("-")),
        "name": full,
        "brand": brand,
        "roast_level": rt,
        "origin": cand_origin(c),
        "process_method": title_words(", ".join(c.get("processing",[]))),
        "weight_oz": 12,
        "amazon_asin": None,
        "roaster_url": desmart(c.get("roaster_url","")) or None,
        "affiliate_tag": None,
        "best_brew_methods": brew_methods(rt, c["name"]),
        "flavor_notes": [desmart(f).lower() for f in c.get("flavor_notes",[])[:5]],
        "acidity": None,"body": None,"sweetness": None,"bitterness": None,"roast_intensity": None,
        "review_framing": None,
        "comparison_anchors": [],
        "reference_slug": slug_from_url(c.get("url","")) or None,
    }
    new_records.append(rec)

# Decision 3: override Stumptown Founder's Blend origin. Corpus said "Indonesia, Sumatra"
# (incomplete) and the critic guessed "Burundi, Colombia" (wrong). Verified on
# stumptowncoffee.com/products/founders-blend: organic beans from South & Central America
# paired with organic Sumatra, Indonesia.
FOUNDERS_ORIGIN = "Central America, South America, Sumatra blend"
founders_fixed = None
for r in new_records:
    if "founder" in r["id"] and "stumptown" in r["id"]:
        founders_fixed = (r["name"], r["origin"], FOUNDERS_ORIGIN)
        r["origin"] = FOUNDERS_ORIGIN
        break

new_with_slug=sum(1 for r in new_records if r["reference_slug"])
new_with_critic=sum(1 for c in keepers if c.get("coffeereview_match"))

# ---------- conservative reference_slug for existing 71 ----------
ref_conn=reference_db.get_conn(str(ROOT/"data"/"coffee_reference.db"))
mapped=unmatched=0; skipped=[]; mapped_list=[]; rejected_list=[]
for p in PRODS:
    if p.get("reference_slug")=="_skip": skipped.append(p["id"]); continue
    if p.get("reference_slug"): continue
    hits=reference_db.find_coffee(ref_conn, p.get("name",""), p.get("brand"))
    if not hits or hits[0][0] < 0.78:
        unmatched+=1; continue
    score, slug = hits[0][0], hits[0][1]
    sp = reference_db.get_specs(ref_conn, slug) or {}
    cn = (sp.get("name") or "").lower()
    cr = norm(sp.get("roaster") or "")
    pn = p.get("name","").lower(); pb = norm(p.get("brand",""))
    brand_tok = pb.split()[0] if pb else ""
    decaf_ok = ("decaf" in cn) == ("decaf" in pn)
    roaster_ok = (brand_tok and brand_tok in cr) or score >= 0.92
    if score >= 0.82 and decaf_ok and roaster_ok:
        p["reference_slug"]=slug; mapped+=1
        mapped_list.append((p["name"], slug, round(score,2)))
    else:
        unmatched+=1
        reason = []
        if score < 0.82: reason.append("low-score")
        if not decaf_ok: reason.append("decaf-mismatch")
        if not roaster_ok: reason.append("roaster-mismatch")
        rejected_list.append((p["name"], slug, round(score,2), ",".join(reason)))
ref_conn.close()

merged=PRODS+new_records
PRODUCTS_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

log("")
log(f"New records: {len(new_records)} | all have reference_slug: {new_with_slug} | carry coffeereview_match: {new_with_critic}")
log("")
log(f"== ROAST BACKFILLED FROM CRITIC SPEC CROSS-CHECK: {len(roast_filled)} ==")
for nm,rv in roast_filled: log(f"  [filled->{rv}] {nm}")
log(f"Still blank after backfill (no critic roast): {len(unknown_roast)}")
for nm in unknown_roast: log(f"  [blank] {nm}")
log("")
if founders_fixed:
    log(f"== FOUNDER'S BLEND ORIGIN OVERRIDE (web-verified) ==")
    log(f"  {founders_fixed[0]}: '{founders_fixed[1]}' -> '{founders_fixed[2]}'")
log("")
log(f"Existing 71: reference_slug mapped (guarded): {mapped} | left null: {unmatched} | preserved _skip: {len(skipped)}")
for nm,sl,sc in mapped_list: log(f"    MAPPED  {nm[:40]:<40} -> {sl} ({sc})")
log("  Rejected existing matches (left null, runtime fuzzy still applies):")
for nm,sl,sc,why in rejected_list[:12]: log(f"    skip   {nm[:40]:<40} -x {sl[:30]} ({sc}; {why})")
log(f"TOTAL products now: {len(merged)}")
log("")
log(f"== ROAST CONFLICTS (ref vs critic differ >=2 bands): {len(roast_conflicts)} ==")
for nm,r,a,b in roast_conflicts: log(f"  - {nm} [{r}]: corpus='{a}' vs critic='{b}'")
log("")
log(f"== ORIGIN CONFLICTS (no shared country/region word): {len(origin_conflicts)} ==")
for nm,r,a,b in origin_conflicts: log(f"  - {nm} [{r}]: corpus={a} vs critic={b}")
log("")
log("Tier-1 keepers (monetizable, id | brand | roast | origin):")
for r in new_records[:len(tier1)]:
    log(f"  {r['id'][:40]:<40} | {r['brand'][:18]:<18} | {r['roast_level'] or '(blank)':<11} | {r['origin'][:34]}")

(ROOT/"data"/"_additions_report.txt").write_text("\n".join(report), encoding="utf-8")
print("REPORT WRITTEN; new records:", len(new_records))
