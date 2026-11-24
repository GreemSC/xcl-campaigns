"""SQLite store: everything read from GitHub, every version of it, and what is extracted from it."""
import hashlib
import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);

-- One GitHub item: issue, PR, issue/PR comment, review comment.
CREATE TABLE IF NOT EXISTS items (
    key TEXT PRIMARY KEY,          -- 'issue:1269', 'pr:1315', 'comment:7134448718', 'revcomment:…'
    kind TEXT NOT NULL,            -- issue | pr | comment | revcomment
    number INTEGER,                -- issue/PR the item belongs to
    author TEXT,
    created TEXT, updated TEXT, closed TEXT, merged TEXT,
    status TEXT,                   -- open | closed | merged
    title TEXT,
    body TEXT,
    url TEXT,
    hash TEXT,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS items_number ON items(number);
CREATE INDEX IF NOT EXISTS items_kind ON items(kind);

-- Every version of a body (people edit their tracking comments in place).
CREATE TABLE IF NOT EXISTS versions (key TEXT, hash TEXT, seen TEXT, updated TEXT, body TEXT, PRIMARY KEY (key, hash));

-- Files touched by a PR (for overlap detection).
CREATE TABLE IF NOT EXISTS pr_files (number INTEGER, sha TEXT, path TEXT, additions INTEGER, deletions INTEGER,
                                     PRIMARY KEY (number, path));

-- Pass 1 (no AI): facts found by plain rules.
CREATE TABLE IF NOT EXISTS facts (key TEXT, hash TEXT, sort TEXT, value TEXT, PRIMARY KEY (key, sort, value));

-- Pass 2: typed card per campaign message, from the author's own block or from the AI, checked by code.
CREATE TABLE IF NOT EXISTS cards (key TEXT PRIMARY KEY, hash TEXT, card TEXT, model TEXT, date TEXT,
                                  source TEXT);   -- 'auto' (AI-extracted) | 'author' (xcl-claim / xcl-result block)
"""


def connect(path=None):
    path = path or os.environ.get("XC_DB", "data/xcl.sqlite")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def get_state(con, key, default=None):
    r = con.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_state(con, key, value):
    con.execute("INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def digest(*texts):
    h = hashlib.sha256()
    for t in texts:
        h.update((t or "").encode())
        h.update(b"\0")
    return h.hexdigest()[:16]


FIELDS = ("number", "author", "created", "updated", "closed", "merged", "status", "title", "body", "url")


def store(con, it, now):
    """Insert or update an item; keep the old version if the body changed. True if new or changed."""
    h = digest(it.get("title"), it.get("body"))
    old = con.execute("SELECT hash FROM items WHERE key=?", (it["key"],)).fetchone()
    con.execute(
        """INSERT INTO items (key,kind,number,author,created,updated,closed,merged,status,title,body,url,hash,raw)
           VALUES (:key,:kind,:number,:author,:created,:updated,:closed,:merged,:status,:title,:body,:url,:hash,:raw)
           ON CONFLICT(key) DO UPDATE SET updated=excluded.updated, closed=excluded.closed,
             merged=COALESCE(excluded.merged, items.merged), status=excluded.status,
             title=excluded.title, body=excluded.body, hash=excluded.hash, raw=excluded.raw""",
        {**{k: None for k in FIELDS}, **it, "hash": h, "raw": json.dumps(it.get("raw"), ensure_ascii=False)})
    con.execute("INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?)", (it["key"], h, now, it.get("updated"), it.get("body")))
    return old is None or old["hash"] != h
