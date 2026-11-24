"""python -m xc <command>

  collect          one read pass over GitHub
  extract          pass 1 (rules, no AI) on what changed
  classify [N]     pass 2 (author blocks, else AI) on at most N pending messages
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
    elif cmd == "render":
        from .render import run
        print(json.dumps(run()))
    elif cmd == "loop":
        from . import classify, collect, extract, render
        while True:
            start = time.time()
            try:
                out = {"collect": collect.run(), "extract": extract.run(), "classify": classify.run(n), "render": render.run()}
                print(time.strftime("%H:%M:%S"), json.dumps(out), flush=True)
            except Exception as ex:  # one failed pass never kills the loop
                print(time.strftime("%H:%M:%S"), "ERROR", repr(ex), flush=True)
            time.sleep(max(5, 60 - (time.time() - start)))
    else:
        print(__doc__)


main(sys.argv)
