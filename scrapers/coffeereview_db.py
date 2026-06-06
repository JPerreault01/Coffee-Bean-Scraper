"""
CoffeeReview.com database — scrapers/coffeereview_db.py
=========================================================
Normalized SQLite corpus of professional coffee reviews from coffeereview.com.
Each row contains a 0-100 overall rating plus five component scores (aroma,
acidity, body, flavor, aftertaste) plus the full blind-assessment text — making
this a high-quality RAG signal for generate_review.py.

Separate from coffee_reference.db (waytocoffee corpus). Lives at data/coffeereview.db.

Build:
    python scrapers/coffeereview_scraper.py              # test: 3 pages
    python scrapers/coffeereview_db.py load data/coffeereview.json

Query:
    python scrapers/coffeereview_db.py stats
    python scrapers/coffeereview_db.py top --n 10
    python scrapers/coffeereview_db.py find "ethiopia"
    python scrapers/coffeereview_db.py specs colombia-penas-blancas-natural-process
    python scrapers/coffeereview_db.py map scrapers/products.json
"""

import argparse
import json
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

DEFAULT_DB = "data/coffeereview.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roasters (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    location TEXT,
    url      TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    id                INTEGER PRIMARY KEY,
    slug              TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    roaster_id        INTEGER REFERENCES roasters(id),
    rating            INTEGER,
    aroma             REAL,
    acidity           REAL,
    body              REAL,
    flavor            REAL,
    aftertaste        REAL,
    roast_level       TEXT,
    blind_assessment  TEXT,
    bottom_line       TEXT,
    review_date       TEXT,
    price_usd         REAL,
    weight_oz         REAL,
    price_per_oz      REAL,
    roaster_url       TEXT,
    url               TEXT,
    scraped_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_name   ON reviews(name);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);

