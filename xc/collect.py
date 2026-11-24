"""Collector: reads the target repository continuously (issues, PRs, comments, review comments, PR files).

Read-only, no rights on the repository needed. Each pass only asks for what changed since the previous
one (`since` + ETag; a 304 answer does not count against the rate limit)."""
import datetime as dt
import os

from . import db
from .gh import GitHub

REPO = os.environ.get("XC_REPO", "xcl-dev/xcl")   # was ivall/xcl until 2026-11-24 (GitHub redirects)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stream(con, gh, name, path, convert):
    """One stream sorted by update time, resumed where the previous pass stopped."""
    cursor = db.get_state(con, f"cursor:{name}")
    etag = db.get_state(con, f"etag:{name}")
    params = {"per_page": 100, "sort": "updated", "direction": "asc"}
    if name == "issues":
        params["state"] = "all"
    if cursor:
        params["since"] = cursor
    seen, changed, top = 0, [], cursor
    for i, (status, page, headers) in enumerate(gh.pages(path, params, etag)):
        if status == 304:
            return 0, []
        if i == 0 and headers.get("ETag"):
            db.set_state(con, f"etag:{name}", headers["ETag"])
        t = now()
        for raw in page:
            it = convert(raw)
            seen += 1
            if db.store(con, it, t):
                changed.append(it["key"])
            if not top or raw["updated_at"] > top:
                top = raw["updated_at"]
        con.commit()
    if top:
        db.set_state(con, f"cursor:{name}", top)
        con.commit()
    return seen, changed


def _issue(b):
    is_pr = "pull_request" in b
    merged = (b.get("pull_request") or {}).get("merged_at")
    return {"key": f"{'pr' if is_pr else 'issue'}:{b['number']}", "kind": "pr" if is_pr else "issue",
            "number": b["number"], "author": (b.get("user") or {}).get("login"),
            "created": b["created_at"], "updated": b["updated_at"], "closed": b.get("closed_at"), "merged": merged,
            "status": "merged" if merged else b["state"], "title": b.get("title"), "body": b.get("body"),
            "url": b["html_url"],
            "raw": {"labels": [l["name"] for l in b.get("labels") or []], "draft": b.get("draft"),
                    "comments": b.get("comments"), "author_association": b.get("author_association"),
                    "state_reason": b.get("state_reason")}}


def _comment(b):
    return {"key": f"comment:{b['id']}", "kind": "comment", "number": int(b["issue_url"].rsplit("/", 1)[1]),
            "author": (b.get("user") or {}).get("login"), "created": b["created_at"], "updated": b["updated_at"],
            "status": "open", "body": b.get("body"), "url": b["html_url"],
            "raw": {"author_association": b.get("author_association")}}


def _review_comment(b):
    return {"key": f"revcomment:{b['id']}", "kind": "revcomment",
            "number": int(b["pull_request_url"].rsplit("/", 1)[1]),
            "author": (b.get("user") or {}).get("login"), "created": b["created_at"], "updated": b["updated_at"],
            "status": "open", "body": b.get("body"), "url": b["html_url"],
            "raw": {"path": b.get("path"), "author_association": b.get("author_association")}}


def _pr_files(con, gh, budget, state="open"):
    """Files touched by PRs whose head commit has not been seen yet (most recently updated first).
    state='closed' covers merged PRs (closed without merge are skipped): needed to spot open PRs that
    redo something already merged."""
    done = 0
    for _, page, _ in gh.pages(f"/repos/{REPO}/pulls",
                               {"state": state, "sort": "updated", "direction": "desc", "per_page": 100}):
        fresh = 0
        for p in page:
            if state == "closed" and not p.get("merged_at"):
                continue
            sha = p["head"]["sha"]
            if con.execute("SELECT 1 FROM pr_files WHERE number=? AND sha=? LIMIT 1", (p["number"], sha)).fetchone():
                continue
            fresh += 1
            if done >= budget:
                return done
            files = []
            for _, fp, _ in gh.pages(f"/repos/{REPO}/pulls/{p['number']}/files", {"per_page": 100}):
                files += fp
            con.execute("DELETE FROM pr_files WHERE number=?", (p["number"],))
            con.executemany("INSERT OR REPLACE INTO pr_files VALUES (?,?,?,?,?)",
                            [(p["number"], sha, f["filename"], f.get("additions"), f.get("deletions")) for f in files]
                            or [(p["number"], sha, "", 0, 0)])
            con.commit()
            done += 1
        if fresh == 0:
            break
    return done


def run(con=None, gh=None, pr_file_budget=150):
    con = con or db.connect()
    gh = gh or GitHub()
    out = {}
    for name, path, conv in (("issues", f"/repos/{REPO}/issues", _issue),
                             ("comments", f"/repos/{REPO}/issues/comments", _comment),
                             ("revcomments", f"/repos/{REPO}/pulls/comments", _review_comment)):
        seen, changed = _stream(con, gh, name, path, conv)
        out[name] = {"seen": seen, "changed": len(changed)}
    out["pr_files"] = _pr_files(con, gh, pr_file_budget)
    out["merged_pr_files"] = _pr_files(con, gh, max(0, pr_file_budget - out["pr_files"]) // 2, "closed")
    out["rate_left"] = gh.remaining
    db.set_state(con, "last_pass", now())
    con.commit()
    return out
