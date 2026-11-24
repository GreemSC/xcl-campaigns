"""python -m xc <command>

  collect          one read pass over GitHub
  extract          pass 1 (rules, no AI) on what changed
  classify [N]     pass 2 (author blocks, else AI) on at most N pending messages
  intent           AI intent card for open PRs / issues (whole repo)
  check            second AI check of candidate duplicate groups
  findings [N]     AI points at which reported numbers form a campaign metric (N messages)
  progress         AI files first-hand reports of how far the game gets (whole repository)
  render           build the pages and the JSON digests
  digest N [--posted]  draft a short GitHub update for campaign N with only what is new (never posts)
  loop [N]         collect + extract + render, then the AI steps + render again, every 60 s
"""
import json
import sys
import time


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "help"
    n = int(argv[2]) if len(argv) > 2 else 30
    if cmd == "collect":
        from .collect import run
        print(json.dumps(run()))
    elif cmd == "extract":
        from .extract import run
        print(json.dumps(run()))
    elif cmd == "classify":
        from .classify import run
        print(json.dumps(run(n)))
    elif cmd == "intent":
        from .intent import run
        print(json.dumps(run()))
    elif cmd == "check":
        from . import db, project
        print(json.dumps(project.check(db.connect())))
    elif cmd == "digest":
        from .digest import main as digest_main
        digest_main(argv[2:])
    elif cmd == "findings":
        from . import classify, db, findings
        print(json.dumps(findings.run(db.connect(), classify.campaigns(), n)))
    elif cmd == "progress":
        from . import db, progress
        print(json.dumps(progress.run(db.connect())))
    elif cmd == "render":
        from .render import run
        print(json.dumps(run()))
    elif cmd == "loop":
        from . import classify, collect, db, extract, findings, intent, progress, project, render
        # render_early: the pages and JSON get what GitHub said right after collect (~15 s), without waiting for the
        # AI steps (up to ~150 s in a burst); what the AI reads in this pass shows at the final render.
        steps = [("collect", collect.run), ("extract", extract.run), ("render_early", render.run),
                 ("classify", lambda: classify.run(n)),
                 ("intent", intent.run), ("check", lambda: project.check(db.connect())),
                 ("findings", lambda: findings.run(db.connect(), classify.campaigns(), 20)),
                 ("progress", lambda: progress.run(db.connect())), ("render", render.run)]
        while True:
            start = time.time()
            status = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": {}}
            for name, fn in steps:   # one failed step never stops the others, nor the loop
                t = time.time()
                try:
                    res, err = fn(), None
                except Exception as ex:
                    res, err = None, repr(ex)[:300]
                status["steps"][name] = {"seconds": round(time.time() - t, 1), "result": res, "error": err}
            status["seconds"] = round(time.time() - start, 1)
            con = db.connect()
            db.set_state(con, "loop_status", json.dumps(status))
            con.commit()
            print(time.strftime("%H:%M:%S"), json.dumps(status), flush=True)
            time.sleep(max(5, 60 - (time.time() - start)))
    else:
        print(__doc__)


main(sys.argv)