CREATE TABLE IF NOT EXISTS origins    (id INTEGER PRIMARY KEY, name   TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS processing (id INTEGER PRIMARY KEY, method TEXT NOT NULL UNIQUE);

CREATE TABLE IF NOT EXISTS review_origins (
    review_id INTEGER REFERENCES reviews(id) ON DELETE CASCADE,
    origin_id INTEGER REFERENCES origins(id),
    PRIMARY KEY (review_id, origin_id)
);
CREATE TABLE IF NOT EXISTS review_processing (
    review_id  INTEGER REFERENCES reviews(id) ON DELETE CASCADE,
    process_id INTEGER REFERENCES processing(id),
    PRIMARY KEY (review_id, process_id)
);
"""


def slug_from_url(url: str) -> str:
    m = re.search(r"/review/([^/?#]+)/?", url)
    if m:
        return m.group(1).lower()
    return re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" \t\n.,;:-").lower()


def get_conn(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _get_or_create(conn: sqlite3.Connection,
                   table: str, col: str, value: str) -> Optional[int]:
    value = norm(value)
    if not value:
        return None
    conn.execute("INSERT OR IGNORE INTO %s (%s) VALUES (?)" % (table, col), (value,))
    row = conn.execute(
        "SELECT id FROM %s WHERE %s = ?" % (table, col), (value,)
    ).fetchone()
    return row["id"] if row else None


# ── load ──────────────────────────────────────────────────────────────────────

def load_from_json(json_path: str, db_path: str = DEFAULT_DB) -> dict:
    """Upsert all records from coffeereview.json into the DB. Re-running is safe."""
    records = json.loads(Path(json_path).read_text(encoding="utf-8"))
    conn    = get_conn(db_path)
    init_db(conn)
    inserted = updated = skipped = 0

    for r in records:
        url  = r.get("url", "")
        slug = slug_from_url(url) if url else norm(r.get("name", "")).replace(" ", "-")
        if not slug or not r.get("name"):
            skipped += 1
            continue

        # Roaster — upsert with location + url
        roaster_id = None
        if r.get("roaster"):
            rname = norm(r["roaster"])
            conn.execute(
                "INSERT OR IGNORE INTO roasters (name, location, url) VALUES (?, ?, ?)",
                (rname, r.get("roaster_location") or None, r.get("roaster_url") or None),
            )
            conn.execute(
                "UPDATE roasters SET"
                " location = COALESCE(?, location),"
                " url      = COALESCE(?, url)"
                " WHERE name = ?",
                (r.get("roaster_location") or None, r.get("roaster_url") or None, rname),
            )
            row = conn.execute(
                "SELECT id FROM roasters WHERE name = ?", (rname,)
            ).fetchone()
            roaster_id = row["id"] if row else None

        existing = conn.execute(
            "SELECT id FROM reviews WHERE slug = ?", (slug,)
        ).fetchone()

        vals = (
            r["name"], roaster_id,
            r.get("rating") or None,
            r.get("aroma")      or None, r.get("acidity")    or None,
            r.get("body")       or None, r.get("flavor")     or None,
            r.get("aftertaste") or None,
            norm(r.get("roast_level", "")) or None,
            r.get("blind_assessment") or None,
            r.get("bottom_line")      or None,
            r.get("review_date")      or None,
            r.get("price_usd")    or None, r.get("weight_oz")   or None,
            r.get("price_per_oz") or None,
            r.get("roaster_url")  or None,
            url,
        )

        if existing:
            rid = existing["id"]
            conn.execute(
                """UPDATE reviews SET
                   name=?, roaster_id=?, rating=?,
                   aroma=?, acidity=?, body=?, flavor=?, aftertaste=?,
                   roast_level=?, blind_assessment=?, bottom_line=?,
                   review_date=?, price_usd=?, weight_oz=?, price_per_oz=?,
                   roaster_url=?, url=?, scraped_at=datetime('now')
                   WHERE id=?""",
                vals + (rid,),
            )
            conn.execute("DELETE FROM review_origins    WHERE review_id=?", (rid,))
            conn.execute("DELETE FROM review_processing WHERE review_id=?", (rid,))
            updated += 1
        else:
            cur = conn.execute(
                """INSERT INTO reviews
                   (slug, name, roaster_id, rating,
                    aroma, acidity, body, flavor, aftertaste,
                    roast_level, blind_assessment, bottom_line,
                    review_date, price_usd, weight_oz, price_per_oz,
                    roaster_url, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug,) + vals,
            )
            rid = cur.lastrowid
            inserted += 1

        for val in r.get("origins", []):
            oid = _get_or_create(conn, "origins", "name", val)
            if oid:
                conn.execute(
                    "INSERT OR IGNORE INTO review_origins VALUES (?, ?)", (rid, oid)
                )
        for val in r.get("processing", []):
            pid = _get_or_create(conn, "processing", "method", val)
            if pid:
                conn.execute(
                    "INSERT OR IGNORE INTO review_processing VALUES (?, ?)", (rid, pid)
                )

    conn.commit()
    result = {
        "inserted": inserted, "updated": updated, "skipped": skipped,
        "total_reviews": conn.execute(
            "SELECT COUNT(*) c FROM reviews"
        ).fetchone()["c"],
    }
    conn.close()
    return result


# ── specs ─────────────────────────────────────────────────────────────────────

def get_specs(conn: sqlite3.Connection, slug: str) -> Optional[dict]:
    r = conn.execute(
        """SELECT rv.*, ro.name AS roaster_name,
                  ro.location AS roaster_location_field,
                  ro.url      AS roaster_url_field
           FROM reviews rv
           LEFT JOIN roasters ro ON ro.id = rv.roaster_id
           WHERE rv.slug = ?""",
        (slug,),
    ).fetchone()
    if not r:
        return None

    origins = [
        row["name"] for row in conn.execute(
            "SELECT o.name FROM review_origins j"
            " JOIN origins o ON o.id = j.origin_id"
            " WHERE j.review_id = ?",
            (r["id"],),
        ).fetchall()
    ]
    processing = [
        row["method"] for row in conn.execute(
            "SELECT p.method FROM review_processing j"
            " JOIN processing p ON p.id = j.process_id"
            " WHERE j.review_id = ?",
            (r["id"],),
        ).fetchall()
    ]

    return {
        "slug":              r["slug"],
        "name":              r["name"],
        "roaster":           r["roaster_name"],
        "roaster_location":  r["roaster_location_field"],
        "rating":            r["rating"],
        "aroma":             r["aroma"],
        "acidity":           r["acidity"],
        "body":              r["body"],
        "flavor":            r["flavor"],
        "aftertaste":        r["aftertaste"],
        "roast_level":       r["roast_level"],
        "origins":           origins,
        "processing":        processing,
        "blind_assessment":  r["blind_assessment"],
        "bottom_line":       r["bottom_line"],
        "review_date":       r["review_date"],
        "price_usd":         r["price_usd"],
        "weight_oz":         r["weight_oz"],
        "price_per_oz":      r["price_per_oz"],
        "roaster_url":       r["roaster_url"] or r["roaster_url_field"],
        "url":               r["url"],
    }


