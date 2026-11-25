"""roadmap.html and api/roadmap.json: the maintainer's roadmap issue, followed issue by issue, with what each blocker
waits for now; the next stages of the ladder; GitHub tags, releases and milestones. Code only, no AI.

The roadmap is read from GitHub itself, every pass: the newest open issue titled "Roadmap: …" opened by a maintainer.
Its first bold sentence after "goal" is the goal; each "- Name: #a, #b" line under a "Where it stops" header is a
blocker group, in the maintainer's order (first = biggest). When the maintainer edits it, the page follows; a format
it cannot read still gives the goal-labelled issues.

What a blocker waits for, from facts on GitHub only:
- a-pr: open, and no open or merged PR says it fixes, addresses or is part of it
- tests: an open PR names it and has fewer than 2 test reports on its current head (api/triage.json)
- decision: an open PR names it and is ready to decide (triage READY_RULE)
- author: an open PR names it, has its test reports, but checks fail or it conflicts with main
- draft: only draft PRs name it
- retest: a PR naming it was merged and the issue is still open: does current main still stop there?
"""
import datetime as dt
import json
import os
import re

from . import db
from .triage import WORKS_ON      # same rule as the label check: "fixes", "addresses", "part of", "towards" #n

REPO = os.environ.get("XC_REPO", "xcl-dev/xcl")
REPO_URL = f"https://github.com/{REPO}"
REFS_EVERY_S = int(os.environ.get("XC_ROADMAP_REFS_EVERY", "600"))
QUIET_DAYS = 3                                  # the repo's own stale rule (#1833): 3 days without activity
GOAL = re.compile(r"goal:?\s*\*\*(.+?)\*\*", re.I)
HEADER = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
BUCKET = re.compile(r"^\s*[-*]\s+(.+?):\s*(#\d.*)$")
NOTE = re.compile(r"\s*\(([^)]*)\)\s*$")
# Goal text -> the ladder stage it is about (xc/progress.py STAGES); "past"/"beyond" means the next stage is the target.
STAGE_WORDS = [("plays_well", r"plays? well|hour"), ("playable", r"playable|gameplay|control"),
               ("in_game", r"world on screen|in.game|world (is )?drawn"), ("world_load", r"world.?load"),
               ("menus", r"menu"), ("title", r"title screen"), ("first_frame", r"first (frame|picture)")]
NEEDS = {"a-pr": "nobody has a PR for it",
         "tests": "a PR waits for test reports",
         "decision": "a PR is ready for a maintainer decision",
         "author": "its PR has test reports but waits for its author (checks or conflicts)",
         "draft": "only draft PRs so far",
         "retest": "a PR naming it was merged, the issue is still open: retest on current main"}


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _days(s):
    return None if not s else round((_now() - _iso(s)).total_seconds() / 86400, 1)


# --- tags, releases, milestones: a few cheap requests every 10 minutes (loop step) -----------------------------

def fetch(con=None, gh=None, force=False):
    con = con or db.connect()
    last = db.get_state(con, "roadmap:refs")
    if last and not force and (_now() - _iso(json.loads(last)["fetched"])).total_seconds() < REFS_EVERY_S:
        return {"skipped": True}
    from .gh import GitHub
    gh = gh or GitHub()

    def first(path, params=None):
        for status, data, _ in gh.pages(path, {"per_page": 100, **(params or {})}):
            return data or []
        return []
    tags = [{"name": t["name"], "sha": t["commit"]["sha"]} for t in first(f"/repos/{REPO}/tags")]
    rels = [{"tag": r["tag_name"], "name": r.get("name"), "published": r.get("published_at"), "draft": r.get("draft"),
             "prerelease": r.get("prerelease"), "url": r["html_url"]} for r in first(f"/repos/{REPO}/releases")]
    mils = [{"number": m["number"], "title": m["title"], "state": m["state"], "open": m["open_issues"],
             "closed": m["closed_issues"], "due": m.get("due_on"), "url": m["html_url"]}
            for m in first(f"/repos/{REPO}/milestones", {"state": "all"})]
    latest = None
    if tags:                                    # GitHub lists tags newest name first, not newest date: take the date
        t = tags[0]
        _, c, _ = gh._req(f"https://api.github.com/repos/{REPO}/commits/{t['sha']}")
        _, cmp_, _ = gh._req(f"https://api.github.com/repos/{REPO}/compare/{t['sha']}...HEAD")
        latest = {**t, "date": ((c or {}).get("commit") or {}).get("committer", {}).get("date"),
                  "main_ahead_by": (cmp_ or {}).get("ahead_by")}
    refs = {"fetched": _now().strftime("%Y-%m-%dT%H:%M:%SZ"), "tags": tags[:20], "latest_tag": latest,
            "releases": rels[:20], "milestones": mils}
    db.set_state(con, "roadmap:refs", json.dumps(refs))
    con.commit()
    return {"tags": len(tags), "releases": len(rels), "milestones": len(mils)}


