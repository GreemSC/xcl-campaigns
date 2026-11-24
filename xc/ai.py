"""The only place an AI is called. Claude Code in print mode, fully boxed in:

- no tools (`--tools ""`), no MCP servers (`--strict-mcp-config`), no settings or hooks (`--setting-sources ""`),
- run in an empty directory, so no CLAUDE.md or project file is read,
- the GitHub text goes in as quoted DATA, and the answer must match a JSON schema (`--json-schema`).

So a comment that says "ignore your instructions" can at worst get its own row filed wrong; it cannot make
the model read, run or send anything."""
import datetime as dt
import json
import os
import sqlite3
import subprocess

AI_DIR = os.environ.get("XC_AI_DIR", "/tmp/xc-classify")


def ask(system, data, schema, model="haiku", timeout=300):
    os.makedirs(AI_DIR, exist_ok=True)
    p = subprocess.run(
        ["claude", "-p", "--setting-sources", "", "--strict-mcp-config", "--tools", "", "--model", model,
         "--no-session-persistence", "--output-format", "json", "--json-schema", json.dumps(schema),
         "--system-prompt", system],
        input="Data (JSON):\n" + json.dumps(data, ensure_ascii=False), capture_output=True, text=True,
        timeout=timeout, cwd=AI_DIR)
    out = json.loads(p.stdout)
    _log_usage(out)
    if out.get("is_error") or not out.get("structured_output"):
        raise RuntimeError(str(out.get("result"))[:200])
    return out["structured_output"], ",".join((out.get("modelUsage") or {}).keys())


def _log_usage(out):
    """Token use of every call, per model, for the health page (separate connection: called from worker threads)."""
    try:
        con = sqlite3.connect(os.environ.get("XC_DB", "data/xcl.sqlite"), timeout=30)
        con.execute("""CREATE TABLE IF NOT EXISTS ai_usage (date TEXT, model TEXT, input INTEGER, cache_read INTEGER,
                       cache_write INTEGER, output INTEGER, cost_usd REAL)""")
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        for model, u in (out.get("modelUsage") or {}).items():
            con.execute("INSERT INTO ai_usage VALUES (?,?,?,?,?,?,?)",
                        (now, model, u.get("inputTokens", 0), u.get("cacheReadInputTokens", 0),
                         u.get("cacheCreationInputTokens", 0), u.get("outputTokens", 0), u.get("costUSD", 0.0)))
        con.commit()
        con.close()
    except Exception:
        pass


def usage(con, hours):
    con.execute("""CREATE TABLE IF NOT EXISTS ai_usage (date TEXT, model TEXT, input INTEGER, cache_read INTEGER,
                   cache_write INTEGER, output INTEGER, cost_usd REAL)""")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
    return {r[0]: {"calls": r[1], "input_tokens": r[2], "cache_read_tokens": r[3], "cache_write_tokens": r[4],
                   "output_tokens": r[5], "api_price_equivalent_usd": round(r[6], 3)}
            for r in con.execute("""SELECT model, count(*), sum(input), sum(cache_read), sum(cache_write), sum(output),
                                    sum(cost_usd) FROM ai_usage WHERE date > ? GROUP BY model""", (since,))}
