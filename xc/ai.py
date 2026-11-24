"""The only place an AI is called. Claude Code in print mode, fully boxed in:

- no tools (`--tools ""`), no MCP servers (`--strict-mcp-config`), no settings or hooks (`--setting-sources ""`),
- run in an empty directory, so no CLAUDE.md or project file is read,
- the GitHub text goes in as quoted DATA, and the answer must match a JSON schema (`--json-schema`).

So a comment that says "ignore your instructions" can at worst get its own row filed wrong; it cannot make
the model read, run or send anything."""
import json
import os
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
    if out.get("is_error") or not out.get("structured_output"):
        raise RuntimeError(str(out.get("result"))[:200])
    return out["structured_output"], ",".join((out.get("modelUsage") or {}).keys())
