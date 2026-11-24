"""Who maintains the repository, from GitHub itself rather than a hand-written list.

Every issue, PR and comment GitHub returns carries the author's `author_association` with the repository. A login
whose most recent item says OWNER, MEMBER or COLLABORATOR (write access) counts as a maintainer. XC_MAINTAINERS
can add logins (comma-separated); XC_NOT_MAINTAINERS can remove some (e.g. a bot account with write access)."""
import json
import os

ROLES = {"OWNER", "MEMBER", "COLLABORATOR"}


def maintainers(con):
    latest = {}
    for author, created, raw in con.execute("SELECT author, created, raw FROM items WHERE raw IS NOT NULL ORDER BY created"):
        try:
            assoc = json.loads(raw).get("author_association")
        except (TypeError, ValueError):
            continue
        if assoc:
            latest[author] = assoc
    out = {a for a, r in latest.items() if r in ROLES}
    out |= {x for x in os.environ.get("XC_MAINTAINERS", "").split(",") if x}
    out -= {x for x in os.environ.get("XC_NOT_MAINTAINERS", "").split(",") if x}
    return out
