"""Draft a short campaign update for GitHub, with only what changed since the last update that was posted.

    python -m xc digest 1269              # prints the draft (Markdown); nothing is posted
    python -m xc digest 1269 --posted     # records the current state as "posted" after a human posted it

It reads the public board (no database needed), so it runs on any machine. A human always reviews and posts:
this never writes to GitHub. If nothing is new, it says so and prints no draft."""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("XC_BASE_URL", "https://greemsc.github.io/xcl-campaigns")
STATE_DIR = os.environ.get("XC_DIGEST_STATE", os.path.expanduser("~/.cache/xcl-campaigns"))


def get(path):
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=30) as r:
        return json.load(r)


def snapshot(n):
    d = get(f"campaign-{n}.json")
    dup = get("api/duplicates.json")
    results = {}
    for t in d["tasks"]:
        if t["type"] == "measure":
            try:
                results[t["id"]] = len(get(f"api/campaigns/{n}/results/{t['id']}.json"))
            except Exception:
                results[t["id"]] = 0
    return {
        "tasks": {t["id"]: t["title"] for t in d["tasks"]},
        "conflicts": sorted(t["id"] for t in d["tasks"] if t["conflict"]),
        "teams": {t["id"]: t["teams"] for t in d["tasks"]},
        "results": results,
        # only the hand-written measurement tasks: auto-added ones are often not hardware-dependent
        "need": sorted((g["task"], g["class"]) for g in d["grid"] if g["need"] > 0 and not g["task"].startswith("A")),
        "campaign_prs": sorted({p["number"] for t in d["tasks"] for p in t["prs"]}),
        "commits": len(d["commits_used"]),
        "messages": len(d["messages"]),
        "dups": sorted("-".join(map(str, sorted(int(k) for k, v in (g["check"] or {}).get("verdicts", {}).items()
                                                if v == "same-change")))
                       for g in dup["pr_groups"] if (g.get("check") or {}).get("ai_check") == "duplicates"),
    }


def draft(n, old, new):
    lines, page = [], f"{BASE}/campaign-{n}.html"
    added = [t for t in new["tasks"] if t not in old.get("tasks", {})]
    if added:
        lines.append("**New tasks** (work announced in the thread): " +
                     "; ".join(f"{t} {new['tasks'][t]}" for t in added) + ".")
    conf = [t for t in new["conflicts"] if t not in old.get("conflicts", []) or new["teams"][t] != old.get("teams", {}).get(t)]
    if conf:
        lines.append("**Separate teams on the same code task** (worth a word between them): " + "; ".join(
            f"{t}: " + " / ".join("+".join(team) for team in new["teams"][t]) for t in conf) + ".")
    more = {t: k - old.get("results", {}).get(t, 0) for t, k in new["results"].items() if k > old.get("results", {}).get(t, 0)}
    if more:
        lines.append(f"**{sum(more.values())} new reported values** (" + ", ".join(f"{t} +{k}" for t, k in more.items()) +
                     f"), each with its hardware class and commit: {page}#reported-numbers")
    if new["need"]:
        cells = ", ".join(f"{t} on {c}" for t, c in new["need"][:8])
        lines.append(f"**Still wanted** (no or one machine so far): {cells}"
                     + (f", and {len(new['need']) - 8} more" if len(new["need"]) > 8 else "") + ".")
    camp_prs = set(new["campaign_prs"])
    dups = [g for g in new["dups"] if g not in old.get("dups", [])
            and camp_prs & {int(x) for x in g.split("-")}]           # only duplicates that concern this campaign
    if dups:
        lines.append("**Open PRs that make the same change** (AI-checked, reading the diffs): " +
                     "; ".join(", ".join(f"#{x}" for x in g.split("-")) for g in dups[:5]) + ".")
    if old.get("commits") is not None and new["commits"] != old["commits"]:
        lines.append(f"Numbers now come from {new['commits']} different `main` commits; compare within one commit.")
    if not (added or conf or more or dups):
        return None
    head = f"**Campaign board update for #{n}** ({new['messages']} messages filed): {page}"
    tail = ("To take a task or report numbers, an `xcl-claim` / `xcl-result` block followed by "
            f"`Tracked on the campaign board: {page}` is enough ({BASE}/AGENTS-campaign.md).\n\n"
            "AI use: Claude Code (Claude Opus 5.5) generated this update from the board; I checked it before posting.")
    return head + "\n\n" + "\n".join(f"- {l}" for l in lines) + "\n\n" + tail


def main(argv):
    n = int(argv[0])
    os.makedirs(STATE_DIR, exist_ok=True)
    path = f"{STATE_DIR}/digest-{n}.json"
    old = json.load(open(path)) if os.path.exists(path) else {}
    new = snapshot(n)
    if "--posted" in argv:
        json.dump(new, open(path, "w"))
        print(f"recorded as posted: {path}")
        return
    if "--init" in argv:        # first run: take today's state as already announced
        json.dump(new, open(path, "w"))
        print(f"initial state recorded: {path}")
        return
    d = draft(n, old, new)
    print(d if d else "Nothing new worth a comment since the last update.")
