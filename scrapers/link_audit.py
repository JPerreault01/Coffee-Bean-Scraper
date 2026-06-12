# scrapers/link_audit.py
"""
Amazon ASIN resolver + link health auditor for products.json.

Two jobs, one toolchain. Both share the PA-API SigV4 signing, the requests
session, and the products.json IO used elsewhere in the pipeline.

  resolve  -- find a verified Amazon ASIN for every product that lacks one.
              PA-API SearchItems first (authoritative), amazon.com/s scrape as
              fallback. Every candidate is scored against the product (brand
              token, name overlap, weight) so a wrong-size or accessory result
              never gets written. High-confidence matches can be written into
              products.json (--write); everything else is parked in a review
              file for human approval.

  check    -- routine broken-link health for amazon_asin (/dp/{asin}) and
              roaster_url. Detects 404, "currently unavailable", Shopify
              "sold out", and the silent failure where a discontinued product
              URL redirects to the store homepage. A state cache + --max-age
              make daily cron runs cheap: only stale/changed links are re-hit.
              Exits non-zero when anything is BROKEN so cron can alert.

Examples
--------
  # Daily cron: re-check only links older than 7 days, alert on breakage.
  python3 scrapers/link_audit.py check --max-age 7

  # Force a full re-check of everything.
  python3 scrapers/link_audit.py check --all

  # Propose ASINs for the first 30 missing, dry-run (writes review file only).
  python3 scrapers/link_audit.py resolve --limit 30

  # Resolve all, auto-write only near-certain matches (>=0.85, makes a .bak).
  python3 scrapers/link_audit.py resolve --write

Dependencies: requests, beautifulsoup4, lxml  (all already in requirements.txt)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths (same resolve pattern as fetch_bean_images.py)
# ---------------------------------------------------------------------------

_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


ENV_FILE      = _resolve("/opt/.env", _REPO_ROOT / ".env")
PRODUCTS_FILE = _resolve("/opt/scrapers/products.json", _SCRAPERS_DIR / "products.json")
DATA_DIR      = _resolve("/opt/data", _REPO_ROOT / "data")
STATE_FILE    = DATA_DIR / "link_state.json"
HEALTH_REPORT = DATA_DIR / "link_health_report.json"
ASIN_REVIEW   = DATA_DIR / "asin_candidates.json"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BASE_HEADERS = {
    "User-Agent":      USER_AGENT,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}
_AMAZON_EXTRA = {
    "Referer":                   "https://www.google.com/",
    "sec-ch-ua":                 '"Chromium";v="120", "Not_A Brand";v="99"',
    "sec-ch-ua-platform":        '"Linux"',
    "Sec-Fetch-Dest":            "document",
    "Sec-Fetch-Mode":            "navigate",
    "Sec-Fetch-Site":            "none",
    "Sec-Fetch-User":            "?1",
    "Upgrade-Insecure-Requests": "1",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("link_audit")

_ENV: dict = {}

# Words that carry no brand-identity signal when matching titles.
_BRAND_STOPWORDS = {
    "coffee", "coffees", "roasters", "roaster", "roasting", "co", "company",
    "the", "and", "of", "llc", "inc", "blend", "beans", "bean",
}
_NAME_STOPWORDS = _BRAND_STOPWORDS | {
    "whole", "ground", "medium", "dark", "light", "roast", "organic",
    "espresso", "arabica", "oz", "ounce", "lb", "pound", "single", "origin",
}

# Tokens that betray a non-coffee accessory/merch listing. Amazon search will
# surface these for a brand query; they must never match a bean product.
_ACCESSORY_TOKENS = {
    "mug", "tumbler", "cup", "ceramic", "filter", "filters", "machine", "maker",
    "grinder", "kettle", "scale", "sticker", "shirt", "tshirt", "hoodie", "hat",
    "gift", "merch", "press", "dripper", "carafe", "frother", "k-cup", "kcup",
    "pods", "pod", "capsule", "capsules", "subscription", "syrup", "creamer",
}


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env: dict = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        log.error("products.json not found at %s", PRODUCTS_FILE)
        sys.exit(1)
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_products(products: list[dict]) -> None:
    backup = PRODUCTS_FILE.with_suffix(".json.bak")
    backup.write_text(PRODUCTS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
        f.write("\n")
    log.info("Wrote %s (backup at %s)", PRODUCTS_FILE.name, backup.name)


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _age_days(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        then = datetime.datetime.fromisoformat(iso)
        return (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds() / 86400
    except Exception:
        return 1e9


# ---------------------------------------------------------------------------
# Polite, thread-safe per-domain rate limiter
# ---------------------------------------------------------------------------

class DomainThrottle:
    """Enforce a minimum gap between requests to the same host."""

    def __init__(self, min_gap: float = 1.0):
        self.min_gap = min_gap
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            gap = time.time() - self._last.get(host, 0.0)
            sleep_for = self.min_gap - gap
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last[host] = time.time()


# ---------------------------------------------------------------------------
# PA-API SigV4 (SearchItems + GetItems)
# ---------------------------------------------------------------------------

PAAPI_HOST    = "webservices.amazon.com"
PAAPI_REGION  = "us-east-1"
PAAPI_SERVICE = "ProductAdvertisingAPI"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret: str, date_stamp: str) -> bytes:
    k = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k = _sign(k, PAAPI_REGION)
    k = _sign(k, PAAPI_SERVICE)
    return _sign(k, "aws4_request")


def paapi_ready() -> bool:
    return all(_ENV.get(k) for k in ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"))


def _paapi_call(operation: str, payload: dict) -> dict | None:
    """Signed POST to a PA-API operation. Returns parsed JSON or None."""
    access_key = _ENV.get("AMAZON_ACCESS_KEY", "")
    secret_key = _ENV.get("AMAZON_SECRET_KEY", "")
    if not (access_key and secret_key):
        return None

    path   = f"/paapi5/{operation.lower()}"
    target = f"com.amazon.paapi5.v1.ProductAdvertisingAPIv1.{operation}"
    body   = json.dumps(payload, separators=(",", ":"))

    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date   = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    canonical_headers = (
        f"content-encoding:amz-1.0\nhost:{PAAPI_HOST}\n"
        f"x-amz-date:{amz_date}\nx-amz-target:{target}\n"
    )
    signed_headers = "content-encoding;host;x-amz-date;x-amz-target"
    payload_hash   = hashlib.sha256(body.encode()).hexdigest()
    canonical_req  = f"POST\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    cred_scope     = f"{date_stamp}/{PAAPI_REGION}/{PAAPI_SERVICE}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{cred_scope}\n"
        f"{hashlib.sha256(canonical_req.encode()).hexdigest()}"
    )
    signature = hmac.new(_signature_key(secret_key, date_stamp),
                         string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (f"AWS4-HMAC-SHA256 Credential={access_key}/{cred_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")

    try:
        resp = requests.post(
            f"https://{PAAPI_HOST}{path}", data=body, timeout=15,
            headers={"content-encoding": "amz-1.0",
                     "content-type": "application/json; charset=utf-8",
                     "host": PAAPI_HOST, "x-amz-date": amz_date,
                     "x-amz-target": target, "Authorization": auth},
        )
        if resp.status_code == 429:
            log.warning("PA-API throttled (429) on %s; backing off 4s", operation)
            time.sleep(4)
            return None
        if resp.status_code != 200:
            log.debug("PA-API HTTP %s on %s: %s", resp.status_code, operation, resp.text[:200])
            return None
        return resp.json()
    except Exception as exc:
        log.warning("PA-API %s failed: %s", operation, exc)
        return None


def paapi_get_items(asins: list[str]) -> dict[str, dict]:
    """Batch liveness lookup (up to 10 ASINs). Returns {asin: result-dict}.

    Authoritative and not subject to the bot-block that makes /dp scraping
    return a fake 404 for every request. An ASIN present with a buyable Offer
    is 'ok'; present but with no Offer is 'warn' (no buy box / unavailable);
    absent / errored is 'broken' (retired or invalid ASIN).
    """
    asins = asins[:10]
    out: dict[str, dict] = {}
    data = _paapi_call("GetItems", {
        "ItemIds": asins,
        "Resources": ["ItemInfo.Title", "Offers.Listings.Price",
                      "Offers.Listings.Availability.Type"],
        "PartnerTag": _ENV.get("AMAZON_PARTNER_TAG", ""),
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.com",
    })
    if data is None:
        return {a: {"status": "unknown", "detail": "PA-API call failed"} for a in asins}

    for item in data.get("ItemsResult", {}).get("Items", []):
        asin = item.get("ASIN")
        if not asin:
            continue
        listings = item.get("Offers", {}).get("Listings", [])
        if listings:
            out[asin] = {"status": "ok", "detail": "buyable"}
        else:
            out[asin] = {"status": "warn", "detail": "no active offer"}
    for err in data.get("Errors", []):
        # Errors carry the bad value in the message; map any unresolved ASIN.
        for a in asins:
            if a not in out and a in (err.get("Message", "") or ""):
                out[a] = {"status": "broken", "detail": err.get("Code", "not found")}
    for a in asins:
        out.setdefault(a, {"status": "broken", "detail": "not returned by GetItems"})
    return out


def paapi_search(keywords: str, item_count: int = 6) -> list[dict]:
    """Return [{asin,title,price}] candidates for a keyword query, or []."""
    data = _paapi_call("SearchItems", {
        "Keywords": keywords,
        "SearchIndex": "Grocery",
        "ItemCount": item_count,
        "Resources": ["ItemInfo.Title", "ItemInfo.ByLineInfo",
                      "Offers.Listings.Price"],
        "PartnerTag": _ENV.get("AMAZON_PARTNER_TAG", ""),
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.com",
    })
    if not data:
        return []
    out = []
    for item in data.get("SearchResult", {}).get("Items", []):
        title = (item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "") or "")
        price = (item.get("Offers", {}).get("Listings", [{}])[0]
                 .get("Price", {}).get("Amount"))
        if item.get("ASIN") and title:
            out.append({"asin": item["ASIN"], "title": title, "price": price})
    return out


# ---------------------------------------------------------------------------
# Amazon search-page scrape fallback (best effort; CAPTCHA-prone)
# ---------------------------------------------------------------------------

_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def amazon_search_scrape(session: requests.Session, keywords: str,
                         throttle: DomainThrottle) -> list[dict]:
    url = f"https://www.amazon.com/s?k={quote_plus(keywords)}&i=grocery"
    throttle.wait(url)
    try:
        resp = session.get(url, headers={**_BASE_HEADERS, **_AMAZON_EXTRA},
                           timeout=20, allow_redirects=True)
    except Exception as exc:
        log.warning("Amazon search failed for '%s': %s", keywords, exc)
        return []
    if resp.status_code != 200 or "captcha" in resp.url.lower() \
            or "Type the characters" in resp.text[:3000]:
        log.warning("Amazon search blocked/CAPTCHA for '%s'", keywords)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    out: list[dict] = []
    for div in soup.select("div[data-asin]"):
        asin = div.get("data-asin", "").strip()
        if not _ASIN_RE.match(asin):
            continue
        h2 = div.select_one("h2 a span") or div.select_one("h2 span")
        title = h2.get_text(strip=True) if h2 else ""
        if title:
            out.append({"asin": asin, "title": title, "price": None})
        if len(out) >= 6:
            break
    return out


# ---------------------------------------------------------------------------
# Candidate <-> product matching
# ---------------------------------------------------------------------------

def _tokens(text: str, stop: set[str]) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in stop and len(w) > 1}


def _weight_oz_from_title(title: str) -> float | None:
    t = title.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:oz|ounce|ounces)\b", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lb|lbs|pound|pounds)\b", t)
    if m:
        return float(m.group(1)) * 16.0
    return None


def match_confidence(product: dict, title: str) -> float:
    """0..1 confidence that `title` is the same product. Conservative."""
    brand_tok = _tokens(product.get("brand", ""), _BRAND_STOPWORDS)
    name_tok  = _tokens(product.get("name", ""), _NAME_STOPWORDS)
    title_tok = _tokens(title, _NAME_STOPWORDS)
    if not title_tok:
        return 0.0

    # Brand presence is close to mandatory: a coffee from the wrong roaster is
    # the wrong product even if flavours line up.
    brand_hit = bool(brand_tok & title_tok) if brand_tok else True
    brand_score = 1.0 if brand_hit else 0.0

    # Name token overlap (recall against the product's distinctive words).
    name_recall = (len(name_tok & title_tok) / len(name_tok)) if name_tok else 0.0

    # Weight agreement is a strong confirmer when present, never a penalty when
    # the title omits it.
    weight_bonus = 0.0
    pw = product.get("weight_oz")
    tw = _weight_oz_from_title(title)
    if pw and tw:
        weight_bonus = 0.15 if abs(pw - tw) <= max(1.0, 0.1 * pw) else -0.20

    # Accessory/merch guard: a token like "mug" or "k-cup" present in the title
    # but absent from the product name means it is the wrong listing (or wrong
    # format) for the same brand. Penalise hard so it cannot clear threshold.
    product_words = set(re.findall(r"[a-z0-9]+", f"{product.get('name','')}".lower()))
    accessory_hit = (_ACCESSORY_TOKENS & title_tok) - product_words
    accessory_penalty = 0.5 if accessory_hit else 0.0

    score = 0.45 * brand_score + 0.55 * name_recall + weight_bonus - accessory_penalty
    return max(0.0, min(1.0, score))


def best_candidate(product: dict, candidates: list[dict]) -> tuple[dict | None, float]:
    best, best_c = None, 0.0
    for c in candidates:
        conf = match_confidence(product, c["title"])
        if conf > best_c:
            best, best_c = c, conf
    return best, round(best_c, 3)


# ---------------------------------------------------------------------------
# resolve subcommand
# ---------------------------------------------------------------------------

def cmd_resolve(args) -> int:
    products = load_products()
    targets = [p for p in products if not p.get("amazon_asin")]
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        targets = [p for p in targets if p["id"] in wanted]
    if args.limit:
        targets = targets[: args.limit]

    use_paapi = paapi_ready()
    log.info("resolve: %d product(s) missing an ASIN | PA-API: %s | scrape fallback: %s",
             len(targets), "ready" if use_paapi else "no creds",
             "on" if args.scrape else "off")

    session  = requests.Session()
    throttle = DomainThrottle(min_gap=2.0)
    review   = load_json(ASIN_REVIEW, {})
    accepted = 0
    proposed = 0

    for p in targets:
        query = f"{p.get('brand','')} {p.get('name','')}".strip()
        cands: list[dict] = []
        source = ""
        if use_paapi:
            cands = paapi_search(query)
            source = "paapi"
            time.sleep(1.2)  # stay under PA-API TPS
        if not cands and args.scrape:
            cands = amazon_search_scrape(session, query, throttle)
            source = "scrape"

        cand, conf = best_candidate(p, cands)
        if not cand:
            log.info("  %-50s no candidates", p["id"][:50])
            review[p["id"]] = {"status": "no_match", "query": query,
                               "checked": now_iso(), "source": source}
            continue

        rec = {"status": "proposed", "query": query, "source": source,
               "asin": cand["asin"], "matched_title": cand["title"],
               "price": cand.get("price"), "confidence": conf,
               "alternatives": [{"asin": c["asin"], "title": c["title"],
                                 "confidence": match_confidence(p, c["title"])}
                                for c in cands if c["asin"] != cand["asin"]][:3],
               "checked": now_iso()}
        proposed += 1

        if args.write and conf >= args.min_confidence:
            p["amazon_asin"] = cand["asin"]
            if not p.get("affiliate_tag"):
                p["affiliate_tag"] = "coffeebeanind-20"
            rec["status"] = "written"
            accepted += 1
            log.info("  %-50s WRITE %s  conf=%.2f", p["id"][:50], cand["asin"], conf)
        else:
            tag = "ACCEPT" if conf >= args.min_confidence else "review"
            log.info("  %-50s %-6s %s  conf=%.2f", p["id"][:50], tag, cand["asin"], conf)
        review[p["id"]] = rec

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASIN_REVIEW.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.write and accepted:
        save_products(products)

    log.info("Done. proposed=%d written=%d | review file: %s",
             proposed, accepted, ASIN_REVIEW)
    if proposed and not args.write:
        log.info("Dry run. Review %s, then re-run with --write to apply matches "
                 ">= %.2f confidence.", ASIN_REVIEW.name, args.min_confidence)
    return 0


# ---------------------------------------------------------------------------
# check subcommand
# ---------------------------------------------------------------------------

# status severity: ok < warn < unknown < broken
_SEVERITY = {"ok": 0, "warn": 1, "unknown": 2, "broken": 3}

_AMZ_GONE = ("page not found", "we couldn't find that page", "dogs of amazon",
             "looking for something?")
_AMZ_UNAVAIL = ("currently unavailable", "this item is not available")
_SOLD_OUT = ("sold out", "out of stock", "no longer available",
             "product no longer exists")


def _slug_tokens(url: str) -> set[str]:
    path = urlparse(url).path
    last = [seg for seg in path.split("/") if seg]
    seg = last[-1] if last else ""
    return _tokens(seg.replace("-", " "), _NAME_STOPWORDS)


def check_amazon_scrape(session: requests.Session, asin: str,
                        throttle: DomainThrottle) -> dict:
    """Fallback liveness via /dp scrape. Used only when PA-API has no creds.

    Amazon soft-blocks datacenter/automation traffic with a 404-shaped "dogs
    of amazon" page that is byte-identical for live and dead ASINs, so this
    path can confirm life but must NEVER assert 'broken' on its own; an
    ambiguous block is reported 'unknown' for a human/PA-API re-check.
    """
    url = f"https://www.amazon.com/dp/{asin}"
    throttle.wait(url)
    try:
        resp = session.get(url, headers={**_BASE_HEADERS, **_AMAZON_EXTRA},
                           timeout=20, allow_redirects=True)
    except Exception as exc:
        return {"status": "unknown", "http": None, "detail": f"request error: {exc}"}

    low = resp.text[:6000].lower()
    soft_block = (resp.status_code == 404 and any(s in low for s in _AMZ_GONE)) \
        or "captcha" in resp.url.lower() or "type the characters" in low
    if soft_block:
        return {"status": "unknown", "http": resp.status_code,
                "detail": "bot-blocked (use PA-API to confirm)"}
    if any(s in low for s in _AMZ_UNAVAIL):
        return {"status": "warn", "http": resp.status_code, "detail": "currently unavailable"}
    if resp.status_code == 200 and ("add to cart" in low or "buy now" in low
                                    or "add-to-cart" in low):
        return {"status": "ok", "http": 200, "final_url": resp.url}
    return {"status": "unknown", "http": resp.status_code, "detail": "inconclusive"}


def check_roaster(session: requests.Session, product: dict,
                  throttle: DomainThrottle) -> dict:
    url = product["roaster_url"]
    throttle.wait(url)
    try:
        resp = session.get(url, headers=_BASE_HEADERS, timeout=20, allow_redirects=True)
    except Exception as exc:
        return {"status": "unknown", "http": None, "detail": f"request error: {exc}"}

    final = resp.url
    low = resp.text[:8000].lower()
    if resp.status_code == 404:
        return {"status": "broken", "http": 404, "final_url": final, "detail": "404"}
    if resp.status_code >= 500:
        return {"status": "unknown", "http": resp.status_code, "final_url": final,
                "detail": "server error"}

    # Discontinued product silently redirected to the store homepage / a
    # collection listing. The link "works" but no longer points to the product.
    orig_path  = urlparse(url).path.rstrip("/")
    final_path = urlparse(final).path.rstrip("/")
    if "/products/" in orig_path and final_path != orig_path:
        if final_path in ("", "/") or "/products/" not in final_path:
            return {"status": "broken", "http": resp.status_code, "final_url": final,
                    "detail": "redirected off product page (discontinued)"}

    if any(s in low for s in _SOLD_OUT):
        return {"status": "warn", "http": resp.status_code, "final_url": final,
                "detail": "sold out / unavailable"}
    if resp.status_code != 200:
        return {"status": "warn", "http": resp.status_code, "final_url": final,
                "detail": "non-200"}

    # Working link, but the URL slug shares no token with the product name:
    # almost always a wrong/placeholder URL copied across products.
    slug = _slug_tokens(url)
    name = _tokens(product.get("name", ""), _NAME_STOPWORDS)
    if slug and name and not (slug & name):
        return {"status": "warn", "http": 200, "final_url": final,
                "detail": "URL slug does not match product (placeholder?)"}
    return {"status": "ok", "http": resp.status_code, "final_url": final}


def cmd_check(args) -> int:
    products = load_products()
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        products = [p for p in products if p["id"] in wanted]
    if args.limit:
        products = products[: args.limit]

    state    = load_json(STATE_FILE, {})
    session  = requests.Session()
    throttle = DomainThrottle(min_gap=1.0)

    # Build the work list, honouring the freshness cache.
    amazon_jobs:  list[tuple[dict, str]] = []
    roaster_jobs: list[dict] = []
    for p in products:
        st = state.setdefault(p["id"], {})
        asin = p.get("amazon_asin")
        if asin:
            cached = st.get("amazon")
            if (args.all or not cached or cached.get("asin") != asin
                    or _age_days(cached.get("checked")) >= args.max_age):
                amazon_jobs.append((p, asin))
        if p.get("roaster_url"):
            cached = st.get("roaster")
            if (args.all or not cached or cached.get("url") != p["roaster_url"]
                    or _age_days(cached.get("checked")) >= args.max_age):
                roaster_jobs.append(p)

    via = "PA-API GetItems" if paapi_ready() else "dp scrape (no creds; ok/unknown only)"
    log.info("check: %d Amazon (%s) + %d roaster link(s) to verify "
             "(max-age=%dd, %d cached/fresh skipped)",
             len(amazon_jobs), via, len(roaster_jobs),
             args.max_age,
             (len(products) * 2) - len(amazon_jobs) - len(roaster_jobs))

    # Roaster URLs: concurrent across domains.
    if roaster_jobs:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(check_roaster, session, p, throttle): p
                       for p in roaster_jobs}
            for fut in as_completed(futures):
                p = futures[fut]
                res = fut.result()
                res.update({"url": p["roaster_url"], "checked": now_iso()})
                state[p["id"]]["roaster"] = res
                _log_result(p["id"], "roaster", res)

    # Amazon: authoritative via PA-API, batched 10/call. Scrape only if no creds.
    if amazon_jobs:
        if paapi_ready():
            for i in range(0, len(amazon_jobs), 10):
                batch = amazon_jobs[i:i + 10]
                results = paapi_get_items([asin for _, asin in batch])
                for p, asin in batch:
                    res = {**results.get(asin, {"status": "unknown", "detail": "no result"}),
                           "asin": asin, "checked": now_iso()}
                    state[p["id"]]["amazon"] = res
                    _log_result(p["id"], "amazon", res)
                time.sleep(1.2)
        else:
            for p, asin in amazon_jobs:
                res = check_amazon_scrape(session, asin, throttle)
                res.update({"asin": asin, "checked": now_iso()})
                state[p["id"]]["amazon"] = res
                _log_result(p["id"], "amazon", res)
                time.sleep(args.amazon_gap)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    report = _build_report(products, state)
    HEALTH_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(report)

    broken = report["totals"]["broken"]
    if broken and not args.no_fail:
        return 1
    return 0


def _log_result(pid: str, kind: str, res: dict) -> None:
    sev = res["status"]
    line = f"  [{sev.upper():7}] {kind:7} {pid[:46]:46} {res.get('detail','')}"
    (log.error if sev == "broken" else
     log.warning if sev in ("warn", "unknown") else log.info)(line)


def _build_report(products: list[dict], state: dict) -> dict:
    rows = []
    totals = {"ok": 0, "warn": 0, "unknown": 0, "broken": 0}
    for p in products:
        st = state.get(p["id"], {})
        for kind in ("amazon", "roaster"):
            r = st.get(kind)
            if not r:
                continue
            totals[r["status"]] += 1
            if r["status"] != "ok":
                rows.append({"id": p["id"], "kind": kind, "status": r["status"],
                             "http": r.get("http"), "detail": r.get("detail"),
                             "url": r.get("url") or (r.get("asin") and
                                    f"https://www.amazon.com/dp/{r['asin']}")})
    rows.sort(key=lambda x: -_SEVERITY[x["status"]])
    return {"generated": now_iso(), "totals": totals, "issues": rows}


def _print_summary(report: dict) -> None:
    t = report["totals"]
    log.info("---- link health: ok=%d warn=%d unknown=%d broken=%d ----",
             t["ok"], t["warn"], t["unknown"], t["broken"])
    for r in report["issues"]:
        if r["status"] in ("broken", "warn"):
            log.info("  %-7s %-7s %-44s %s", r["status"], r["kind"],
                     r["id"][:44], r["detail"])
    log.info("Full report: %s", HEALTH_REPORT)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    global _ENV
    _ENV = load_env()

    parser = argparse.ArgumentParser(description="Amazon ASIN resolver + link health auditor")
    sub = parser.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("resolve", help="find missing Amazon ASINs")
    pr.add_argument("--limit", type=int, default=0, help="cap how many products to process")
    pr.add_argument("--ids", default="", help="comma-separated product ids only")
    pr.add_argument("--write", action="store_true",
                    help="apply matches >= --min-confidence to products.json (makes a .bak)")
    pr.add_argument("--min-confidence", type=float, default=0.85,
                    help="threshold to auto-write a match (default 0.85, strict: "
                         "near-certain matches only; everything else -> review file)")
    pr.add_argument("--scrape", action="store_true",
                    help="allow amazon.com/s scrape fallback when PA-API yields nothing")
    pr.set_defaults(func=cmd_resolve)

    pc = sub.add_parser("check", help="health-check Amazon + roaster links")
    pc.add_argument("--max-age", type=int, default=7,
                    help="re-check links older than N days (default 7)")
    pc.add_argument("--all", action="store_true", help="ignore cache; check everything")
    pc.add_argument("--limit", type=int, default=0, help="cap products to check")
    pc.add_argument("--ids", default="", help="comma-separated product ids only")
    pc.add_argument("--workers", type=int, default=8, help="concurrent roaster checks")
    pc.add_argument("--amazon-gap", type=float, default=2.0,
                    help="seconds between Amazon dp checks (default 2.0)")
    pc.add_argument("--no-fail", action="store_true",
                    help="exit 0 even when broken links are found")
    pc.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