# ── find ──────────────────────────────────────────────────────────────────────

def find_review(conn: sqlite3.Connection,
                name: str,
                roaster: Optional[str] = None,
                limit: int = 5) -> list:
    target = norm(name)
    rows   = conn.execute(
        "SELECT rv.slug, rv.name, rv.rating, ro.name AS roaster"
        " FROM reviews rv"
        " LEFT JOIN roasters ro ON ro.id = rv.roaster_id"
    ).fetchall()
    rnorm  = norm(roaster) if roaster else None
    scored = []
    for row in rows:
        score = SequenceMatcher(None, target, norm(row["name"])).ratio()
        if rnorm and row["roaster"] and rnorm in norm(row["roaster"]):
            score += 0.15
        scored.append((
            round(score, 3),
            row["slug"],
            row["name"],
            row["roaster"],
            row["rating"],
        ))
    scored.sort(reverse=True)
    return scored[:limit]


# ── top ───────────────────────────────────────────────────────────────────────

def top_reviews(conn: sqlite3.Connection,
                n: int = 20,
                origin: Optional[str] = None,
                roast: Optional[str] = None) -> list:
    joins  = ""
    wheres: list[str] = []
    params: list      = []

    if origin:
        joins += (
            " JOIN review_origins ro2 ON ro2.review_id = rv.id"
            " JOIN origins o2 ON o2.id = ro2.origin_id"
        )
        wheres.append("LOWER(o2.name) LIKE ?")
        params.append("%" + origin.lower() + "%")
    if roast:
        wheres.append("LOWER(rv.roast_level) LIKE ?")
        params.append("%" + roast.lower() + "%")

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(n)

    sql = (
        "SELECT rv.slug, rv.name, rv.rating, ro.name AS roaster,"
        "       rv.roast_level, rv.review_date"
        " FROM reviews rv"
        " LEFT JOIN roasters ro ON ro.id = rv.roaster_id"
        " %s %s"
        " ORDER BY rv.rating DESC"
        " LIMIT ?"
    ) % (joins, where_sql)

    return conn.execute(sql, params).fetchall()


# ── stats ─────────────────────────────────────────────────────────────────────

