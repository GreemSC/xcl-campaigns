"""python -m xc <command>

  collect          one read pass over GitHub
  extract          pass 1 (rules, no AI) on what changed
  classify [N]     pass 2 (author blocks, else AI) on at most N pending messages
  intent           AI intent card for open PRs / issues (whole repo)
  check            second AI check of candidate duplicate groups
  render           build the pages and the JSON digests
  loop [N]         collect + extract + classify + render, every 60 s
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
    elif cmd == "render":
        from .render import run
        print(json.dumps(run()))
    elif cmd == "loop":
        from . import classify, collect, db, extract, intent, project, render
        steps = [("collect", collect.run), ("extract", extract.run), ("classify", lambda: classify.run(n)),
                 ("intent", intent.run), ("check", lambda: project.check(db.connect())), ("render", render.run)]
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
