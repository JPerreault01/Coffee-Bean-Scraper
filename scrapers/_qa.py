import json,os,re,statistics,collections
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d=json.load(open(os.path.join(ROOT,'scrapers','products.json'),encoding='utf-8'))
new=d[71:]
def path(i): return os.path.join(ROOT,'drafts',f"{i}-2026-06-10.md")
missing=[p['id'] for p in new if not os.path.exists(path(p['id']))]
T={p['id']:open(path(p['id']),encoding='utf-8').read() for p in new if os.path.exists(path(p['id']))}

agentic=re.compile(r"I tried to save|let me know|ready to paste|git command|needs your permission|I've written|paste (it|this) into|Three diversity claims|No em/en dash|woven in:|written the review to spec|happy to|Would you like",re.I)
def cnt(pred): return [i for i,t in T.items() if pred(t)]
dash=cnt(lambda t:'—'in t or '–'in t or '�'in t)
fp=cnt(lambda t:re.search(r"\b(I tried|I brewed|I tasted|I found|buyers say|reviewers report|customers note|users find)\b",t,re.I))
leak=cnt(lambda t:re.search(r"than (Koa|Onyx|Volcanica|Intelligentsia|Stumptown|Lavazza|Peet|Lily|Four Barrel|Studio|Hermetic|Sey)\b|past [A-Z][a-z]+'s [0-9]\.[0-9]|match [A-Z][a-z]+'s",t))
nomark=cnt(lambda t:'PRICE_PENDING'not in t)
agent=cnt(lambda t:agentic.search(t))
duph1=cnt(lambda t:len(re.findall(r"^##\s+.+Review\s*$",t,re.M))>1)
aftsc=[]
for i,t in T.items():
    m=re.search(r"<!--SCORE.*?-->",t,re.S)
    if m:
        tail=re.sub(r"<!--PRICE_PENDING.*?-->","",t[m.end():],flags=re.S).strip()
        if len(tail)>3: aftsc.append(i)
secs=["**One-line verdict**","### Tasting notes","### Who it's for","### Who should skip it","### Price analysis","### Rating:","<!--SCORE"]
incomplete=[i for i,t in T.items() if any(s not in t for s in secs)]

print("drafts present:",len(T),"| missing:",len(missing),missing)
for label,lst in [("dash/replacement",dash),("first-person/crowd",fp),("comparison leak",leak),
                  ("missing price marker",nomark),("agentic chatter",agent),("duplicate H1",duph1),
                  ("prose after SCORE",aftsc),("incomplete format",incomplete)]:
    print(f"  {label:<22}: {len(lst)} {lst if lst else ''}")

dist=collections.Counter(); scores=[]
for t in T.values():
    m=re.search(r'###\s*Rating:\s*([0-9]+\.[0-9]+)',t)
    if m: s=float(m.group(1)); scores.append(s); dist[s]+=1
print("\n=== rating distribution (all 100) ===")
for s in sorted(dist): print(f"  {s:>4}: {dist[s]:>2}  {'#'*dist[s]}")
print(f"\n n={len(scores)} min={min(scores)} max={max(scores)} median={statistics.median(scores)} mean={round(statistics.fmean(scores),2)} stdev={round(statistics.pstdev(scores),2)}")
print(f" >=8.0:{sum(1 for s in scores if s>=8)} | 7.0-7.9:{sum(1 for s in scores if 7<=s<8)} | 5.0-6.9:{sum(1 for s in scores if 5<=s<7)} | <5:{sum(1 for s in scores if s<5)}")
