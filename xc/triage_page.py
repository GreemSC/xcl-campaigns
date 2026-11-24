"""triage.html: open pull requests a maintainer could close first, and those ready to decide, from api/triage.json
(xc/triage.py). Numbers, logins, enums and links only: no PR title or other free text written by people or an AI."""
import json

STRONG = ["duplicate-checked", "redoes-merged", "duplicate-open", "rules-stale"]          # strongest first; then off-goal, then waiting
SHORT = {"duplicate-checked": "duplicate checked by two contributors", "redoes-merged": "redoes a merged PR", "duplicate-open": "duplicate of an open PR",
         "rules-stale": "failing the repo rules for over a week", "ai-off-goal": "off goal (AI reading)", "off-goal": "off goal (AI reading)",
         "rules-failing": "failing the repo rules (waits for the author)"}
TOUCH_TXT = {"wall": "what stops the title today", "reached-stage": "a stage testers reach", "campaign": "a campaign task",
             "general": "general", "no-runtime-change": "no runtime change"}
EVID_TXT = {"retail-shows-effect": "a retail run shows the effect", "retail-regression-only": "a retail run, no regression only",
            "other-run": "another run", "tests-only": "tests only", "none": "none"}
CHECK_CSS = {"success": "ok", "failure": "bad", "pending": "warn"}


def _pr(e, url, n):
    return f'<a href="{e(url(n))}">#{n}</a>'


def proof(e, url, x):
    """The evidence behind one reason, as short facts with links."""
    r = x["reason"]
    if r == "duplicate-checked":
        return (f'keep {_pr(e, url, x["keep"])} · unit {e(x.get("unit") or "?")} of '
                f'<a href="https://github.com/xcl-dev/xcl/issues/1607">#1607</a>') if x.get("keep") else ""
    if r == "redoes-merged":
        return "same change as merged " + ", ".join(_pr(e, url, m) for m in x.get("merged", []))
    if r == "duplicate-open":
        return f'same change as {_pr(e, url, x["keep"])}, which looks more complete or is older' if x.get("keep") else ""
    if r in ("rules-stale", "rules-failing"):
        f = [{"ci": "CI fails", "pr_checks": "PR checks fail"}.get(k, e(k)) for k in x.get("failing", [])]
        if x.get("conflicts"):
            f.append("conflicts with main")
        if x.get("last_commit_days") is not None:
            d = x["last_commit_days"]
            f.append(f'last commit {d} day{"s" if d != 1 else ""} ago')
        return ", ".join(f)
    if r in ("ai-off-goal", "off-goal"):
        return (f'touches: {e(TOUCH_TXT.get(x.get("touches"), x.get("touches") or "?"))}; '
                f'evidence: {e(EVID_TXT.get(x.get("evidence"), x.get("evidence") or "?"))}; second model agrees')
    return ""


def checks(e, c):
    if not c:
        return '<span class="mute">not read yet</span>'
    o = []
    for k, lab in (("ci", "CI"), ("pr_checks", "PR checks")):
        o.append(f'<span class="{CHECK_CSS.get(c[k], "mute")}">{lab}: {e(c[k])}</span>')
    o.append(f'<span class="{"bad" if c["mergeable"] == "CONFLICTING" else "ok" if c["mergeable"] == "MERGEABLE" else "mute"}">'
             f'{e(c["mergeable"].lower())}</span>')
    if c.get("draft"):
        o.append('<span class="mute">draft</span>')
    return " · ".join(o)


def reports(e, tr):
    """Test reports by other people posted after the last commit (a checked #1607 batch counts as one)."""
    if not tr or not tr.get("count"):
        return '<span class="mute">none</span>'
    ppl = tr.get("people") or []
    who = ", ".join(e(x) for x in ppl[:5]) + (f" and {len(ppl) - 5} more" if len(ppl) > 5 else "")
    batch = (f' + batch {e(tr["batch_1607"])} of <a href="https://github.com/xcl-dev/xcl/issues/1607">#1607</a>'
             if tr.get("batch_1607") else "")
    return f'<b>{tr["count"]}</b> <span class="small">{who}{batch}</span>'


