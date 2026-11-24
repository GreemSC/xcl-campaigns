"""The whole repository, not only campaigns: areas, overlapping PRs, duplicate issues. Code only, no AI.

Links are candidates for a human to check, never verdicts:
- two open PRs say they fix the same issue, or touch mostly the same files AND have similar titles;
- two open issues share a crash signature (xcl.exe+0x… offset), or have very similar titles."""
import collections
import json
import os
import re

LAST_ANALYSIS = None   # the analysis of the last pass, set by write_api
TRIVIAL = re.compile(r"(^|/)(Cargo\.lock|README\.md|HANDOFF\.md|CONTRIBUTING\.md|AGENTS\.md|CLAUDE\.md|CHANGELOG\.md)$|^\.github/")
FIXES = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d{2,5})\b", re.I)
TITLE_REF = re.compile(r"\(#(\d{2,5})\)\s*$")
TRACKER_PRS = 6   # an issue that more open PRs than this point to is a tracker, not a shared bug
CRASH = re.compile(r"\bxcl\.exe\s*\+\s*(0x[0-9a-fA-F]{4,})")
STOP = set("a an the of to in on for and or with from by is are be as at it its this that via when not no into per "
           "d3d12 d3d12x xcl recompiler fix fixes add adds use make game crash crashes issue bug error when after "
           "windows linux gta gtavi gta6 does doesn't don't can't cannot".split())
AREA_WORDS = [("shaders", r"shader|dxc|dxil|hlsl|recomp|pso|pipeline|spir"), ("memory", r"memory|vram|heap|commit|page|alloc"),
              ("linux-wine", r"linux|wine|proton|vkd3d|radv|steam ?deck"), ("crash", r"crash|exception|0xc0|access violation"),
              ("audio", r"audio|xaudio|xma|opus"), ("input", r"input|keyboard|mouse|controller|gamepad"),
              ("storage", r"dstorage|directstorage|bcpack|rpf|vfs"), ("video", r"bink|movie|video|mfplat")]


def ft(x):
    """Free text from GitHub for a page: escaped, withheld when it reads like an instruction (render.ft)."""
    from .render import ft as f
    return f(x)



def words(t):
    return {w for w in re.findall(r"[a-z0-9_]{3,}", (t or "").lower()) if w not in STOP}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def area_of_path(p):
    """File paths come from PR authors (untrusted): the area name is reduced to a safe charset."""
    if p.startswith("crates/xcl/src/"):
        parts = p[len("crates/xcl/src/"):].split("/")
        a = "/".join(parts[:2]) if len(parts) > 2 else parts[0].removesuffix(".rs")
    else:
        a = p.split("/")[0]
    a = re.sub(r"[^A-Za-z0-9_/-]", "_", a).strip("/._") or "other"
    return a[:60]


def area_of(title, paths):
    if paths:
        c = collections.Counter(area_of_path(p) for p in paths)
        return c.most_common(1)[0][0]
    t = (title or "").lower()
    for name, rx in AREA_WORDS:
        if re.search(rx, t):
            return name
    return "other"


class UF:
    def __init__(self, keys):
        self.p = {k: k for k in keys}

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a, b):
        self.p[self.find(a)] = self.find(b)

    def groups(self):
        g = collections.defaultdict(list)
        for k in self.p:
            g[self.find(k)].append(k)
        return sorted((sorted(v) for v in g.values() if len(v) > 1), key=lambda v: (-len(v), v[0]))