# --- reading the roadmap issue ---------------------------------------------------------------------------------

def parse(body):
    """{'goal', 'buckets': [{'name', 'note', 'issues'}], 'hubs': [{'name', 'issues'}]}; buckets empty if unreadable."""
    body = (body or "").replace("\r", "")
    m = GOAL.search(body)
    out = {"goal": m.group(1).strip() if m else None, "buckets": [], "hubs": []}
    section = ""
    for line in body.split("\n"):
        h = HEADER.match(line)
        if h:
            section = h.group(1).lower()
            continue
        b = BUCKET.match(line)
        if not b:
            continue
        name, rest = b.group(1).strip(), b.group(2)
        nums = [int(x) for x in re.findall(r"#(\d{1,5})\b", rest)]
        if "stop" in section or "block" in section:
            note = NOTE.search(name)
            out["buckets"].append({"name": NOTE.sub("", name).strip(), "note": note.group(1) if note else None,
                                   "issues": list(dict.fromkeys(nums))})
        elif "go" in section:
            out["hubs"].append({"name": name, "issues": nums})
    return out


def target_stage(goal):
    """(stage the goal names, stage it asks to reach) as indexes in progress.STAGES, or (None, None)."""
    from . import progress as P
    g = (goal or "").lower()
    for sid, words in STAGE_WORDS:
        if re.search(words, g):
            k = P.STAGE_IDS.index(sid)
            return k, min(k + 1, len(P.STAGES) - 1) if re.search(r"\b(past|beyond|through|after)\b", g) else k
    return None, None


def roadmaps(con, maintainers):
    """Every roadmap issue a maintainer opened, the current one first (newest open), then the older ones."""
    rows = con.execute("SELECT number, author, title, body, status, created, updated, url FROM items "
                       "WHERE kind='issue' AND title LIKE 'Roadmap%' ORDER BY (status='open') DESC, created DESC").fetchall()
    return [dict(r) for r in rows if r["author"] in maintainers]


def goal_history(con, number):
    """Goals the roadmap issue has had, from the stored versions of its body (oldest first)."""
    out = []
    for r in con.execute("SELECT seen, updated, body FROM versions WHERE key=? ORDER BY COALESCE(updated, seen)", (f"issue:{number}",)):
        g = parse(r["body"])["goal"]
        if g and (not out or out[-1]["goal"] != g):
            out.append({"goal": g, "since": r["updated"] or r["seen"]})
    return out


# --- facts per issue --------------------------------------------------------------------------------------------

def _labels(raw):
    try:
        return (json.loads(raw or "{}") or {}).get("labels") or []
    except ValueError:
        return []


def pr_links(con):
    """issue -> PRs whose title or body says they fix, address or are part of it: [{pr, status, merged, updated, author}]."""
    out = {}
    for r in con.execute("SELECT number, title, body, status, merged, updated, author, raw FROM items WHERE kind='pr'"):
        text = f"{r['title'] or ''}\n{r['body'] or ''}"
        for n in {int(x) for x in WORKS_ON.findall(text)}:
            raw = json.loads(r["raw"] or "{}") or {}
            out.setdefault(n, []).append({"pr": r["number"], "status": r["status"], "merged": r["merged"],
                                          "updated": r["updated"], "author": r["author"], "draft": bool(raw.get("draft")),
                                          "labels": raw.get("labels") or []})
    return out


