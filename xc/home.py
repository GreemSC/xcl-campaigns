"""The human front page (index.html) and the reports page (reports.html): how far the game gets, what changed,
where the project is, how to help. Computed by code from the database; text written by people on GitHub (PR and
issue titles) is shown escaped, as data; nothing on these pages is written by an AI."""
import collections
import datetime as dt
import json
import os
import re

from . import progress as P

CONFIRM = int(os.environ.get("XC_CONFIRM_PEOPLE", "2"))     # people needed to call a stage "confirmed"
RECENT_DAYS = int(os.environ.get("XC_RECENT_DAYS", "7"))
REPO_URL = "https://github.com/" + os.environ.get("XC_REPO", "xcl-dev/xcl")
STAGE_NAME = {i: n for i, n, _ in P.STAGES}
STAGE_DESC = {i: d for i, _, d in P.STAGES}
END_TXT = {"stalls": "then stalls", "crashes": "then crashes", "exits": "then the game quits",
           "keeps_running": "and keeps running", "stopped_by_user": "run stopped by the tester", "unknown": ""}
AREA = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ./+_-]{1,22}):\s")

CSS = """
.hero{padding:28px 0 8px}.kicker{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 6px}
.hero h1{font-size:clamp(26px,5vw,40px);line-height:1.15;margin:0 0 10px}.answer{font-size:clamp(18px,3vw,23px);margin:0 0 10px}
.answer b{color:var(--warn)}.lede{max-width:760px;color:var(--mute);margin:0}
.ladder{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin:22px 0 6px}
.step{position:relative;padding:10px 8px 8px;border-radius:6px;background:var(--chip);font-size:13px;line-height:1.25;min-height:58px}
.step small{display:block;color:var(--mute);font-size:11px;margin-top:3px}
.step.done{background:var(--ok);color:var(--bg)}.step.done small{color:var(--bg);opacity:.85}
.step.once{background:repeating-linear-gradient(135deg,var(--chip) 0 6px,var(--hi) 6px 12px);outline:1px dashed var(--warn)}
.legend{font-size:12px;color:var(--mute);display:flex;gap:16px;flex-wrap:wrap}.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;margin-right:5px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card h3{margin:0 0 6px;font-size:16px}.card p{margin:6px 0;font-size:14px}
.mini{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin:8px 0}.mini span{height:8px;border-radius:2px;background:var(--chip)}
.mini span.done{background:var(--ok)}.mini span.once{background:var(--warn)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px}
.feed{list-style:none;padding:0;margin:0}.feed li{padding:8px 0;border-bottom:1px solid var(--line);font-size:14px}
.feed .meta{font-size:12px;color:var(--mute)}.area{display:inline-block;font-size:11px;padding:0 6px;border-radius:8px;background:var(--chip);color:var(--mute);margin-right:4px}
.areas{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}.areas button{font:inherit;font-size:12px;padding:2px 9px;border-radius:12px;
 border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}.areas button[aria-pressed=true]{border-color:var(--ok);color:var(--ok);font-weight:600}
.chart{width:100%;height:auto;display:block}.chart text{fill:var(--mute);font-size:10px}.chart rect{fill:var(--ok)}
.help a.card{display:block;text-decoration:none;color:var(--fg)}.help a.card:hover{border-color:var(--ok)}.help .card b{color:var(--ok)}
.note{font-size:12.5px;color:var(--mute)}
.stages{display:flex;flex-direction:column;gap:8px;margin:10px 0}.stage{display:grid;grid-template-columns:220px 1fr 1.3fr;gap:6px 16px;
 background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:8px;padding:10px 14px;font-size:14px}
.stage.done{border-left-color:var(--ok)}.stage.once{border-left-color:var(--warn)}.stage.todo{opacity:.7}
.sname small{display:block;color:var(--mute);font-size:12px}blockquote{margin:0 0 6px;font-style:italic;color:var(--fg)}
blockquote cite{display:block;font-style:normal;font-size:11.5px;color:var(--mute)}
@media (max-width:820px){.stage{grid-template-columns:1fr}}.quote{font-size:13px;color:var(--mute);font-style:italic;margin-top:2px}
@media (max-width:640px){.ladder{grid-template-columns:repeat(4,1fr)}}
"""