def analyse(con):
    from . import intent, verify
    intents = intent.load(con)
    prs = {r["number"]: dict(r) for r in con.execute(
        "SELECT number, author, title, body, created, url, status FROM items WHERE kind='pr'")}
    issues = {r["number"]: dict(r) for r in con.execute(
        "SELECT number, author, title, body, created, url, status FROM items WHERE kind='issue'")}
    files = collections.defaultdict(set)
    for r in con.execute("SELECT number, path FROM pr_files"):
        if r["path"] and not TRIVIAL.search(r["path"]):
            files[r["number"]].add(r["path"])
    open_prs = [n for n, p in prs.items() if p["status"] == "open"]
    fixes = {n: ({int(x) for x in FIXES.findall(prs[n]["body"] or "")}
                 | {int(x) for x in TITLE_REF.findall(prs[n]["title"] or "")}) & set(issues) for n in prs}
    count = collections.Counter(i for n in prs for i in fixes[n])          # open and merged PRs
    trackers = {i for i, k in count.items() if k > TRACKER_PRS} | {
        i for i, v in issues.items()
        if re.search(r"track|\[official\]|\bmeta\b|roadmap|results", v["title"] or "", re.I)
        or len(re.findall(r"[,/&;]", v["title"] or "")) >= 3}             # umbrella issues listing many topics
    fixes = {n: v - trackers for n, v in fixes.items()}
    tw = {n: words(p["title"]) for n, p in prs.items()}

    # Overlapping open PRs.
    uf, why = UF(open_prs), collections.defaultdict(set)
    by_issue = collections.defaultdict(list)
    for n in open_prs:
        for i in fixes[n]:
            by_issue[i].append(n)
    for i, ns in by_issue.items():
        if len({prs[n]["author"] for n in ns}) < 2:
            continue                                  # one author's stacked PRs are not duplicates
        for a in ns[1:]:
            uf.join(a, ns[0])
        for a in ns:
            why[a].add(f"says it fixes #{i}")
    sized = sorted(n for n in open_prs if 0 < len(files[n]) <= 40)
    for k, a in enumerate(sized):
        for b in sized[k + 1:]:
            fj = jac(files[a], files[b])
            if prs[a]["author"] != prs[b]["author"] and fj >= 0.5 and jac(tw[a], tw[b]) >= 0.25:
                uf.join(a, b)
                why[a].add("same files, similar title")
                why[b].add("same files, similar title")
    # Same intent (AI intent cards): same area, at least 2 shared keywords and keyword overlap >= 50 %,
    # or the same crash offset / same fixed issue according to the cards. Different authors only.
    ik = {n: intents.get(f"pr:{n}") for n in open_prs}
    with_int = [n for n in open_prs if ik[n]]
    for k, a_ in enumerate(with_int):
        for b in with_int[k + 1:]:
            x, y = ik[a_], ik[b]
            if prs[a_]["author"] == prs[b]["author"]:
                continue
            kx, ky = set(x["keywords"]), set(y["keywords"])
            same_kw = x["area"] == y["area"] and len(kx & ky) >= 2 and jac(kx, ky) >= 0.5
            same_fix = bool(set(x["fixes"]) & set(y["fixes"]) - trackers)
            same_crash = x.get("crash_offset") and x["crash_offset"] == y.get("crash_offset")
            if same_kw or same_fix or same_crash:
                uf.join(a_, b)
                w = "same subject (AI keywords)" if same_kw else "same fixed issue (AI)" if same_fix else "same crash offset (AI)"
                why[a_].add(w)
                why[b].add(w)
    pr_groups = uf.groups()

    # Open PRs that redo something already merged (the most actionable case: the open one can simply be closed).
    merged = [n for n, p in prs.items() if p["status"] == "merged"]
    redo, redo_why = collections.defaultdict(set), collections.defaultdict(set)
    for o in open_prs:
        io = intents.get(f"pr:{o}")
        for m in merged:
            if prs[m]["author"] == prs[o]["author"]:
                continue                    # an author's own follow-up / stacked PRs are not redos
            reasons = []
            if fixes[o] & fixes[m]:
                reasons.append(f"both fix #{min(fixes[o] & fixes[m])}")
            if files[o] and files[m] and len(files[o]) <= 40 and jac(files[o], files[m]) >= 0.5 and jac(tw[o], tw[m]) >= 0.25:
                reasons.append("same files, similar title")
            im = intents.get(f"pr:{m}")
            if io and im and io["area"] == im["area"]:
                ko, km = set(io["keywords"]), set(im["keywords"])
                if len(ko & km) >= 2 and jac(ko, km) >= 0.5:
                    reasons.append("same subject (AI keywords)")
            if reasons:
                redo[o].add(m)
                redo_why[o].update(reasons)
    redo_groups = [[o] + sorted(ms) for o, ms in sorted(redo.items())]

    # Duplicate open issues.
    open_issues = [n for n, i in issues.items() if i["status"] == "open"]
    sig = {n: {s.lower() for s in CRASH.findall(issues[n]["body"] or "")}
              | ({intents[f"issue:{n}"]["crash_offset"]} if intents.get(f"issue:{n}", {}).get("crash_offset") else set())
           for n in open_issues}
    ikw = {n: set((intents.get(f"issue:{n}") or {}).get("keywords") or []) for n in open_issues}
    iar = {n: (intents.get(f"issue:{n}") or {}).get("area") for n in open_issues}
    iw = {n: words(issues[n]["title"]) for n in open_issues}
    uf2, why2 = UF(open_issues), collections.defaultdict(set)
    for k, a in enumerate(open_issues):
        for b in open_issues[k + 1:]:
            s = sig[a] & sig[b]
            if s:
                uf2.join(a, b)
                why2[a].add(f"same crash offset {min(s)}")
                why2[b].add(f"same crash offset {min(s)}")
            elif len(iw[a]) >= 3 and jac(iw[a], iw[b]) >= 0.5:
                uf2.join(a, b)
                why2[a].add("very similar title")
                why2[b].add("very similar title")
            elif iar[a] and iar[a] == iar[b] and len(ikw[a] & ikw[b]) >= 3 and jac(ikw[a], ikw[b]) >= 0.6:
                uf2.join(a, b)
                why2[a].add("same symptom (AI keywords)")
                why2[b].add("same symptom (AI keywords)")
    issue_groups = uf2.groups()

    fixed_by = collections.defaultdict(list)
    for n in open_prs:
        for i in fixes[n]:
            fixed_by[i].append(n)
    area = {n: area_of(prs[n]["title"], files[n]) for n in prs}
    iarea = {n: area_of(issues[n]["title"], ()) for n in issues}
    for n in prs:                                   # the AI area is better than the path-based one when known
        if intents.get(f"pr:{n}"):
            area[n] = intents[f"pr:{n}"]["area"]
    for n in issues:
        if intents.get(f"issue:{n}"):
            iarea[n] = intents[f"issue:{n}"]["area"]
    checks = {("pr", tuple(g)): verify.get(con, "pr", g) for g in pr_groups}
    checks.update({("merged", tuple(g)): verify.get(con, "merged", g) for g in redo_groups})
    checks.update({("issue", tuple(g)): verify.get(con, "issue", g) for g in issue_groups})
    return dict(prs=prs, issues=issues, files=files, open_prs=open_prs, open_issues=open_issues, fixes=fixes,
                pr_groups=pr_groups, pr_why=why, issue_groups=issue_groups, issue_why=why2, fixed_by=fixed_by,
                area=area, iarea=iarea, intents=intents, checks=checks, redo_groups=redo_groups, redo_why=redo_why)


