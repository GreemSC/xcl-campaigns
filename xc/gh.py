"""Minimal read-only GitHub REST client, standard library only."""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def jeton():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    chemin = os.environ.get("XC_TOKEN_FILE", ".github-token")
    if os.path.exists(chemin):
        return open(chemin).read().strip()
    if os.environ.get("XC_GH_CLI") == "1":  # dev machine only: reuse the `gh` CLI token
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    return None


class GitHub:
    def __init__(self, token=None):
        self.token = token or jeton()
        self.remaining = None
        self.reset = None

    def diff(self, repo, number, limit=200000):
        """Unified diff of a PR (text), truncated to `limit` bytes."""
        h = {"Accept": "application/vnd.github.diff", "User-Agent": "xcl-campaigns"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(f"{API}/repos/{repo}/pulls/{number}", headers=h)
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read(limit).decode("utf-8", "replace")

    def graphql(self, query, variables):
        """One read-only GraphQL query; returns `data` (raises on errors)."""
        h = {"Content-Type": "application/json", "User-Agent": "xcl-campaigns"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        body = json.dumps({"query": query, "variables": variables}).encode()
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(f"{API}/graphql", data=body, headers=h),
                                            timeout=90) as r:
                    out = json.loads(r.read())
                if out.get("errors") and not out.get("data"):
                    raise RuntimeError(str(out["errors"])[:200])
                return out["data"]
            except urllib.error.HTTPError as e:
                if e.code in (403, 429, 500, 502, 503, 504):
                    time.sleep(min(60, 2 ** attempt * 5))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt)
        raise RuntimeError("GitHub GraphQL does not answer")

    def _req(self, url, etag=None, accept="application/vnd.github+json"):
        h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
             "User-Agent": "xcl-campaigns"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if etag:
            h["If-None-Match"] = etag
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                    self.remaining = int(r.headers.get("X-RateLimit-Remaining", "0") or 0)
                    self.reset = int(r.headers.get("X-RateLimit-Reset", "0") or 0)
                    return r.status, json.loads(r.read() or b"null"), r.headers
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    return 304, None, e.headers
                if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
                    wait = max(5, int(e.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time())
                    time.sleep(min(wait, 900))
                    continue
                if e.code in (500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt)
        raise RuntimeError(f"GitHub does not answer: {url}")

    def pages(self, chemin, params=None, etag=None):
        """Iterate over all pages. Yields (304, None, headers) if the first page did not change."""
        q = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        url = f"{API}{chemin}?{q}" if q else f"{API}{chemin}"
        first = True
        while url:
            status, data, headers = self._req(url, etag if first else None)
            if status == 304:
                yield 304, None, headers
                return
            yield status, data, headers
            first = False
            m = re.search(r'<([^>]+)>;\s*rel="next"', headers.get("Link", "") or "")
            url = m.group(1) if m else None