def corpus_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) c FROM reviews").fetchone()["c"]
    rating_row = conn.execute(
        "SELECT MIN(rating) mn, ROUND(AVG(rating),1) avg, MAX(rating) mx"
        " FROM reviews WHERE rating > 0"
    ).fetchone()
    top_origins = conn.execute(
        "SELECT o.name, COUNT(*) cnt"
        " FROM review_origins j JOIN origins o ON o.id = j.origin_id"
        " GROUP BY o.name ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    top_roasters = conn.execute(
        "SELECT ro.name, COUNT(*) cnt"
        " FROM reviews rv JOIN roasters ro ON ro.id = rv.roaster_id"
        " GROUP BY ro.name ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    return {
        "total_reviews": total,
        "rating": {
            "min": rating_row["mn"],
            "avg": rating_row["avg"],
            "max": rating_row["mx"],
        } if rating_row and rating_row["mn"] else {},
        "top_origins":  [(r["name"], r["cnt"]) for r in top_origins],
        "top_roasters": [(r["name"], r["cnt"]) for r in top_roasters],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p   = argparse.ArgumentParser(description="CoffeeReview.com DB tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--db", default=DEFAULT_DB,
                        help="DB path (default: %s)" % DEFAULT_DB)

    pl = sub.add_parser("load", parents=[shared],
                        help="Load or reload coffeereview.json into the DB (upsert)")
    pl.add_argument("json_path")

    ps = sub.add_parser("specs", parents=[shared],
                        help="Print all fields for a review slug")
    ps.add_argument("slug")

    pf = sub.add_parser("find", parents=[shared],
                        help="Fuzzy name search (top 5 matches)")
    pf.add_argument("name")
    pf.add_argument("--roaster", default=None,
                    help="Boost results matching this roaster name")

    pt = sub.add_parser("top", parents=[shared],
                        help="List N highest-rated reviews")
    pt.add_argument("--n", type=int, default=20, metavar="N")
    pt.add_argument("--origin", default=None,
                    help="Filter to reviews whose origin contains this string")
    pt.add_argument("--roast", default=None,
                    help="Filter to reviews whose roast level contains this string")

    pm = sub.add_parser("map", parents=[shared],
                        help="Suggest coffeereview_slug for each product in products.json")
    pm.add_argument("products_json")

    sub.add_parser("stats", parents=[shared], help="Corpus statistics")

    args = p.parse_args()

    if args.cmd == "load":
        result = load_from_json(args.json_path, args.db)
        print(result)

    elif args.cmd == "specs":
        conn  = get_conn(args.db)
        specs = get_specs(conn, args.slug)
        print(
            json.dumps(specs, indent=2, ensure_ascii=False) if specs else "Not found."
        )
        conn.close()

    elif args.cmd == "find":
        conn = get_conn(args.db)
        hits = find_review(conn, args.name, args.roaster)
        if not hits:
            print("No results.")
        else:
            print("%-6s  %-52s  %s" % ("Score", "Slug", "Name  (Roaster)  Rating"))
            print("-" * 100)
            for score, slug, name, roaster, rating in hits:
                roaster_s = roaster or ""
                rating_s  = str(rating) if rating else ""
                print("%-6s  %-52s  %s  (%s)  %s" % (
                    score, slug, name, roaster_s, rating_s
                ))
        conn.close()

    elif args.cmd == "top":
        conn = get_conn(args.db)
        rows = top_reviews(conn, args.n, args.origin, args.roast)
        if not rows:
            print("No results.")
        else:
            print("%-6s  %-46s  %-30s  %-12s  %s" % (
                "Rating", "Name", "Roaster", "Roast", "Date"
            ))
            print("-" * 108)
            for row in rows:
                rating_s    = str(row["rating"]) if row["rating"] else ""
                name_s      = (row["name"] or "")[:45]
                roaster_s   = (row["roaster"] or "")[:29]
                roast_s     = (row["roast_level"] or "")[:11]
                date_s      = row["review_date"] or ""
                print("%-6s  %-46s  %-30s  %-12s  %s" % (
                    rating_s, name_s, roaster_s, roast_s, date_s
                ))
        conn.close()

    elif args.cmd == "map":
        products = json.loads(Path(args.products_json).read_text(encoding="utf-8"))
        conn     = get_conn(args.db)
        print("%-40s  %-52s  %-6s  Score" % ("Product", "coffeereview_slug", "Rating"))
        print("-" * 108)
        for prod in products:
            name = prod.get("name", "")
            hits = find_review(conn, name, prod.get("roaster"))
            if hits:
                score, slug, _, _, rating = hits[0]
                rating_s = str(rating) if rating else ""
                print("%-40s  %-52s  %-6s  %.3f" % (
                    name[:39], slug, rating_s, score
                ))
            else:
                print("%-40s  %-52s  %-6s  0.000" % (name[:39], "no match", ""))
        conn.close()

    elif args.cmd == "stats":
        conn = get_conn(args.db)
        s    = corpus_stats(conn)
        print("Total reviews: %d" % s["total_reviews"])
        if s.get("rating") and s["rating"].get("min") is not None:
            r = s["rating"]
            print("Rating: min=%s  avg=%s  max=%s" % (r["min"], r["avg"], r["max"]))
        print("\nTop 10 origins:")
        for name, cnt in s.get("top_origins", []):
            print("  %4d  %s" % (cnt, name))
        print("\nTop 10 roasters:")
        for name, cnt in s.get("top_roasters", []):
            print("  %4d  %s" % (cnt, name))
        conn.close()


if __name__ == "__main__":
    main()