def check(con):
    """Run the second AI check on candidate groups (outside the render lock: it can take minutes)."""
    from . import verify
    a = analyse(con)
    return verify.run(con, {"merged": a["redo_groups"], "pr": a["pr_groups"], "issue": a["issue_groups"]}, a["intents"])


def _verdicts(a, kind, g):
    c = a["checks"].get((kind, tuple(g)))
    if not c:
        return None
    return {"ai_check": c["summary_kind"], "verdicts": {str(m["number"]): m["verdict"] for m in c["members"]},
            "looks_most_complete": next((m["number"] for m in c["members"]
                                         if m.get("looks_most_complete", m.get("most_complete"))), None)}


def _intent(a, key):
    i = a["intents"].get(key)
    return {k: i[k] for k in ("area", "kind", "subject", "keywords")} if i else None


def write_api(a, out, campaigns_api):
    """Small static JSON files, one per question an agent asks: a few hundred bytes instead of a full digest."""
    global LAST_ANALYSIS
    LAST_ANALYSIS = a                                   # reused by agentapi (api/v2) in the same pass
    api = f"{out}/api"
    for d in ("prs", "issues", "areas"):
        os.makedirs(f"{api}/{d}", exist_ok=True)
    # A PR or issue that is no longer open loses its file (it used to keep saying "status": "open").
    keep = {"prs": {f"{n}.json" for n in a["open_prs"]}, "issues": {f"{n}.json" for n in a["open_issues"]}}
    for d, names in keep.items():
        for f in os.listdir(f"{api}/{d}"):
            if f.endswith(".json") and f not in names:
                os.remove(f"{api}/{d}/{f}")
    pr_group = {n: g for g in a["pr_groups"] for n in g}
    redo_m = {g[0]: g for g in a["redo_groups"]}
    is_group = {n: g for g in a["issue_groups"] for n in g}

    def dump(path, obj):
        with open(f"{api}/{path}", "w") as fh:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))

    for n in a["open_prs"]:
        g = pr_group.get(n, [])
        dump(f"prs/{n}.json", {"pr": n, "status": "open", "author": a["prs"][n]["author"], "area": a["area"][n],
                               "intent": _intent(a, f"pr:{n}"), "files": len(a["files"][n]),
                               "fixes": sorted(a["fixes"][n]),
                               "overlaps": [x for x in g if x != n],
                               "why": sorted(a["pr_why"][n]), "check": _verdicts(a, "pr", g) if g else None,
                               "redoes_merged": redo_m.get(n, [])[1:],
                               "redo_check": _verdicts(a, "merged", redo_m[n]) if n in redo_m else None,
                               "other_prs_fixing_same_issue": sorted({x for i in a["fixes"][n] for x in a["fixed_by"][i]} - {n})})
    for n in a["open_issues"]:
        g = is_group.get(n, [])
        dump(f"issues/{n}.json", {"issue": n, "area": a["iarea"][n], "intent": _intent(a, f"issue:{n}"),
                                  "duplicates": [x for x in g if x != n], "check": _verdicts(a, "issue", g) if g else None,
                                  "why": sorted(a["issue_why"][n]), "open_prs_fixing_it": sorted(a["fixed_by"].get(n, []))})
    by_area = collections.defaultdict(lambda: {"open_prs": [], "overlap_groups": 0})
    for n in a["open_prs"]:
        by_area[a["area"][n]]["open_prs"].append(n)
    for g in a["pr_groups"]:
        by_area[a["area"][g[0]]]["overlap_groups"] += 1
    for name, v in by_area.items():
        dump(f"areas/{name.replace('/', '__')}.json", {"area": name, "open_prs": sorted(v["open_prs"]),
                                                       "overlap_groups": v["overlap_groups"]})
    dump("duplicates.json", {
        "redo_merged": [{"open": g[0], "merged": g[1:], "why": sorted(a["redo_why"][g[0]]),
                         "check": _verdicts(a, "merged", g)} for g in a["redo_groups"]],
        "pr_groups": [{"members": g, "check": _verdicts(a, "pr", g)} for g in a["pr_groups"]],
        "issue_groups": [{"members": g, "check": _verdicts(a, "issue", g)} for g in a["issue_groups"]],
        "note": "check = second AI review of the group (null while pending). Candidates for a human, not verdicts."})
    by_file = collections.defaultdict(list)
    for n in a["open_prs"]:
        for f in a["files"][n]:
            by_file[f].append(n)
    dump("files.json", {f: sorted(v) for f, v in sorted(by_file.items())})
    dump("areas.json", sorted(({"area": k, "open_prs": len(v["open_prs"]), "overlap_groups": v["overlap_groups"]}
                               for k, v in by_area.items()), key=lambda x: -x["open_prs"]))
    dump("index.json", {
        "about": "Typed, read-only data about xcl-dev/xcl (formerly ivall/xcl), rebuilt every few minutes from public GitHub data. No prose, no instructions.",
        "endpoints": {
            "api/prs/<n>.json": "one open PR: area, AI intent, PRs it overlaps (with the AI check), merged PRs it seems to redo, issues it fixes",
            "api/issues/<n>.json": "one open issue: likely duplicates, open PRs that say they fix it",
            "api/duplicates.json": "all groups of overlapping open PRs and duplicate open issues",
            "api/files.json": "path -> open PRs touching it: before writing a change, see who already touches the same files",
            "api/areas.json": "open PRs and overlap groups per code area",
            "api/areas/<area>.json": "open PRs of one area ('/' written as '__')",
            "api/triage.json": "open PRs a maintainer could close first (reason + evidence per PR: redoes merged, duplicate, stale and failing the repo rules, off goal) and PRs ready to decide",
            **campaigns_api}})


