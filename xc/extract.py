"""Pass 1, no AI: what plain rules find reliably in a text.

Commits, issue/PR numbers, GPUs, OS, drivers, RAM, XCL_* variables, declared AI tool/model, and the
`xcl-claim` / `xcl-result` / `xcl-fix` blocks posted by authors."""
import json
import re

from . import db

RX = {
    "commit": re.compile(r"(?:`|\bmain\s+|\bcommit\s+|@)([0-9a-f]{7,40})\b"),
    "ref": re.compile(r"(?:(?<![\w/])#|github\.com/ivall/xcl/(?:issues|pull)/)(\d{2,5})\b"),
    "gpu": re.compile(r"\b(RTX\s?\d{4}(?:\s?(?:Ti|SUPER|Super))?|GTX\s?\d{3,4}(?:\s?Ti)?|RX\s?\d{4}(?:\s?(?:XTX|XT|GRE))?"
                      r"|Arc\s?[AB]\d{3}|Radeon\s+\d{3,4}M|Steam\s?Deck)\b", re.I),
    "os": re.compile(r"\b(Windows\s?1[01]|Linux|Steam\s?Deck|CachyOS|Arch|Ubuntu|Fedora|Proton|Wine)\b", re.I),
    "driver": re.compile(r"\b(RADV|Mesa\s?\d+\.\d+(?:\.\d+)?|NVIDIA\s(?:driver\s)?\d{3}\.\d+(?:\.\d+)?"
                         r"|driver\s(?:32\.0\.\d+\.\d+|\d{3}\.\d+(?:\.\d+)?))", re.I),
    "ram_gb": re.compile(r"\b(\d{1,3})\s?GB(?:\sof)?\s(?:DDR\d\s)?RAM\b", re.I),
    "env": re.compile(r"\b(XCL_[A-Z0-9_]+)(?:=([\w.,:-]+))?"),
    "ai_model": re.compile(r"\b(Claude\s(?:Opus|Sonnet|Haiku|Fable)\s[\d.]+|Fable\s[\d.]+|Opus\s[\d.]+|GPT-\d(?:\.\d)?(?:[- ]\w+)?"
                           r"|Gemini\s[\d.]+(?:\s\w+)?|Codex|Copilot|Cursor|Devin)\b"),
}
BLOCK = re.compile(r"```(xcl-result|xcl-claim|xcl-fix)\s*\n(.*?)```", re.S)


def facts_of(text):
    text = text or ""
    out = set()
    for sort, rx in RX.items():
        for m in rx.finditer(text):
            v = m.group(1)
            if sort == "commit" and not (re.search(r"\d", v) and re.search(r"[a-f]", v)):
                continue
            if sort == "env" and m.group(2):
                v = f"{v}={m.group(2)}"
            if sort in ("gpu", "os"):
                v = re.sub(r"\s+", " ", v).strip()
            out.add((sort, v))
    if re.search(r"\*\*AI use\*\*|AI use[:\s]|AI-assisted", text, re.I):
        out.add(("ai_declared", "yes"))
    return out


def blocks_of(text):
    """Structured blocks posted by the author. Only valid JSON objects are kept."""
    res = []
    for kind, body in BLOCK.findall(text or ""):
        try:
            v = json.loads(body)
            res.append((kind, v if isinstance(v, dict) else {"_invalid": True}))
        except ValueError:
            res.append((kind, {"_invalid": True}))
    return res


def run(con=None):
    con = con or db.connect()
    rows = con.execute("""SELECT i.key, i.hash, i.title, i.body FROM items i
                          WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.key=i.key AND f.hash=i.hash)""").fetchall()
    for r in rows:
        con.execute("DELETE FROM facts WHERE key=?", (r["key"],))
        text = f"{r['title'] or ''}\n{r['body'] or ''}"
        facts = facts_of(text) | {("block", json.dumps([k, b], ensure_ascii=False, sort_keys=True)) for k, b in blocks_of(text)}
        facts.add(("_seen", "1"))
        con.executemany("INSERT OR IGNORE INTO facts VALUES (?,?,?,?)", [(r["key"], r["hash"], s, v) for s, v in facts])
    con.commit()
    return {"items": len(rows)}