def issue_facts(con, n, links, triage, reports, maintainers, goal_label=None, thread=False):
    """thread: a hub the roadmap sends work to (#1269 "official thread"): a merged PR does not ask for a retest."""
    it = con.execute("SELECT * FROM items WHERE key=?", (f"issue:{n}",)).fetchone()
    if not it:
        return {"issue": n, "known": False}
    com = con.execute("SELECT author, created FROM items WHERE kind='comment' AND number=? ORDER BY created", (n,)).fetchall()
    week = (_now() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    prs = sorted(links.get(n, []), key=lambda p: -p["pr"])
    open_prs, merged = [], []
    for p in prs:
        if p["status"] == "open":
            t = triage.get(p["pr"]) or {}
            open_prs.append({"pr": p["pr"], "author": p["author"], "draft": p["draft"],
                             "ready_to_decide": bool(t.get("ready_to_decide")),
                             "test_reports_on_head": (t.get("test_reports_on_head") or {}).get("count", 0),
                             "conflicts": (t.get("checks") or {}).get("mergeable") == "CONFLICTING",
                             "goal_label": bool(goal_label) and goal_label in p["labels"],
                             "updated": p["updated"]})
        elif p["status"] == "merged":
            merged.append({"pr": p["pr"], "merged": p["merged"], "author": p["author"]})
    merged.sort(key=lambda p: p["merged"] or "", reverse=True)
    acts = [it["created"]] + [c["created"] for c in com] + [p["updated"] for p in open_prs] + [p["merged"] for p in merged if p["merged"]]
    last = max(a for a in acts if a)
    maint = [c["created"] for c in com if c["author"] in maintainers]
    src = f"/issues/{n}#"
    reps = [r for r in reports if src in (r.get("source") or "") and (r.get("date") or "") >= week]
    needs = []
    if it["status"] == "open":
        if merged and not thread:
            needs.append("retest")
        if any(p["ready_to_decide"] for p in open_prs):
            needs.append("decision")
        if any(not p["draft"] and not p["ready_to_decide"] and p["test_reports_on_head"] < 2 for p in open_prs):
            needs.append("tests")
        live = [p for p in open_prs if not p["draft"]]
        if live and not any(p["ready_to_decide"] or p["test_reports_on_head"] < 2 for p in live):
            needs.append("author")
        if open_prs and not live:
            needs.append("draft")
        if not open_prs and not merged:
            needs.append("a-pr")
    return {"issue": n, "known": True, "thread": thread, "status": it["status"], "title": it["title"], "url": it["url"],
            "closed": it["closed"], "labels": _labels(it["raw"]), "comments": len(com),
            "comments_7d": sum(1 for c in com if c["created"] >= week), "last_activity": last,
            "quiet_days": _days(last) if _days(last) and _days(last) >= QUIET_DAYS else None,
            "last_maintainer_comment": maint[-1] if maint else None,
            "run_reports_7d": len(reps), "run_reporters_7d": len({r["author"] for r in reps}),
            "open_prs": open_prs, "merged_prs": merged, "needs": needs}


# --- build ------------------------------------------------------------------------------------------------------

def build(con, out):
    """Returns (roadmap dict, feed events). Reads api/triage.json and api/progress.json written earlier in the pass."""
    from . import people, progress as P
    maintainers = people.maintainers(con)
    all_rm = roadmaps(con, maintainers)
    rm = all_rm[0] if all_rm and all_rm[0]["status"] == "open" else None
    rm_raw = rm and con.execute("SELECT raw FROM items WHERE key=?", (f"issue:{rm['number']}",)).fetchone()["raw"]
    # The goal's label is the one the roadmap issue carries (goal:world-load today); a new goal can bring another.
    goal_label = next((l for l in _labels(rm_raw) if l.startswith("goal:")), None) if rm else None

    def load(name):
        try:
            with open(f"{out}/api/{name}.json") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}
    tri = {p["pr"]: p for p in (load("triage").get("prs") or [])}
    prog = load("progress")
    reports = prog.get("reports") or []
    links = pr_links(con)
    refs = json.loads(db.get_state(con, "roadmap:refs") or "null")

    goal_issues = sorted({r["number"] for r in con.execute("SELECT number, raw FROM items WHERE kind='issue' AND status='open'")
                          if goal_label and goal_label in _labels(r["raw"])})
    labels_seen = sorted({l for r in con.execute("SELECT raw FROM items WHERE kind IN ('issue','pr')") for l in _labels(r["raw"])
                          if l.startswith("goal:")})
    parsed = parse(rm["body"]) if rm else {"goal": None, "buckets": [], "hubs": []}
    listed = {n for b in parsed["buckets"] for n in b["issues"]}
    hubs = {n for h in parsed["hubs"] for n in h["issues"]}
    buckets = []
    for i, b in enumerate(parsed["buckets"]):
        facts = [issue_facts(con, n, links, tri, reports, maintainers, goal_label,
                             n in hubs or "thread" in (b["note"] or "").lower()) for n in b["issues"]]
        buckets.append({"rank": i + 1, "name": b["name"], "note": b["note"], "issues": facts,
                        "open": sum(1 for f in facts if f.get("status") == "open"),
                        "closed": sum(1 for f in facts if f.get("status") == "closed")})
    others = [issue_facts(con, n, links, tri, reports, maintainers, goal_label) for n in goal_issues if n not in listed
              and (not rm or n != rm["number"])]
    gk, tk = target_stage(parsed["goal"])
    byp = prog.get("by_platform") or {}
    stage_ids = P.STAGE_IDS
    week = (_now() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    at_goal = [r for r in reports if gk is not None and r.get("stage") == stage_ids[gk] and (r.get("date") or "") >= week]
    ends = {}
    for r in at_goal:
        ends.setdefault(r.get("platform") or "?", {}).setdefault(r.get("ended") or "unknown", set()).add(r["author"])
    ladder = [{"id": sid, "name": name, "people_7d": ((byp.get("all") or {}).get("people_per_stage") or {}).get(sid, 0),
               "confirm_people": next((s.get("confirm_people") for s in prog.get("stages", []) if s["id"] == sid), None),
               "role": ("goal" if k == tk else "next" if tk is not None and k > tk else "behind" if tk is not None and k < tk else None)}
              for k, (sid, name, _) in enumerate(P.STAGES)]
    since = (refs or {}).get("latest_tag", {}) or {}
    since_date = since.get("date") or (rm or {}).get("created")
    merged_since = sorted({(p["pr"], p["merged"]) for b in buckets for f in b["issues"] for p in f.get("merged_prs", [])
                           if p["merged"] and since_date and p["merged"] >= since_date}
                          | {(p["pr"], p["merged"]) for f in others for p in f.get("merged_prs", [])
                             if p["merged"] and since_date and p["merged"] >= since_date}, key=lambda x: x[1], reverse=True)
    closed_since = [f["issue"] for b in buckets for f in b["issues"]
                    if f.get("status") == "closed" and since_date and (f.get("closed") or "") >= since_date]
    data = {"generated": _now().strftime("%Y-%m-%dT%H:%M:%SZ"), "repo": REPO,
            "roadmap_issue": rm and {"number": rm["number"], "url": rm["url"], "status": rm["status"], "updated": rm["updated"]},
            "goal": parsed["goal"], "goal_history": goal_history(con, rm["number"]) if rm else [],
            "goal_stage": stage_ids[gk] if gk is not None else None, "target_stage": stage_ids[tk] if tk is not None else None,
            "goal_label": goal_label, "goal_labels_on_github": labels_seen, "readable": bool(parsed["buckets"]),
            "previous_roadmaps": [{"number": r["number"], "url": r["url"], "status": r["status"], "created": r["created"],
                                   "goal": parse(r["body"])["goal"]} for r in all_rm if not rm or r["number"] != rm["number"]],
            "buckets": buckets, "other_goal_issues": others, "hubs": parsed["hubs"], "ladder": ladder,
            "runs_at_goal_stage_7d": {p: {k: len(v) for k, v in d.items()} for p, d in ends.items()},
            "furthest_by_platform": {p: {"by_few": v.get("furthest_by_few"), "confirmed": v.get("furthest_confirmed")}
                                     for p, v in byp.items()},
            "refs": refs, "since": {"what": "latest tag" if since.get("date") else "roadmap posted", "date": since_date,
                                    "merged_prs": [p for p, _ in merged_since], "closed_issues": closed_since},
            "needs": NEEDS, "quiet_days_rule": QUIET_DAYS}
    os.makedirs(f"{out}/api", exist_ok=True)
    api = json.loads(json.dumps(data))
    for f in [f for b in api["buckets"] for f in b["issues"]] + api["other_goal_issues"]:
        f.pop("title", None)                    # free text stays on GitHub and on the escaped page
    with open(f"{out}/api/roadmap.json", "w") as fh:
        json.dump(api, fh, separators=(",", ":"))
    base = os.environ.get("XC_BASE_URL", "https://greemsc.github.io/xcl-campaigns") + "/roadmap.html"
    ev = []
    if rm:
        ev.append({"id": f"roadmap-issue-{rm['number']}", "link": rm["url"], "title": f"XCL roadmap issue #{rm['number']}"})
    if parsed["goal"]:
        ev.append({"id": "roadmap-goal-" + db.digest(parsed["goal"]), "link": base, "title": f"Roadmap goal: {parsed['goal']}"})
    for b in buckets:
        for f in b["issues"]:
            if f.get("status") == "closed":
                ev.append({"id": f"roadmap-closed-{f['issue']}", "link": base, "title": f"Roadmap blocker #{f['issue']} closed ({b['name']})"})
            if "decision" in f.get("needs", []):
                for p in f["open_prs"]:
                    if p["ready_to_decide"]:
                        ev.append({"id": f"roadmap-ready-{p['pr']}", "link": base,
                                   "title": f"PR #{p['pr']} for roadmap blocker #{f['issue']} is ready for a decision"})
    for t in (refs or {}).get("tags", []):
        ev.append({"id": f"tag-{t['name']}", "link": f"{REPO_URL}/releases/tag/{t['name']}", "title": f"XCL tag {t['name']}"})
    for m in (refs or {}).get("milestones", []):
        ev.append({"id": f"milestone-{m['number']}", "link": m["url"], "title": f"XCL milestone: {m['title']}"})
    for l in labels_seen:
        if l != "goal:world-load":            # the first goal label (2026-11-24); any later one is news
            ev.append({"id": f"goal-label-{l}", "link": f"{REPO_URL}/issues?q=label%3A{l}", "title": f"New goal label on XCL: {l}"})
    return data, ev


# --- page -------------------------------------------------------------------------------------------------------

CSS = """
.rm-goal{font-size:clamp(19px,3vw,24px);margin:4px 0 8px}.rm-goal b{color:var(--warn)}
.rm-ladder{display:grid;grid-template-columns:repeat(8,1fr);gap:4px;margin:14px 0 4px}
.rm-ladder div{padding:8px;border-radius:6px;background:var(--chip);font-size:12.5px;line-height:1.25}
.rm-ladder div small{display:block;color:var(--mute);font-size:11px;margin-top:3px}
.rm-ladder .behind{background:var(--ok);color:var(--bg)}.rm-ladder .behind small{color:var(--bg);opacity:.85}
.rm-ladder .goal{outline:2px solid var(--warn);background:var(--hi)}
.blk{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--bad);border-radius:8px;padding:10px 14px;margin:10px 0}
.blk.done{border-left-color:var(--ok);opacity:.75}.blk h3{margin:0 0 6px;font-size:16px}.blk h3 small{color:var(--mute);font-weight:400}
.need{display:inline-block;font-size:11.5px;padding:0 7px;border-radius:9px;margin:1px 3px 1px 0;border:1px solid}
.need.a-pr{color:var(--bad);border-color:var(--bad)}.need.tests,.need.retest{color:var(--warn);border-color:var(--warn)}
.need.decision{color:var(--ok);border-color:var(--ok)}.need.closed{color:var(--mute);border-color:var(--line)}
.focus{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:10px 0}
.focus .card ul{margin:6px 0 0;padding-left:18px;font-size:14px}.focus .card li{margin:3px 0}
@media (max-width:640px){.rm-ladder{grid-template-columns:repeat(4,1fr)}}
"""

def _pf(p):
    from . import progress as P
    return dict(P.PLATFORMS).get(p, {"all": "All platforms", "?": "Platform not said"}.get(p, p))


def _issue(e, f):
    return f'<a href="{REPO_URL}/issues/{f["issue"]}">#{f["issue"]}</a>'


def _pr(e, n):
    return f'<a href="{REPO_URL}/pull/{n}">#{n}</a>'


def _row(e, ft, ago, f):
    if not f.get("known"):
        return f'<tr><td>{_issue(e, f)}</td><td colspan=4 class=mute>not read yet by the board</td></tr>'
    chips = "".join(f'<span class="need {k}">{e(NEEDS[k].split(":")[0])}</span>' for k in f["needs"]) or (
        '<span class="need closed">closed</span>' if f["status"] == "closed" else "")
    prs = []
    for p in sorted(f["open_prs"], key=lambda p: (not p["ready_to_decide"], p["draft"], -p["test_reports_on_head"]))[:6]:
        bits = ["draft" if p["draft"] else f'{p["test_reports_on_head"]} test report{"s" if p["test_reports_on_head"] != 1 else ""} on head']
        if p["ready_to_decide"]:
            bits.append("ready to decide")
        if p["conflicts"]:
            bits.append("conflicts")
        prs.append(f'{_pr(e, p["pr"])} <span class=mute>({e(", ".join(bits))})</span>')
    if len(f["open_prs"]) > 6:
        prs.append(f'<span class=mute>+{len(f["open_prs"]) - 6} open</span>')
    for p in f["merged_prs"][:3]:
        prs.append(f'{_pr(e, p["pr"])} <span class=mute>merged {ago(e, p["merged"])}</span>')
    more = len(f["merged_prs"]) - 3
    if more > 0:
        prs.append(f'<span class=mute>+{more} merged</span>')
    act = ago(e, f["last_activity"]) + (f' <span class="warn">· quiet {int(f["quiet_days"])} d</span>' if f["quiet_days"] else "")
    r = f["run_reporters_7d"]
    who = f'{r} {"person" if r == 1 else "people"} reported runs' if r else ""
    return (f'<tr{" class=mute" if f["status"] == "closed" else ""}><td class=nw>{_issue(e, f)}</td><td>{ft(f["title"])}'
            f'<div>{chips}</div></td><td>{"<br>".join(prs) or "<span class=mute>none</span>"}</td>'
            f'<td class=nw>{act}<br><span class=mute>{f["comments_7d"]} comments this week</span></td>'
            f'<td class="num">{e(who)}</td></tr>')


def html(d, e, ft, ago):
    rm = d["roadmap_issue"]
    o = ['<h1>Roadmap: the current goal and what blocks it</h1>']
    prev = d["previous_roadmaps"]
    prev_html = ('<h2 id="before">Earlier roadmaps</h2><ul>' + "".join(
        f'<li><a href="{e(r["url"])}">#{r["number"]}</a> ({e(r["status"])}, posted {ago(e, r["created"])}): {ft(r["goal"] or "?")}</li>'
        for r in prev) + '</ul>') if prev else ""
    if not rm:
        o.append('<p class="banner">No open roadmap issue from a maintainer (an issue titled "Roadmap: …"). '
                 'This page fills itself when one is posted.</p>' + prev_html)
        return "\n".join(o)
    o.append(f'<p class="rm-goal">Goal: <b>{ft(d["goal"] or "?")}</b></p>')
    hist = d["goal_history"]
    o.append(f'<p class="lede">Read from <a href="{e(rm["url"])}">#{rm["number"]}</a>, written by the maintainer '
             f'(edited {ago(e, rm["updated"])}); this page follows it every few minutes. The groups and their order are the '
             f'maintainer\'s; what each blocker waits for is computed from GitHub (open and merged PRs that say they fix, '
             f'address or are part of it, and test reports on their current head). Nothing here is written by an AI.'
             + (f' Label of this goal on GitHub: <a href="{REPO_URL}/issues?q=is%3Aopen+label%3A{e(d["goal_label"])}"><code>{e(d["goal_label"])}</code></a>.'
                if d["goal_label"] else "")
             + (f' Goal since {ago(e, hist[-1]["since"])}' + (f', before: {", ".join(ft(h["goal"]) for h in hist[:-1])}' if len(hist) > 1 else "") + "." if hist else "")
             + '</p>')
    if not d["readable"]:
        o.append(f'<p class="banner">The board could not read the blocker list of #{rm["number"]} (its format changed). '
                 'The goal-labelled issues are listed below; the page will follow the new format once the board is updated.</p>')
    # ladder
    o.append('<h2 id="stages">Stages</h2><div class="rm-ladder">' + "".join(
        f'<div class="{s["role"] or ""}">{e(s["name"])}<small>{s["people_7d"]} people this week'
        f'{" · goal" if s["role"] == "goal" else ""}</small></div>' for s in d["ladder"]) + '</div>')
    nxt = [s["name"] for s in d["ladder"] if s["role"] == "next"]
    o.append('<p class="note">People who report getting at least that far in the last 7 days (<a href="reports.html">test reports</a>, '
             'read by an AI from GitHub comments). Outlined: the stage the goal asks for.'
             + (f' After it: {e(", then ".join(nxt))}.' if nxt else "") + '</p>')
    if d["runs_at_goal_stage_7d"]:
        stage = next((s["name"] for s in d["ladder"] if s["id"] == d["goal_stage"]), "")
        rows = "".join(f'<tr><td>{e(_pf(p))}</td><td class=num>{v.get("crashes", 0)}</td><td class=num>{v.get("stalls", 0)}</td>'
                       f'<td class=num>{v.get("exits", 0)}</td><td class=num>{v.get("keeps_running", 0) + v.get("stopped_by_user", 0) + v.get("unknown", 0)}</td></tr>'
                       for p, v in sorted(d["runs_at_goal_stage_7d"].items(), key=lambda x: -sum(x[1].values())))
        o.append(f'<details><summary>How runs end at "{e(stage)}" this week, by platform (people)</summary><div class=scroll>'
                 '<table class="tbl"><tr><th>Platform</th><th class=num>crash</th><th class=num>stall</th><th class=num>game quits</th>'
                 f'<th class=num>other</th></tr>{rows}</table></div></details>')
    # focus
    allf = [(b, f) for b in d["buckets"] for f in b["issues"] if f.get("known")] + [({"name": "also labelled", "rank": 99}, f) for f in d["other_goal_issues"] if f.get("known")]
    o.append('<h2 id="now">What blocks now</h2><div class="focus">')
    for k, title in [("a-pr", "Nobody has a PR"), ("tests", "PRs waiting for test reports"),
                     ("decision", "Ready for a maintainer decision"), ("retest", "Fix merged, issue still open")]:
        items = [(b, f) for b, f in allf if k in f["needs"]]
        if k in ("tests", "decision"):           # one line per issue: a busy thread (#1269) must not hide the others
            lis, n_prs = [], 0
            for b, f in sorted(items, key=lambda x: x[1].get("thread", False)):
                ps = [p for p in f["open_prs"] if (p["ready_to_decide"] if k == "decision" else
                                                    not p["draft"] and not p["ready_to_decide"] and p["test_reports_on_head"] < 2)]
                n_prs += len(ps)
                lis.append(f'<li>{_issue(e, f)}: ' + ", ".join(_pr(e, p["pr"]) for p in ps[:5])
                           + (f' <span class=mute>+{len(ps) - 5}</span>' if len(ps) > 5 else "") + '</li>')
        elif k == "retest":
            lis = [f'<li>{_issue(e, f)} · merged {", ".join(_pr(e, p["pr"]) for p in f["merged_prs"][:3])}</li>' for b, f in items]
        else:
            lis = [f'<li>{_issue(e, f)} <span class=mute>{e(b["name"] if b["rank"] != 99 else "labelled, not in the roadmap list")}</span></li>'
                   for b, f in items]
        count = f'{n_prs} PRs, {len(lis)} issues' if k in ("tests", "decision") else len(lis)
        o.append(f'<div class="card"><h3>{e(title)} <small class=mute>({count})</small></h3>'
                 + (f'<ul>{"".join(lis[:12])}</ul>' + (f'<p class=note>+{len(lis) - 12} more below</p>' if len(lis) > 12 else "")
                    if lis else '<p class="mute">none</p>') + '</div>')
    o.append('</div><p class="note">Blockers in the maintainer\'s order (first group = biggest obstacle). '
             'A PR in another state (draft, or tested but failing checks) shows in the group\'s table. '
             f'"Quiet": no comment, PR update or merge for {QUIET_DAYS}+ days. Only "fixes", "closes", "resolves", "addresses", '
             '"part of" or "towards" followed by the issue number links a PR to an issue (the rule of the goal label): '
             'a PR that only mentions the number is not counted.</p>')
    # buckets
    o.append('<h2 id="blockers">Blockers, group by group</h2>')
    for b in d["buckets"]:
        done = b["open"] == 0 and b["closed"] > 0
        o.append(f'<section class="blk{" done" if done else ""}" id="g{b["rank"]}"><h3>{b["rank"]}. {ft(b["name"])} '
                 f'<small>{("(" + ft(b["note"]) + ") ") if b["note"] else ""}{b["open"]} open, {b["closed"]} closed</small></h3>'
                 '<div class=scroll><table class="tbl"><tr><th>Issue</th><th>Title, waits for</th><th>PRs naming it</th>'
                 '<th>Last activity</th><th class=num>This week</th></tr>'
                 + "".join(_row(e, ft, ago, f) for f in b["issues"]) + '</table></div></section>')
    if d["other_goal_issues"]:
        o.append(f'<details><summary>Other open issues labelled {e(d["goal_label"])} but not in the roadmap list ({len(d["other_goal_issues"])})</summary>'
                 '<div class=scroll><table class="tbl"><tr><th>Issue</th><th>Title, waits for</th><th>PRs naming it</th><th>Last activity</th>'
                 '<th class=num>This week</th></tr>' + "".join(_row(e, ft, ago, f) for f in d["other_goal_issues"]) + '</table></div></details>')
    # tags, releases, milestones
    refs, s = d["refs"] or {}, d["since"]
    o.append('<h2 id="tags">Tags, releases, milestones</h2>')
    lt = refs.get("latest_tag")
    if not refs:
        o.append('<p class="mute">Not read yet.</p>')
    else:
        if lt:
            o.append(f'<p>Latest tag: <a href="{REPO_URL}/releases/tag/{e(lt["name"])}"><b>{e(lt["name"])}</b></a>'
                     + (f' ({ago(e, lt["date"])})' if lt.get("date") else "")
                     + (f'; main is {lt["main_ahead_by"]} commits ahead of it' if lt.get("main_ahead_by") is not None else "") + '.</p>')
        else:
            o.append('<p>XCL has <b>no tag or release yet</b>. The first one will show here and in the <a href="feed.xml">feed</a>.</p>')
        rel = [r for r in refs.get("releases", []) if not r.get("draft")]
        if rel:
            o.append('<ul>' + "".join(f'<li><a href="{e(r["url"])}">{e(r["tag"])}</a>{" (pre-release)" if r.get("prerelease") else ""} '
                                      f'{ago(e, r["published"]) if r.get("published") else ""}</li>' for r in rel[:5]) + '</ul>')
        mils = refs.get("milestones") or []
        if mils:
            o.append('<div class=scroll><table class="tbl"><tr><th>Milestone</th><th>State</th><th class=num>Open</th><th class=num>Closed</th>'
                     '<th>Due</th></tr>' + "".join(
                         f'<tr><td><a href="{e(m["url"])}">{ft(m["title"])}</a></td><td>{e(m["state"])}</td><td class=num>{m["open"]}</td>'
                         f'<td class=num>{m["closed"]}</td><td>{e((m.get("due") or "")[:10])}</td></tr>' for m in mils) + '</table></div>')
        else:
            o.append('<p class="mute">No GitHub milestones; the roadmap issue is the plan.</p>')
        o.append(f'<p class="note">Checked {ago(e, refs["fetched"])}. Goal labels on GitHub: '
                 + (", ".join(f'<code>{e(l)}</code>' for l in d["goal_labels_on_github"]) or "none") + '; a new one shows in the feed.</p>')
    what = "the latest tag" if s["what"] == "latest tag" else "the roadmap was posted"
    o.append(f'<h3>In the next tag, toward the goal</h3><p>Since {e(what)} ({ago(e, s["date"]) if s["date"] else "?"}): '
             f'{len(s["merged_prs"])} merged PR{"s" if len(s["merged_prs"]) != 1 else ""} naming a goal issue'
             + (": " + ", ".join(_pr(e, n) for n in s["merged_prs"][:30]) if s["merged_prs"] else "")
             + f'; {len(s["closed_issues"])} roadmap blocker{"s" if len(s["closed_issues"]) != 1 else ""} closed'
             + (": " + ", ".join(f'<a href="{REPO_URL}/issues/{n}">#{n}</a>' for n in s["closed_issues"]) if s["closed_issues"] else "")
             + '.</p>')
    if d["hubs"]:
        o.append('<h2 id="where">Where things go (from the roadmap)</h2><ul>' + "".join(
            f'<li>{ft(h["name"])}: ' + ", ".join(f'<a href="{REPO_URL}/issues/{n}">#{n}</a>' for n in h["issues"]) + '</li>'
            for h in d["hubs"]) + '</ul>')
    o.append(prev_html)
    o.append('<p class="note">Same data as JSON: <a href="api/roadmap.json">api/roadmap.json</a> (no titles: numbers, states, dates).</p>')
    return "\n".join(o)


def write(con, out, page, e, ft, ago):
    d, ev = build(con, out)
    with open(f"{out}/roadmap.html", "w") as fh:
        fh.write(page("XCL roadmap: the current goal and what blocks it · XCL board", html(d, e, ft, ago), "api/roadmap.json",
                      nav="roadmap", path="roadmap.html", crumb="Roadmap",
                      description="The XCL maintainer's roadmap for GTA VI, followed issue by issue: what blocks the current goal, "
                                  "which PRs work on it, what waits for tests or a decision, and the next stages."))
    open_ = sum(b["open"] for b in d["buckets"])
    return {"goal": d["goal"], "blockers_open": open_,
            "needs": {k: sum(1 for b in d["buckets"] for f in b["issues"] if k in f.get("needs", [])) for k in NEEDS}}, ev