def html(a, page, e):
    labels = {"duplicates": ("bad", "AI check: duplicates"), "partial-overlap": ("warn", "AI check: partial overlap"),
              "same-area-different-changes": ("mute", "AI check: same area, different changes"),
              "unrelated": ("mute", "AI check: unrelated"), None: ("mute", "AI check pending")}
    order = {"duplicates": 0, "partial-overlap": 1, None: 2, "same-area-different-changes": 3, "unrelated": 4}

    def table(groups, items, why, kind):
        o = []
        for g in sorted(groups, key=lambda g: order[(_verdicts(a, kind, g) or {}).get("ai_check")]):
            v = _verdicts(a, kind, g) or {}
            css, lab = labels[v.get("ai_check")]
            o.append(f"<h3 class='{css}' style='font-size:14px;margin:22px 0 4px'>{e(lab)} · {len(g)} {kind}s</h3>"
                     "<div class='scroll'><table class='tbl'><tr><th>#</th><th>Author</th><th>Opened</th><th>Title</th>"
                     "<th>AI subject</th><th>AI verdict</th><th>Why grouped</th></tr>")
            for n in sorted(g, key=lambda n: items[n]["created"]):
                p = items[n]
                it = a["intents"].get(f"{kind}:{n}") or {}
                vd = (v.get("verdicts") or {}).get(str(n), "")
                best = " · looks most complete (AI reading hint, not a ranking)" if v.get("looks_most_complete") == n else ""
                o.append(f'<tr><td><a href="{e(p["url"])}">#{n}</a></td><td>{e(p["author"])}</td><td>{e(p["created"][5:16].replace("T", " "))}</td>'
                         f'<td>{ft(p["title"])}</td><td class="small">{ft(it.get("subject", ""))}</td>'
                         f'<td class="{"bad" if vd == "same-change" else "warn" if vd == "partial-overlap" else "mute"}">{e(vd)}{e(best)}</td>'
                         f'<td class="small">{e("; ".join(sorted(why[n])))}</td></tr>')
            o.append("</table></div>")
        return "\n".join(o)

    def redo_table():
        rows = []
        for g in a["redo_groups"]:
            v = _verdicts(a, "merged", g) or {}
            vd = (v.get("verdicts") or {}).get(str(g[0]))
            if vd == "different":
                continue
            o = a["prs"][g[0]]
            merged_links = " ".join(f'<a href="{e(a["prs"][m]["url"])}">#{m}</a>' for m in g[1:])
            css = "bad" if vd == "same-change" else "warn" if vd == "partial-overlap" else "mute"
            rows.append((0 if vd == "same-change" else 1 if vd == "partial-overlap" else 2,
                         f'<tr><td><a href="{e(o["url"])}">#{g[0]}</a></td><td>{e(o["author"])}</td><td>{ft(o["title"])}</td>'
                         f'<td>{merged_links}</td><td class="{css}">{e(vd or "AI check pending")}</td>'
                         f'<td class="small">{e("; ".join(sorted(a["redo_why"][g[0]])))}</td></tr>'))
        if not rows:
            return ""
        rows.sort(key=lambda r: r[0])
        return ("<h2>Open PRs that seem to redo an already merged PR</h2><p class='mute'>The most actionable list: if the AI "
                "check says <i>same-change</i>, the open PR probably duplicates what is already in main. Members the AI judged "
                "<i>different</i> are left out.</p><div class='scroll'><table class='tbl'><tr><th>Open PR</th><th>Author</th>"
                "<th>Title</th><th>Already merged</th><th>AI check (reads diffs)</th><th>Why grouped</th></tr>"
                + "".join(r[1] for r in rows) + "</table></div><h2>Open PRs that overlap each other</h2>")

    known = sum(1 for n in a["open_prs"] if a["files"][n])
    pr_page = page("Duplicate and overlapping XCL pull requests · XCL board", "<p class='mute'><b>Overlapping PRs</b> · <a href='duplicate-issues.html'>Duplicate issues</a></p>" + f"<h1>Open PRs that overlap</h1><p class='mute'>{len(a['open_prs'])} open PRs, "
                   f"{known} with their file list so far, {sum(1 for n in a['open_prs'] if a['intents'].get(f'pr:{n}'))} with an AI intent card. "
                   f"{len(a['pr_groups'])} candidate groups: they say they fix the same issue, touch mostly the same files with similar titles, "
                   "or have the same subject according to the AI. A second AI (Sonnet) then reads each group and says which members make "
                   "the same change, reading their diffs. Candidates for a human to check; oldest first in each group, confirmed groups first.</p>"
                   + redo_table() + table(a["pr_groups"], a["prs"], a["pr_why"], "pr"), nav="dups", path="overlaps.html", crumb="Overlapping PRs",
                   description="Open XCL pull requests that overlap or redo a merged PR, grouped by files and issues and checked by "
                   "an AI that reads the diffs: avoid duplicate work.")
    is_page = page("Duplicate XCL issues (same crash, same symptom) · XCL board", "<p class='mute'><a href='overlaps.html'>Overlapping PRs</a> · <b>Duplicate issues</b></p>" + f"<h1>Open issues that are probably duplicates</h1><p class='mute'>{len(a['open_issues'])} open "
                   f"issues. {len(a['issue_groups'])} groups: same crash offset (xcl.exe+0x…), very similar titles, or the same symptom "
                   "according to the AI, then checked by a second AI. Candidates for a human to check.</p>" + table(a["issue_groups"], a["issues"], a["issue_why"], "issue"), nav="dups",
                   path="duplicate-issues.html", crumb="Duplicate issues",
                   description="Probable duplicate XCL issues (same xcl.exe+0x crash offset, similar title or symptom), checked by an "
                   "AI, so contributors can merge reports.")
    return pr_page, is_page


def run(con, out, page, e, campaigns_api):
    a = analyse(con)
    write_api(a, out, campaigns_api)
    from . import triage
    try:
        tri = triage.write(con, a, out)
    except Exception as ex:                         # the triage list never stops the other pages
        tri = {"error": repr(ex)[:200]}
    pr_page, is_page = html(a, page, e)
    with open(f"{out}/overlaps.html", "w") as fh:
        fh.write(pr_page)
    with open(f"{out}/duplicate-issues.html", "w") as fh:
        fh.write(is_page)
    return {"pr_groups": len(a["pr_groups"]), "issue_groups": len(a["issue_groups"]), "redo_merged": len(a["redo_groups"]),
            "open_prs": len(a["open_prs"]), "open_issues": len(a["open_issues"]), "triage": tri}
