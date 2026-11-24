# xcl-campaigns

A community board for [xcl-dev/xcl](https://github.com/xcl-dev/xcl) (formerly ivall/xcl), the recompiler that runs the
Xbox Series build of GTA VI on PC. Made by contributors, not by the XCL maintainers.

**For everyone** (front page): does the game run yet, and how far it gets on each platform (Windows / Linux ×
NVIDIA / AMD / Intel, Steam Deck), from first-hand test reports; what was merged lately; where the project is
(changes per day, open PRs and issues, the most discussed issues). **Test reports**: every report, filterable.

**For contributors**: the *campaign issues*, where the maintainer asks many contributors, and their AI agents, to
work on one topic at once (the first one is [#1269](https://github.com/xcl-dev/xcl/issues/1269), shader compile
time); overlapping PRs and duplicate issues across the repository; a JSON API and `llms.txt` for agents.

On #1269, 40 comments from 27 authors arrived in the first hour. Four people measured the same `-O0` threshold,
numbers came from ten different `main` commits, and nobody could see who was doing what. This board turns the
thread into a page, every few minutes:

- **Tasks**: who holds each one, which teams formed, where two teams work on the same thing, linked PRs.
- **What can I do?**: pick your machine, see the measurements that still need it and the free code tasks, with a
  claim line ready to copy.
- **What the numbers say**: for each measurement, the few metrics that compare across machines (e.g. driver time
  per KB of DXIL), with the median, the range and whether the machines agree, per hardware class.
- **Measurement grid**: measurement × hardware class, which cells are empty, which mix commits.
- **Volunteers**: people who offered help, and the cells their hardware could fill.
- **Overlapping PRs** across the whole repository.
- **A typed JSON digest** per campaign, so agents read data instead of 100 comments.
- **A small static API for agents** ([`api/v2/index.json`](https://greemsc.github.io/xcl-campaigns/api/v2/index.json), [`llms.txt`](https://greemsc.github.io/xcl-campaigns/llms.txt)): one small JSON file per question (who touches this file? is anyone already doing X? what can my GPU measure for campaign N? where does this median come from?), each with `generated_at`, `synced_until` and the list of fields a model filled. Measured with fresh agents before and after (`xc/agentapi.py`). The older `api/*.json` stays for existing users.

**Live board:** https://greemsc.github.io/xcl-campaigns/

## Nobody has to use it

It reads GitHub. Every comment is filed whether or not its author knows the board exists. Ending a comment with
one small board link that carries the data (`<sub>[board: M2 result](…/campaign-1269.html?r=M2&class=amd-radv&m=…)</sub>`)
only makes your row exact and immediate. See [AGENTS-campaign.md](AGENTS-campaign.md).

## How it works

| Step | What | AI? |
|---|---|---|
| `collect` | Reads issues, PRs, comments, PR files of xcl-dev/xcl every minute (public API, read-only token, `since` + ETag). Keeps every version of every comment. | no |
| `extract` | Rules: commits, PR numbers, GPUs, drivers, `XCL_*` variables, author blocks. | no |
| `classify` | Campaign messages without a block: an AI (Claude Haiku via `claude -p`, **no tools, no network**) returns a card constrained by a JSON schema; code then checks it against the source text. New `[OFFICIAL]` / help-wanted issues from a maintainer open a campaign automatically, and work announced in a thread grows the task list (A1, A2, …). | yes, typed output only |
| `intent` | Every open PR and issue gets a typed intent card (area, kind, subject, keywords, crash offset), used to find duplicates that are worded differently. | yes, typed output only |
| `check` | A second model (Sonnet) reads each candidate group of duplicates and marks each member same-change / partial-overlap / different. Cached until a member changes. | yes, typed output only |
| `findings` | For each result message, an AI (Haiku, same box) only points at which of its numbers form a metric of the campaign file (metric id, number indexes, a size written in the text). Code converts units, checks the size against the text, computes the value and aggregates across machines. | yes, typed output only |
| `progress` | Issues and comments that name a stage of the game and some hardware (rules) get a typed card: first-hand or not, furthest stage (starts → first pictures → title screen → menus → world loading → world on screen → playable; "world on screen" means the world was drawn, not that anyone played), how it ended, OS, GPU vendor, GPU, commit, time, fps. GPU, commit and numbers must appear in the text. "World on screen" and "playable" are re-read by Sonnet, which must quote verbatim the author's description of the screen; without such a quote the report counts as world loading. A stage is "confirmed" when 2+ people reached it. | yes, typed output only |
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

## Publishing faster

`xc-publish.timer` runs every 2 minutes and `publish.sh` asks GitHub how Pages builds the site. With the branch
builder (about 10 builds per hour) it publishes at most every 6 minutes. Once Settings > Pages > Source is
"GitHub Actions", it publishes every run and adds `deploy/pages-workflow.yml` to each published commit (the
`github-pages` environment must allow the `gh-pages` branch).
Browsers may keep a page up to 10 minutes (GitHub's cache header): the page checks `api/health.json` and offers to
load the latest copy when it is older than the server's.

## Limits

- `campaigns/1269.yaml` is an **unofficial draft** inferred from the thread, until the maintainer adopts or corrects it.
- Rows marked *auto* come from an AI reading free text: they can be wrong. Every row links to its source;
  authors can fix theirs (`xcl-fix`).
- "Overlapping PRs" are candidates for a human to check, not verdicts.
- No game data anywhere: GitHub text, counts and timings only.

License: MIT.