def _iso(d):
    return dt.datetime.fromisoformat(d.replace("Z", "+00:00"))


def _now():
    return dt.datetime.now(dt.timezone.utc)


def ago(e, iso):
    """A date the page script turns into "3 h ago"; the static text stays meaningful without the script."""
    return f'<time class="ago" datetime="{e(iso)}">{e(iso[5:16].replace("T", " "))} UTC</time>'


def area_of(title):
    m = AREA.match(title or "")
    return m.group(1).strip() if m else "Other"


def ladder_state(reps):
    """Per platform and overall: the furthest stage reached by CONFIRM+ people, and by at least one."""
    recent = [r for r in reps if (_now() - _iso(r["date"])).days < RECENT_DAYS]
    people = collections.defaultdict(set)              # (platform, rank) -> authors who reached at least it
    for r in recent:
        for k in range(r["rank"] + 1):
            people[(r["platform"], k)].add(r["author"])
            people[("all", k)].add(r["author"])
    out = {}
    for p in [x for x, _ in P.PLATFORMS] + ["all"]:
        conf = max([k for k in range(len(P.STAGES)) if len(people[(p, k)]) >= CONFIRM], default=-1)
        once = max([k for k in range(len(P.STAGES)) if people[(p, k)]], default=-1)
        mine = [r for r in recent if p == "all" or r["platform"] == p]
        top = [r for r in mine if r["rank"] == once]
        secs = sorted(r["at_seconds"] for r in top if r.get("at_seconds"))
        ends = collections.Counter(r["ended"] for r in top if r["ended"] != "unknown")
        out[p] = {"confirmed": conf, "once": once, "people": {k: len(people[(p, k)]) for k in range(len(P.STAGES))},
                  "reports": len(mine), "latest": mine[0] if mine else None, "top": top,
                  "median_end_s": secs[len(secs) // 2] if secs else None,
                  "usual_end": ends.most_common(1)[0][0] if ends else None}
    return out


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def stage_stats(reps):
    """For each stage: the recent runs that ended there, their frame rate, how they ended, what people saw."""
    recent = [r for r in reps if (_now() - _iso(r["date"])).days < RECENT_DAYS]
    out = {}
    for k in range(len(P.STAGES)):
        here = [r for r in recent if r["rank"] == k]
        fps = [r["fps"] for r in here if r.get("fps")]
        ends = collections.Counter(r["ended"] for r in here if r["ended"] != "unknown")
        quotes, seen = [], set()
        for r in here:                                   # newest first, one quote per person
            if r.get("screen_quote") and r["author"] not in seen:
                seen.add(r["author"])
                quotes.append(r)
        out[k] = {"runs": len(here), "people": len({r["author"] for r in here}), "fps": _median(fps), "fps_n": len(fps),
                  "end_s": _median([r["at_seconds"] for r in here if r.get("at_seconds")]),
                  "usual_end": ends.most_common(1)[0][0] if ends else None, "quotes": quotes[:2]}
    return out


def html_stages(e, ss, a):
    """What each stage looks like, from the people who stopped there."""
    last = max([k for k in ss if ss[k]["runs"]] + [a["once"], 0])
    o = ['<h2 id="stages">What you see at each stage</h2><p class="mute">From the runs that stopped at each stage '
         f'(last {RECENT_DAYS} days). Quotes are copied word for word from the testers\' comments; click to read them.</p>'
         '<div class="stages">']
    for k, (sid, name, desc) in enumerate(P.STAGES):
        if k > last + 1:
            break
        s = ss[k]
        facts = []
        if s["runs"]:
            facts.append(f'{s["runs"]} run{"s" if s["runs"] > 1 else ""} stopped here ({s["people"]} '
                         f'{"person" if s["people"] == 1 else "people"})')
        if s["fps"] is not None:
            facts.append(f'<b>~{s["fps"]:g} fps</b> <span class="mute">({s["fps_n"]} report{"s" if s["fps_n"] > 1 else ""})</span>')
        if s["usual_end"] and END_TXT.get(s["usual_end"]):
            facts.append("usually " + e(END_TXT[s["usual_end"]].replace("then ", "")) +
                         (f' around {s["end_s"]:g} s' if s["end_s"] else ""))
        quotes = "".join(f'<blockquote>“{e(r["screen_quote"])}”<cite><a href="{e(r["source"])}">{e(r["author"])}</a>'
                         f'{", " + e(r["gpu"]) if r.get("gpu") else ""}</cite></blockquote>' for r in s["quotes"])
        state = "done" if k <= a["confirmed"] else "once" if k <= a["once"] else "todo"
        o.append(f'<div class="stage {state}"><div class="sname"><b>{e(name)}</b><small>{e(desc)}</small></div>'
                 f'<div class="sfacts">{" · ".join(facts) or "<span class=mute>nobody has reported this yet</span>"}</div>'
                 f'<div class="squotes">{quotes}</div></div>')
    o.append("</div>")
    return "\n".join(o)


def overview(con):
    """Project pulse, computed from the collected GitHub data."""
    now = _now()
    day = (now - dt.timedelta(hours=24)).isoformat(timespec="seconds").replace("+00:00", "Z")
    merged = [dict(r) for r in con.execute("""SELECT number, author, merged, title, url FROM items
                                              WHERE kind='pr' AND status='merged' AND merged IS NOT NULL ORDER BY merged DESC""")]
    per_day = collections.Counter(m["merged"][:10] for m in merged)
    days = [(now - dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    first = con.execute("SELECT min(created) FROM items").fetchone()[0] or ""
    hot = con.execute("""SELECT c.number, count(DISTINCT c.author) people, count(*) msgs, i.title, i.url
                         FROM items c JOIN items i ON i.kind='issue' AND i.number=c.number AND i.status='open'
                         WHERE c.kind='comment' AND c.created > ? GROUP BY c.number ORDER BY people DESC, msgs DESC LIMIT 6""",
                      (day,)).fetchall()
    count = lambda q, *a: con.execute(q, a).fetchone()[0]
    return {
        "since": first,
        "merged_24h": sum(1 for m in merged if m["merged"] > day),
        "open_prs": count("SELECT count(*) FROM items WHERE kind='pr' AND status='open'"),
        "open_issues": count("SELECT count(*) FROM items WHERE kind='issue' AND status='open'"),
        "people_24h": count("SELECT count(DISTINCT author) FROM items WHERE created > ?", day),
        "merged_per_day": [{"day": d, "merged": per_day.get(d, 0)} for d in days if d >= first[:10]],
        "latest_merged": [{**m, "area": area_of(m["title"])} for m in merged[:150]],
        "hot_issues": [dict(r) for r in hot],
    }


def svg_bars(e, rows):
    if not rows:
        return ""
    w, h, pad = 640, 150, 18
    top = max(r["merged"] for r in rows) or 1
    bw = min((w - 10) / len(rows), 56)
    x0 = (w - bw * len(rows)) / 2
    o = [f'<svg class="chart" viewBox="0 0 {w} {h + pad + 14}" role="img" aria-label="Pull requests merged per day">']
    for i, r in enumerate(rows):
        bh = h * r["merged"] / top
        x = x0 + i * bw
        o.append(f'<rect x="{x + 3:.1f}" y="{pad + h - bh:.1f}" width="{bw - 6:.1f}" height="{bh:.1f}" rx="2"><title>{e(r["day"])}: '
                 f'{r["merged"]} merged</title></rect><text x="{x + bw / 2:.1f}" y="{pad + h - bh - 4:.1f}" text-anchor="middle">'
                 f'{r["merged"] or ""}</text><text x="{x + bw / 2:.1f}" y="{pad + h + 13:.1f}" text-anchor="middle">{e(r["day"][5:])}</text>')
    o.append("</svg>")
    return "".join(o)


def describe(r, e):
    """One factual line composed from typed fields only."""
    bits = [f'<b>{e(STAGE_NAME[r["stage"]])}</b>']
    if END_TXT.get(r["ended"]):
        bits.append(e(END_TXT[r["ended"]]) + (f' at {r["at_seconds"]:g} s' if r.get("at_seconds") else ""))
    if r.get("fps"):
        bits.append(f'({r["fps"]:g} fps)')
    if r.get("screen_quote"):         # verbatim from the author's comment, checked by code
        bits.append(f'<div class="quote">“{e(r["screen_quote"])}”</div>')
    return " ".join(bits)


def html_home(e, st, ov, reps, camps):
    pnames = dict(P.PLATFORMS)
    ss = stage_stats(reps)
    a = st["all"]
    o = []
    # 1. The answer
    if a["once"] < 0:
        answer = "No first-hand report filed yet."
    else:
        played = a["confirmed"] >= P.STAGE_IDS.index("playable")
        answer = ("<b>Yes</b>, people report playing it." if played else
                  f'<b>Not playable yet.</b> Furthest point reached by {a["people"][a["confirmed"]]} people: '
                  f'<b>{e(STAGE_NAME[P.STAGE_IDS[a["confirmed"]]])}</b>' if a["confirmed"] >= 0 else "<b>Not playable yet.</b>")
        if a["once"] > a["confirmed"]:
            answer += (f'; reported once: <b>{e(STAGE_NAME[P.STAGE_IDS[a["once"]]])}</b>')
        answer += "."
    o.append(f"""<section class="hero" id="status"><p class="kicker">Community board for the XCL project</p>
<h1>Does GTA VI run with XCL yet?</h1><p class="answer">{answer}</p>
<p class="lede">XCL recompiles the Xbox Series build of the game so it runs on a PC: Windows, and Linux through Wine or Proton.
This page sums up what testers and developers report on <a href="{REPO_URL}">GitHub</a>, every few minutes, with a link to
each source. It hosts no game files and no downloads.</p></section>""")
    # 2. The ladder
    o.append('<div class="ladder" aria-label="How far the game gets">')
    for k, (sid, name, desc) in enumerate(P.STAGES):
        cls = "done" if k <= a["confirmed"] else "once" if k <= a["once"] else ""
        fps = f' · ~{ss[k]["fps"]:g} fps' if ss[k]["fps"] is not None else ""
        o.append(f'<div class="step {cls}" title="{e(desc)}">{e(name)}<small>{a["people"].get(k, 0)} people{fps}</small></div>')
    o.append(f'</div><div class="legend"><span><i style="background:var(--ok)"></i>reached by {CONFIRM}+ people</span>'
             '<span><i style="background:var(--warn)"></i>reported by one person</span>'
             f'<span>Reports of the last {RECENT_DAYS} days. <a href="reports.html">All reports →</a></span></div>')
    o.append(html_stages(e, ss, a))
    # 3. Per platform
    o.append('<h2 id="platforms">By platform</h2><div class="cards">')
    for pid, pname in P.PLATFORMS:
        s = st[pid]
        mini = "".join(f'<span class="{"done" if k <= s["confirmed"] else "once" if k <= s["once"] else ""}"></span>'
                       for k in range(len(P.STAGES)))
        if s["once"] < 0:
            body = '<p class="mute">No report yet. Tried it on this platform? Tell the project on GitHub.</p>'
        else:
            far = P.STAGE_IDS[s["once"]]
            end = (f' {e(END_TXT[s["usual_end"]])}' if s.get("usual_end") and END_TXT.get(s["usual_end"]) else "")
            end += f' (median {s["median_end_s"]:g} s)' if s.get("median_end_s") else ""
            lt = s["latest"]
            body = (f'<p>Furthest: <b>{e(STAGE_NAME[far])}</b>{end}</p>'
                    f'<p class="note">{s["people"][s["once"]]} {"person" if s["people"][s["once"]] == 1 else "people"} there · '
                    f'{s["reports"]} reports · latest <a href="{e(lt["source"])}">{ago(e, lt["date"])}</a> by {e(lt["author"])}</p>')
        o.append(f'<div class="card"><h3>{e(pname)}</h3><div class="mini">{mini}</div>{body}'
                 f'<p class="note"><a href="reports.html#{pid}">reports →</a></p></div>')
    o.append("</div>")
    # 4. What's new
    o.append('<h2 id="news">What\'s new</h2><div class="cols"><div>')
    lm = ov["latest_merged"]
    areas = collections.Counter(m["area"] for m in lm[:60])
    o.append(f'<h3>Merged into XCL <span class="mute">· {ov["merged_24h"]} changes in 24 h</span></h3>'
             '<div class="areas" data-filter="merged"><button type="button" aria-pressed="true" data-area="">all</button>'
             + "".join(f'<button type="button" data-area="{e(k)}">{e(k)} <span class="mute">{v}</span></button>' for k, v in areas.most_common(8))
             + '</div><ul class="feed" id="merged">')
    for i, m in enumerate(lm[:60]):
        title = AREA.sub("", m["title"] or "", count=1)
        o.append(f'<li data-area="{e(m["area"])}"{" hidden" if i >= 15 else ""}><span class="area">{e(m["area"])}</span>'
                 f'<a href="{e(m["url"])}">{e(title)}</a><div class="meta">#{m["number"]} by {e(m["author"])} · {ago(e, m["merged"])}</div></li>')
    o.append('</ul><p><button type="button" class="btn" id="merged-more">Show more</button> '
             f'<a class="note" href="{REPO_URL}/commits/main">full history on GitHub →</a></p></div><div>')
    o.append('<h3>Latest test reports</h3><ul class="feed">')
    for r in reps[:12]:
        o.append(f'<li><span class="area">{e(pnames.get(r["platform"], "platform unknown"))}</span>{describe(r, e)}'
                 f'<div class="meta">{e(r["gpu"] or "")}{" · " if r["gpu"] else ""}by {e(r["author"])} · '
                 f'<a href="{e(r["source"])}">{ago(e, r["date"])}</a></div></li>')
    o.append('</ul><p class="note"><a href="reports.html">All reports →</a> Lines are composed from fields an AI filled from '
             'the comment and that code checked against it; open the source to read it.</p></div></div>')
    # 5. Pulse
    o.append(f'<h2 id="pulse">Where the project is</h2><div class="kpis">' + "".join(
        f'<div class="kpi"><b>{v}</b>{k}</div>' for k, v in [
            ("changes merged in 24 h", ov["merged_24h"]), ("open pull requests", ov["open_prs"]),
            ("open issues", ov["open_issues"]), ("people active in 24 h", ov["people_24h"])]) + "</div>")
    o.append(f'<div class="cols"><div><h3>Changes merged per day</h3>{svg_bars(e, ov["merged_per_day"])}'
             f'<p class="note">Counted since this board started reading the repository ({e(ov["since"][:10])}).</p></div><div>'
             '<h3>Most discussed right now</h3><ul class="feed">')
    for h in ov["hot_issues"]:
        o.append(f'<li><a href="{e(h["url"])}">{e(h["title"])}</a><div class="meta">#{h["number"]} · {h["people"]} people, '
                 f'{h["msgs"]} comments in 24 h</div></li>')
    o.append("</ul></div></div>")
    # 6. Get involved
    o.append('<h2 id="help">Get involved</h2><div class="cards help">')
    for n, c in camps.items():
        o.append(f'<a class="card" href="campaign-{n}.html"><b>Campaign #{n}</b><p>{e(c["title"])}</p>'
                 '<p class="note">Who does what, what the numbers say, and what your machine can measure.</p></a>')
    o.append('<a class="card" href="overlaps.html"><b>Overlapping pull requests</b><p>Open PRs that change the same thing.</p>'
             '<p class="note">Check before writing a change.</p></a>'
             '<a class="card" href="duplicate-issues.html"><b>Duplicate issues</b><p>Open issues that report the same problem.</p>'
             '<p class="note">Check before opening an issue.</p></a>'
             '<a class="card" href="AGENTS-campaign.md"><b>For AI agents</b><p>One line for your agent\'s instructions, '
             'small JSON files instead of long threads.</p><p class="note">llms.txt · api/</p></a>'
             f'<a class="card" href="{REPO_URL}"><b>XCL on GitHub</b><p>The project itself: code, issues, pull requests.</p>'
             '<p class="note">Read its README before testing.</p></a></div>')
    return "\n".join(o)


def html_reports(e, reps):
    """Every first-hand report, by platform, newest first."""
    pnames = dict(P.PLATFORMS)
    o = ['<h1>Test reports</h1><p class="mute">Every GitHub message where someone says how far the game got on their '
         'machine. An AI filled the fields (stage, platform, GPU, time) from the comment; code checked them against the '
         'text. Open the source before relying on a line.</p>',
         '<div class="filters"><select name="pl"><option value="">all platforms</option>'
         + "".join(f'<option value="{e(k)}">{e(v)}</option>' for k, v in P.PLATFORMS)
         + '<option value="none">platform unknown</option></select><select name="st"><option value="">all stages</option>'
         + "".join(f'<option value="{e(i)}">{e(n)}</option>' for i, n, _ in P.STAGES)
         + '</select><span id="rep-count" class="mute small"></span></div>',
         '<div class="scroll"><table class="tbl" id="reports"><tr><th>When</th><th>Platform</th><th>GPU</th><th>Furthest point</th>'
         '<th>Commit</th><th>Who</th></tr>']
    seen = set()
    for r in reps:
        anchor = ""
        if r["platform"] and r["platform"] not in seen:
            seen.add(r["platform"])
            anchor = f' id="{e(r["platform"])}"'
        o.append(f'<tr{anchor} data-pl="{e(r["platform"] or "none")}" data-st="{e(r["stage"])}"><td><a href="{e(r["source"])}">'
                 f'{ago(e, r["date"])}</a></td><td>{e(pnames.get(r["platform"], "unknown"))}</td><td>{e(r["gpu"] or "")}</td>'
                 f'<td>{describe(r, e)}</td><td><code>{e(r["commit"] or "")}</code></td><td>{e(r["author"])}'
                 f'<div class="small">{"issue" if r["kind"] == "issue" else "comment on"} #{r["number"]}</div></td></tr>')
    o.append("</table></div>")
    return "\n".join(o)


def api(reps, st, ov):
    return ({"stages": [{"id": i, "name": n, "meaning": d} for i, n, d in P.STAGES], "confirm_people": CONFIRM,
             "recent_days": RECENT_DAYS,
             "by_platform": {p: {"furthest_confirmed": P.STAGE_IDS[s["confirmed"]] if s["confirmed"] >= 0 else None,
                                 "furthest_reported": P.STAGE_IDS[s["once"]] if s["once"] >= 0 else None,
                                 "people_per_stage": {P.STAGE_IDS[k]: v for k, v in s["people"].items()},
                                 "reports": s["reports"], "median_end_s": s["median_end_s"]} for p, s in st.items()},
             "reports": [{k: r.get(k) for k in ("date", "author", "platform", "stage", "ended", "gpu", "commit", "at_seconds",
                                            "fps", "source")} for r in reps]},
            {k: ov[k] for k in ("since", "merged_24h", "open_prs", "open_issues", "people_24h", "merged_per_day")}
            | {"latest_merged": [{k: m[k] for k in ("number", "merged", "area", "url")} for m in ov["latest_merged"][:60]],
               "hot_issues": [{k: h[k] for k in ("number", "people", "msgs", "url")} for h in ov["hot_issues"]]})


def build(con, out, page, e, camps):
    reps = P.reports(con)
    st = ladder_state(reps)
    ov = overview(con)
    with open(f"{out}/index.html", "w") as fh:
        fh.write(page("XCL board: does GTA VI run yet?", html_home(e, st, ov, reps, camps), "api/progress.json",
                      extra_css=CSS, nav="home"))
    with open(f"{out}/reports.html", "w") as fh:
        fh.write(page("Test reports · XCL board", html_reports(e, reps), "api/progress.json", extra_css=CSS, nav="reports"))
    prog, pulse = api(reps, st, ov)
    os.makedirs(f"{out}/api", exist_ok=True)
    with open(f"{out}/api/progress.json", "w") as fh:
        json.dump(prog, fh, separators=(",", ":"))
    with open(f"{out}/api/overview.json", "w") as fh:
        json.dump(pulse, fh, separators=(",", ":"))
    return {"reports": len(reps), "furthest": st["all"]["once"]}
