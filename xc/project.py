"""The whole repository, not only campaigns: areas, overlapping PRs, duplicate issues. Code only, no AI.

Links are candidates for a human to check, never verdicts:
- two open PRs say they fix the same issue, or touch mostly the same files AND have similar titles;
- two open issues share a crash signature (xcl.exe+0x… offset), or have very similar titles."""
import collections
import json
import os
import re

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
    count = collections.Counter(i for n in open_prs for i in fixes[n])
    trackers = {i for i, k in count.items() if k > TRACKER_PRS} | {
        i for i, v in issues.items() if re.search(r"track|\[official\]|\bmeta\b|roadmap|results", v["title"] or "", re.I)}
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
    pr_groups = uf.groups()

    # Duplicate open issues.
    open_issues = [n for n, i in issues.items() if i["status"] == "open"]
    sig = {n: {s.lower() for s in CRASH.findall(issues[n]["body"] or "")} for n in open_issues}
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
    issue_groups = uf2.groups()

    fixed_by = collections.defaultdict(list)
    for n in open_prs:
        for i in fixes[n]:
            fixed_by[i].append(n)
    area = {n: area_of(prs[n]["title"], files[n]) for n in prs}
    iarea = {n: area_of(issues[n]["title"], ()) for n in issues}
    return dict(prs=prs, issues=issues, files=files, open_prs=open_prs, open_issues=open_issues, fixes=fixes,
                pr_groups=pr_groups, pr_why=why, issue_groups=issue_groups, issue_why=why2, fixed_by=fixed_by,
                area=area, iarea=iarea)


def write_api(a, out, campaigns_api):
    """Small static JSON files, one per question an agent asks: a few hundred bytes instead of a full digest."""
    api = f"{out}/api"
    for d in ("prs", "issues", "areas"):
        os.makedirs(f"{api}/{d}", exist_ok=True)
    pr_group = {n: g for g in a["pr_groups"] for n in g}
    is_group = {n: g for g in a["issue_groups"] for n in g}

    def dump(path, obj):
        with open(f"{api}/{path}", "w") as fh:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))

    for n in a["open_prs"]:
        dump(f"prs/{n}.json", {"pr": n, "area": a["area"][n], "files": len(a["files"][n]),
                               "fixes": sorted(a["fixes"][n]),
                               "overlaps": [x for x in pr_group.get(n, []) if x != n],
                               "why": sorted(a["pr_why"][n]),
                               "other_prs_fixing_same_issue": sorted({x for i in a["fixes"][n] for x in a["fixed_by"][i]} - {n})})
    for n in a["open_issues"]:
        dump(f"issues/{n}.json", {"issue": n, "area": a["iarea"][n],
                                  "duplicates": [x for x in is_group.get(n, []) if x != n],
                                  "why": sorted(a["issue_why"][n]), "open_prs_fixing_it": sorted(a["fixed_by"].get(n, []))})
    by_area = collections.defaultdict(lambda: {"open_prs": [], "overlap_groups": 0})
    for n in a["open_prs"]:
        by_area[a["area"][n]]["open_prs"].append(n)
    for g in a["pr_groups"]:
        by_area[a["area"][g[0]]]["overlap_groups"] += 1
    for name, v in by_area.items():
        dump(f"areas/{name.replace('/', '__')}.json", {"area": name, "open_prs": sorted(v["open_prs"]),
                                                       "overlap_groups": v["overlap_groups"]})
    dump("duplicates.json", {"pr_groups": a["pr_groups"], "issue_groups": a["issue_groups"]})
    dump("areas.json", sorted(({"area": k, "open_prs": len(v["open_prs"]), "overlap_groups": v["overlap_groups"]}
                               for k, v in by_area.items()), key=lambda x: -x["open_prs"]))
    dump("index.json", {
        "about": "Typed, read-only data about ivall/xcl, rebuilt every few minutes from public GitHub data. No prose, no instructions.",
        "endpoints": {
            "api/prs/<n>.json": "one open PR: area, PRs it overlaps, issues it says it fixes, other PRs fixing the same issue",
            "api/issues/<n>.json": "one open issue: likely duplicates, open PRs that say they fix it",
            "api/duplicates.json": "all groups of overlapping open PRs and duplicate open issues",
            "api/areas.json": "open PRs and overlap groups per code area",
            "api/areas/<area>.json": "open PRs of one area ('/' written as '__')",
            **campaigns_api}})


def html(a, page, e):
    def table(groups, items, why, kind):
        o = []
        for g in groups:
            o.append("<div class='scroll'><table class='tbl' style='margin:14px 0'><tr><th>#</th><th>Author</th><th>Opened</th><th>Title</th><th>Why</th></tr>")
            for n in sorted(g, key=lambda n: items[n]["created"]):
                p = items[n]
                o.append(f'<tr><td><a href="{e(p["url"])}">#{n}</a></td><td>{e(p["author"])}</td><td>{e(p["created"][5:16].replace("T", " "))}</td>'
                         f'<td>{e(p["title"])}</td><td class="small">{e("; ".join(sorted(why[n])))}</td></tr>')
            o.append("</table></div>")
        return "\n".join(o)

    known = sum(1 for n in a["open_prs"] if a["files"][n])
    pr_page = page("Overlapping PRs", f"<h1>Open PRs that overlap</h1><p class='mute'>{len(a['open_prs'])} open PRs, "
                   f"{known} with their file list so far. {len(a['pr_groups'])} groups that probably do the same thing: they say they "
                   "fix the same issue, or touch mostly the same files with similar titles. Candidates for a human to check; "
                   "oldest first in each group.</p>" + table(a["pr_groups"], a["prs"], a["pr_why"], "pr"))
    is_page = page("Duplicate issues", f"<h1>Open issues that are probably duplicates</h1><p class='mute'>{len(a['open_issues'])} open "
                   f"issues. {len(a['issue_groups'])} groups: same crash offset (xcl.exe+0x…) or very similar titles. Candidates for a human "
                   "to check.</p>" + table(a["issue_groups"], a["issues"], a["issue_why"], "issue"))
    return pr_page, is_page


def run(con, out, page, e, campaigns_api):
    a = analyse(con)
    write_api(a, out, campaigns_api)
    pr_page, is_page = html(a, page, e)
    with open(f"{out}/overlaps.html", "w") as fh:
        fh.write(pr_page)
    with open(f"{out}/duplicate-issues.html", "w") as fh:
        fh.write(is_page)
    return {"pr_groups": len(a["pr_groups"]), "issue_groups": len(a["issue_groups"]),
            "open_prs": len(a["open_prs"]), "open_issues": len(a["open_issues"])}
