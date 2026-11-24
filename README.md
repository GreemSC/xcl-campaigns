# xcl-campaigns

A board for the *campaign issues* of [ivall/xcl](https://github.com/ivall/xcl): issues where the maintainer asks
many contributors, and their AI agents, to work on one topic at once (the first one is
[#1269](https://github.com/ivall/xcl/issues/1269), shader compile time).

On #1269, 40 comments from 27 authors arrived in the first hour. Four people measured the same `-O0` threshold,
numbers came from ten different `main` commits, and nobody could see who was doing what. This board turns the
thread into a page, every few minutes:

- **Tasks**: who holds each one, which teams formed, where two teams work on the same thing, linked PRs.
- **Measurement grid**: measurement × hardware class, which cells are empty, which mix commits.
- **Volunteers**: people who offered help, and the cells their hardware could fill.
- **Overlapping PRs** across the whole repository.
- **A typed JSON digest** per campaign, so agents read data instead of 100 comments.

**Live board:** https://greemsc.github.io/xcl-campaigns/

## Nobody has to use it

It reads GitHub. Every comment is filed whether or not its author knows the board exists. Posting a small
`xcl-claim` / `xcl-result` block only makes your row exact and immediate. See [AGENTS-campaign.md](AGENTS-campaign.md).

## How it works

| Step | What | AI? |
|---|---|---|
| `collect` | Reads issues, PRs, comments, PR files of ivall/xcl every minute (public API, read-only token, `since` + ETag). Keeps every version of every comment. | no |
| `extract` | Rules: commits, PR numbers, GPUs, drivers, `XCL_*` variables, author blocks. | no |
| `classify` | Campaign messages without a block: an AI (Claude Haiku via `claude -p`, **no tools, no network**) returns a card constrained by a JSON schema; code then checks it against the source text. | yes, typed output only |
| `render` | Pages + JSON digest, computed by code. Every row links to its source comment. | no |

Why the AI never writes the page: a summary written by a model is exactly what a hidden instruction in a
comment would target. Here the model only fills typed fields (enums, numbers, logins, commits), and the page and
digest are computed from those fields by plain code.

## Run it

```sh
python3 -m xc loop 30        # collect + extract + classify + render, every 60 s; output in site/
```

Needs Python 3 with PyYAML, a read-only GitHub token in `.github-token` (fine-grained, public repositories,
no permissions), and the `claude` CLI logged in for the classify step (without it, everything else still runs).
A campaign is one file: `campaigns/<issue>.yaml`.

## Limits

- `campaigns/1269.yaml` is an **unofficial draft** inferred from the thread, until the maintainer adopts or corrects it.
- Rows marked *auto* come from an AI reading free text: they can be wrong. Every row links to its source;
  authors can fix theirs (`xcl-fix`).
- "Overlapping PRs" are candidates for a human to check, not verdicts.
- No game data anywhere: GitHub text, counts and timings only.

License: MIT.