def table(e, url, rows, with_reasons=True):
    o = ['<div class="scroll"><table class="tbl"><tr><th>PR</th><th>Author</th><th>Area</th><th>Opened</th>'
         + ('<th>Why</th>' if with_reasons else '<th>Test reports on the last commit</th>') + '<th>Checks</th></tr>']
    for p in rows:
        why = ("<td><ul class='why'>" + "".join(f'<li><b>{e(SHORT.get(x["reason"], x["reason"]))}</b>'
                                                f'<span class="small"> · {proof(e, url, x)}</span></li>'
                                                for x in p["closable"]) + "</ul></td>") if with_reasons \
            else f'<td>{reports(e, p.get("test_reports_on_head"))}</td>'
        labs = "".join(f'<span class="chip">{e(x)}</span>' for x in p.get("labels_on_github") or [])
        o.append(f'<tr id="pr{p["pr"]}"><td>{_pr(e, url, p["pr"])}{"<br>" + labs if labs else ""}</td><td>{e(p["author"])}</td>'
                 f'<td class="small">{e(p.get("area") or "")}</td><td class="small nw">{e((p.get("created") or "")[:10])}</td>'
                 f'{why}<td class="small">{checks(e, p.get("checks"))}</td></tr>')
    o.append("</table></div>")
    return "\n".join(o)


FIRST = ["off-goal-but-runtime", "off-goal-but-goal-issue"]     # contradict the label's own rule: shown first
REPO = "https://github.com/xcl-dev/xcl"


def label_check(t, e, url):
    """The maintainer's labels (#1833) against what the board reads: a second look, one list per check."""
    prs = t["prs"]
    on = t.get("labels_on_github_counts") or {}
    o = ['<h2 id="labels">Label check (second look)</h2>',
         f'<p class="mute">Labels are set on GitHub by the maintainers, by script from titles and paths '
         f'(<a href="{REPO}/issues/1833">#1833</a>), and they asked for a second look. This compares them with what the '
         f'board reads: a second look, never a verdict. On GitHub now: '
         + ", ".join(f'<span class="chip">{e(k)}</span> {v}' for k, v in on.items())
         + f'. What can be closed is reported on <a href="{REPO}/issues/1607">#1607</a>.</p>']
    ids = FIRST + [k for k in t["label_why"] if k not in FIRST]
    for k in ids:
        rows = [p for p in prs if k in (p.get("label_check") or [])]
        head = (f'<b>{e(k)}</b> <span class="mute">· {len(rows)} PR{"s" if len(rows) != 1 else ""} · '
                f'{e(t["label_why"].get(k, ""))}</span>')
        if not rows:
            o.append(f'<p class="small">{head}</p>')
            continue
        body = ['<div class="scroll"><table class="tbl"><tr><th>PR</th><th>Labels on GitHub</th><th class="num">Runtime files</th>'
                '<th>Author</th><th>Area</th></tr>']
        for p in sorted(rows, key=lambda p: p["pr"]):
            labs = "".join(f'<span class="chip">{e(x)}</span>' for x in p.get("labels_on_github") or []) or '<span class="mute">none</span>'
            body.append(f'<tr><td>{_pr(e, url, p["pr"])}</td><td>{labs}</td><td class="num">{p.get("runtime_files", "")}</td>'
                        f'<td>{e(p["author"])}</td><td class="small">{e(p.get("area") or "")}</td></tr>')
        body.append('</table></div>')
        o.append(f'<details{" open" if k in FIRST or len(rows) <= 10 else ""}><summary>{head}</summary>{"".join(body)}</details>')
    return "\n".join(o)


