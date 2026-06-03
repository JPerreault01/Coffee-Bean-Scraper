"""
Coffee reference database — scrapers/reference_db.py
======================================================
Normalized SQLite corpus of ~14k coffees from thewaytocoffee.com.
Seed data for the site's entity graph and review enrichment.

Build:
    python scrapers/waytocoffee_scraper.py --all --format json --output data/waytocoffee.json
    python scrapers/reference_db.py load data/waytocoffee.json

Query:
    python scrapers/reference_db.py specs lavazza-super-crema
    python scrapers/reference_db.py find "super crema" --roaster lavazza
    python scrapers/reference_db.py map scrapers/products.json
"""

import argparse
import json
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

DEFAULT_DB = "data/coffee_reference.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roasters (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url  TEXT
);
CREATE TABLE IF NOT EXISTS coffees (
    id          INTEGER PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    roaster_id  INTEGER REFERENCES roasters(id),
    description TEXT,
    roast_level TEXT,
    url         TEXT,
    scraped_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_coffees_name ON coffees(name);
CREATE TABLE IF NOT EXISTS origins      (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS flavor_notes (id INTEGER PRIMARY KEY, note TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS processing   (id INTEGER PRIMARY KEY, method TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS varietals    (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS coffee_origins (
    coffee_id INTEGER REFERENCES coffees(id) ON DELETE CASCADE,
    origin_id INTEGER REFERENCES origins(id),
    PRIMARY KEY (coffee_id, origin_id)
);
CREATE TABLE IF NOT EXISTS coffee_flavor_notes (
    coffee_id INTEGER REFERENCES coffees(id) ON DELETE CASCADE,
    note_id   INTEGER REFERENCES flavor_notes(id),
    PRIMARY KEY (coffee_id, note_id)
);
CREATE TABLE IF NOT EXISTS coffee_processing (
    coffee_id  INTEGER REFERENCES coffees(id) ON DELETE CASCADE,
    process_id INTEGER REFERENCES processing(id),
    PRIMARY KEY (coffee_id, process_id)
);
CREATE TABLE IF NOT EXISTS coffee_varietals (
    coffee_id   INTEGER REFERENCES coffees(id) ON DELETE CASCADE,
    varietal_id INTEGER REFERENCES varietals(id),
    PRIMARY KEY (coffee_id, varietal_id)
);
"""


def slug_from_url(url: str) -> str:
    m = re.search(r"/beans/([^/?#]+)/?", url)
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


def _get_or_create(conn, table: str, col: str, value: str) -> Optional[int]:
    value = norm(value)
    if not value:
        return None
    conn.execute(f"INSERT OR IGNORE INTO {table} ({col}) VALUES (?)", (value,))
    row = conn.execute(f"SELECT id FROM {table} WHERE {col} = ?", (value,)).fetchone()
    return row["id"] if row else None


def load_from_json(json_path: str, db_path: str = DEFAULT_DB) -> dict:
    records = json.loads(Path(json_path).read_text(encoding="utf-8"))
    conn = get_conn(db_path)
    init_db(conn)
    inserted = updated = skipped = 0
    for r in records:
        url = r.get("url", "")
        slug = slug_from_url(url) if url else norm(r.get("name", "")).replace(" ", "-")
        if not slug or not r.get("name"):
            skipped += 1
            continue
        roaster_id = None
        if r.get("roaster"):
            conn.execute(
                "INSERT OR IGNORE INTO roasters (name, url) VALUES (?, ?)",
                (norm(r["roaster"]), r.get("roaster_url") or None),
            )
            row = conn.execute(
                "SELECT id FROM roasters WHERE name = ?", (norm(r["roaster"]),)
            ).fetchone()
            roaster_id = row["id"] if row else None
        existing = conn.execute("SELECT id FROM coffees WHERE slug = ?", (slug,)).fetchone()
        if existing:
            cid = existing["id"]
            conn.execute(
                """UPDATE coffees SET name=?, roaster_id=?, description=?,
                   roast_level=?, url=?, scraped_at=datetime('now') WHERE id=?""",
                (r["name"], roaster_id, r.get("description") or None,
                 norm(r.get("roast_level", "")) or None, url, cid),
            )
            for jt in ("coffee_origins", "coffee_flavor_notes",
                       "coffee_processing", "coffee_varietals"):
                conn.execute(f"DELETE FROM {jt} WHERE coffee_id = ?", (cid,))
            updated += 1
        else:
            cur = conn.execute(
                """INSERT INTO coffees (slug, name, roaster_id, description, roast_level, url)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (slug, r["name"], roaster_id, r.get("description") or None,
                 norm(r.get("roast_level", "")) or None, url),
            )
            cid = cur.lastrowid
            inserted += 1
        for val in r.get("origins", []):
            oid = _get_or_create(conn, "origins", "name", val)
            if oid:
                conn.execute("INSERT OR IGNORE INTO coffee_origins VALUES (?, ?)", (cid, oid))
        for val in r.get("flavor_notes", []):
            nid = _get_or_create(conn, "flavor_notes", "note", val)
            if nid:
                conn.execute("INSERT OR IGNORE INTO coffee_flavor_notes VALUES (?, ?)", (cid, nid))
        for val in r.get("processing", []):
            pid = _get_or_create(conn, "processing", "method", val)
            if pid:
                conn.execute("INSERT OR IGNORE INTO coffee_processing VALUES (?, ?)", (cid, pid))
        for val in r.get("typology", []):
            vid = _get_or_create(conn, "varietals", "name", val)
            if vid:
                conn.execute("INSERT OR IGNORE INTO coffee_varietals VALUES (?, ?)", (cid, vid))
    conn.commit()
    stats = {
        "inserted": inserted, "updated": updated, "skipped": skipped,
        "total_coffees": conn.execute("SELECT COUNT(*) c FROM coffees").fetchone()["c"],
    }
    conn.close()
    return stats


def _linked(conn, coffee_id: int, jt: str, ref_table: str, ref_col: str) -> list:
    key = {
        "flavor_notes": "note_id", "origins": "origin_id",
        "processing": "process_id", "varietals": "varietal_id",
    }[ref_table]
    rows = conn.execute(
        f"SELECT t.{ref_col} v FROM {jt} j"
        f" JOIN {ref_table} t ON t.id = j.{key}"
        f" WHERE j.coffee_id = ?",
        (coffee_id,),
    ).fetchall()
    return [row["v"] for row in rows]


def get_specs(conn, slug: str) -> Optional[dict]:
    c = conn.execute(
        """SELECT co.*, r.name AS roaster_name, r.url AS roaster_url
           FROM coffees co LEFT JOIN roasters r ON r.id = co.roaster_id
           WHERE co.slug = ?""",
        (slug,),
    ).fetchone()
    if not c:
        return None
    return {
        "slug": c["slug"], "name": c["name"],
        "roaster": c["roaster_name"], "roaster_url": c["roaster_url"],
        "roast_level": c["roast_level"], "description": c["description"],
        "url": c["url"],
        "origins":      _linked(conn, c["id"], "coffee_origins",      "origins",      "name"),
        "flavor_notes": _linked(conn, c["id"], "coffee_flavor_notes", "flavor_notes", "note"),
        "processing":   _linked(conn, c["id"], "coffee_processing",   "processing",   "method"),
        "varietals":    _linked(conn, c["id"], "coffee_varietals",    "varietals",    "name"),
    }


def find_coffee(conn, name: str, roaster: Optional[str] = None, limit: int = 5) -> list:
    target = norm(name)
    rows = conn.execute(
        "SELECT co.slug, co.name, r.name AS roaster"
        " FROM coffees co LEFT JOIN roasters r ON r.id = co.roaster_id"
    ).fetchall()
    scored = []
    rnorm = norm(roaster) if roaster else None
    for row in rows:
        score = SequenceMatcher(None, target, norm(row["name"])).ratio()
        if rnorm and row["roaster"] and rnorm in row["roaster"]:
            score += 0.15
        scored.append((round(score, 3), row["slug"], row["name"], row["roaster"]))
    scored.sort(reverse=True)
    return scored[:limit]


def main() -> None:
    p = argparse.ArgumentParser(description="Coffee reference DB tool")
    sub = p.add_subparsers(dest="cmd", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--db", default=DEFAULT_DB)

    pl = sub.add_parser("load", parents=[shared], help="Load scraper JSON into DB")
    pl.add_argument("json_path")

    ps = sub.add_parser("specs", parents=[shared], help="Print specs for a slug")
    ps.add_argument("slug")

    pf = sub.add_parser("find", parents=[shared], help="Fuzzy-find by name")
    pf.add_argument("name")
    pf.add_argument("--roaster", default=None)

    pm = sub.add_parser("map", parents=[shared],
                        help="Suggest reference_slug for each product in products.json")
    pm.add_argument("products_json")

    args = p.parse_args()

    if args.cmd == "load":
        print(load_from_json(args.json_path, args.db))
    elif args.cmd == "specs":
        conn = get_conn(args.db)
        specs = get_specs(conn, args.slug)
        print(json.dumps(specs, indent=2, ensure_ascii=False) if specs else "Not found.")
        conn.close()
    elif args.cmd == "find":
        conn = get_conn(args.db)
        for score, slug, name, roaster in find_coffee(conn, args.name, args.roaster):
            print(f"{score:>6}  {slug:<40}  {name}  ({roaster})")
        conn.close()
    elif args.cmd == "map":
        products = json.loads(Path(args.products_json).read_text(encoding="utf-8"))
        conn = get_conn(args.db)
        print(f"{'Product':<40} {'Best slug':<45} Score")
        print("-" * 90)
        for prod in products:
            name = prod.get("name", "")
            hits = find_coffee(conn, name, prod.get("roaster"))
            if hits:
                score, slug, _, _ = hits[0]
                print(f"{name[:39]:<40} {slug:<45} {score:.3f}")
            else:
                print(f"{name[:39]:<40} {'no match':<45} 0.000")
        conn.close()


if __name__ == "__main__":
    main()