def html(t, page, e, url):
    prs = t["prs"]
    rank = {r: i for i, r in enumerate(STRONG)}
    strong = sorted([p for p in prs if any(x["reason"] in rank for x in p["closable"])],
                    key=lambda p: (min(rank.get(x["reason"], 9) for x in p["closable"]), p["pr"]))
    offgoal = [p for p in prs if p not in strong and any(x["reason"] in ("ai-off-goal", "off-goal") for x in p["closable"])]
    waiting = [p for p in prs if p["closable"] and all(x["reason"] == "rules-failing" for x in p["closable"])]
    ready = sorted([p for p in prs if p["ready_to_decide"]],     # the current wall first, then the most tested
                   key=lambda p: ("goal:world-load" not in (p.get("labels_on_github") or []),
                                  -((p.get("test_reports_on_head") or {}).get("count") or 0), p["pr"]))
    c = t["counts"]
    nlab = sum(1 for p in prs if p.get("label_check"))
    o = ['<h1>Open pull requests: triage</h1>',
         f'<p class="lede"><b>This page closes nothing and writes nothing on GitHub.</b> These are candidates for a maintainer, '
         'not verdicts. Each line gives its reason and the evidence, with links: check them before acting.</p>',
         '<div class="kpis">' + "".join(f'<div class="kpi"><b>{v}</b>{e(k)}</div>' for k, v in [
             ("open PRs", t["open_prs"]), ("labels to look at again", nlab), ("could close first", len(strong)), ("off goal (AI reading)", len(offgoal)),
             ("wait for their author", len(waiting)), ("ready to decide", len(ready)),
             ("PRs read by the AI so far", f'{t["ai_cards"]}/{t["open_prs"]}')]) + "</div>",
         f'<p class="small mute">Checks and conflicts read from GitHub {e((t.get("status_read_at") or "?")[:16].replace("T", " "))} UTC. '
         f'Machine-readable: <a href="api/triage.json">api/triage.json</a>.</p>']

    if t.get("label_why"):
        o.append(label_check(t, e, url))
    o.append('<h2 id="close">Could close first</h2><p class="mute">Strongest reason first: '
             + " &gt; ".join(f'<abbr title="{e(t["reasons"].get(r, ""))}">{e(SHORT[r])}</abbr> ({c.get(r, 0)})' for r in STRONG)
             + '. The rules are the repository\'s own (CONTRIBUTING); duplicates come from two contributors on #1607 or from an AI reading the diffs.</p>')
    o.append(table(e, url, strong) if strong else '<p class="mute">None right now.</p>')

    o.append(f'<h2 id="off-goal">Off goal, according to the AI</h2><p class="mute">{e(t["reasons"].get("ai-off-goal") or t["reasons"].get("off-goal", ""))}. '
             'Shown apart: an AI reading, not a fact.</p>')
    o.append(table(e, url, offgoal) if offgoal else '<p class="mute">None right now.</p>')

    rule = t.get("ready_rule") or ("PR checks green, CI not failing, no conflict with main, not a draft, no reason "
                                   "above, and test reports from at least two other people after its last commit "
                                   "(a checked #1607 batch counts as one); goal:world-load first, then the most tested")
    o.append(f'<h2 id="ready">Ready to decide</h2><p class="mute">{e(rule[0].upper() + rule[1:])}. A maintainer can '
             'merge or refuse these now; the board does not say which.</p>')
    if not ready:
        o.append('<p class="mute">None yet.</p>')
    elif len(ready) > 40:
        o.append(table(e, url, ready[:40], with_reasons=False)
                 + f'<details><summary>{len(ready) - 40} more</summary>' + table(e, url, ready[40:], with_reasons=False) + '</details>')
    else:
        o.append(table(e, url, ready, with_reasons=False))

    o.append(f'<h2 id="waiting">Waiting for their author</h2><p class="mute">{e(t["reasons"].get("rules-failing", ""))}. '
             'Not a reason to close: the author can fix it.</p>')
    if waiting:
        o.append(f'<details><summary>{len(waiting)} PRs</summary>' + table(e, url, waiting) + '</details>')
    else:
        o.append('<p class="mute">None right now.</p>')

    if t["ai_cards"]:
        o.append('<h2 id="ai">What the AI read</h2><div class="cols"><div><h3>Touches</h3><table class="tbl">'
                 + "".join(f'<tr><td>{e(TOUCH_TXT.get(k, k))}</td><td class="num">{v}</td></tr>' for k, v in t["by_touches"].items())
                 + '</table></div><div><h3>Evidence in the PR</h3><table class="tbl">'
                 + "".join(f'<tr><td>{e(EVID_TXT.get(k, k))}</td><td class="num">{v}</td></tr>' for k, v in t["by_evidence"].items())
                 + '</table></div></div>')
    return page("Open XCL pull requests to triage · XCL board", "\n".join(o), "api/triage.json", nav="triage",
                path="triage.html", crumb="PR triage",
                description="Open XCL pull requests a maintainer could close first (redo a merged PR, duplicate, failing "
                            "the repo rules) and those ready to decide, each with its evidence. Candidates, not verdicts.")


CSS = ".why{margin:0;padding-left:16px}.why li{margin:2px 0}.tbl td.nw,.tbl code{white-space:nowrap}abbr{text-decoration:underline dotted}"


def write(out, page, e, url):
    with open(f"{out}/api/triage.json") as fh:
        t = json.load(fh)
    with open(f"{out}/triage.html", "w") as fh:
        fh.write(html(t, page, e, url))
    return {"close_first": sum(1 for p in t["prs"] if any(x["reason"] in STRONG for x in p["closable"])),
            "ready": sum(1 for p in t["prs"] if p["ready_to_decide"])}
