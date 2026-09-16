#!/usr/bin/env python3
"""soak — run realistic document cycles against Nelson until something gives.

    soak.py [CYCLES]

Each cycle does what an agent session does, through dev/bench/nb.py so every
call is traced and a hang is captured with a gdb backtrace:

  Writer: create with a path, write an HTML report, outline, search, comment,
          save, close.
  Calc:   create with a path, write a table with formulas, chart, save, close.

After every cycle it records elapsed time, failed calls and the resident
memory of soffice.bin, so a leak shows up as a slope and a hang stops the run.
Results go to results/soak-<stamp>.jsonl next to the trace.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work", "soak")
RESULTS = os.path.join(HERE, "results")
NB = [sys.executable, os.path.join(HERE, "nb.py"), "call"]

REPORT = """<h1>Soak report %d</h1><h2>Summary</h2>
<p>Cycle <b>%d</b> of the endurance run.</p>
<table><tr><th>Key</th><th>Value</th></tr><tr><td>cycle</td><td>%d</td></tr></table>
<h2>Details</h2><ul><li>first</li><li>second</li></ul>"""


def call(tool, args):
    env = dict(os.environ, NB_MAXPRINT="400")
    r = subprocess.run(NB + [tool, json.dumps(args)], capture_output=True,
                       text=True, env=env)
    out = r.stdout.strip()
    status = out[1:].split(" ", 1)[0] if out.startswith("[") else "?"
    if r.returncode == 3:
        status = "HANG"
    return status, out


def soffice_rss_kb():
    pids = subprocess.run(
        ["pgrep", "-f", "UserInstallation=file:///tmp/lo_dev_profile"],
        capture_output=True, text=True).stdout.split()
    for p in pids:
        try:
            if open("/proc/%s/comm" % p).read().strip() != "soffice.bin":
                continue
            for line in open("/proc/%s/status" % p):
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
        except OSError:
            continue
    return None


def writer_cycle(n):
    path = os.path.join(WORK, "w%03d.odt" % n)
    doc = {"_document": "path:" + path}
    steps = [
        ("doc_create", {"doc_type": "writer", "path": path}),
        ("text_apply_range", dict(doc, target="full", content=REPORT % (n, n, n))),
        ("nav_outline", doc),
        ("text_search", dict(doc, pattern="cycle", max_results=5)),
        ("comment_add", dict(doc, paragraph_index=0, content="soak %d" % n,
                             author="soak")),
        ("doc_save", doc),
        ("doc_close", doc),
    ]
    return steps


def calc_cycle(n):
    path = os.path.join(WORK, "c%03d.ods" % n)
    doc = {"_document": "path:" + path}
    rows = [["Item", "Q1", "Q2", "Total"]] + [
        ["row%d" % i, i * 10, i * 7, "=B%d+C%d" % (i + 2, i + 2)]
        for i in range(10)]
    steps = [
        ("doc_create", {"doc_type": "calc", "path": path}),
        ("calc_write_range", dict(doc, start_cell="A1", values=rows)),
        ("calc_chart", dict(doc, action="create", data_range="A1:C11",
                            chart_type="bar", title="soak %d" % n,
                            position="F2")),
        ("doc_save", doc),
        ("doc_close", doc),
    ]
    return steps


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    out_path = os.path.join(RESULTS, "soak-%s.jsonl" % time.strftime("%Y%m%d-%H%M%S"))
    os.environ["NB_SCENARIO"] = "X-soak"
    print("soak: %d cycles -> %s" % (cycles, out_path), flush=True)
    with open(out_path, "w") as out:
        for n in range(1, cycles + 1):
            t0 = time.time()
            failures = []
            for kind, steps in (("writer", writer_cycle(n)), ("calc", calc_cycle(n))):
                for tool, args in steps:
                    status, text = call(tool, args)
                    if status == "HANG":
                        rec = {"cycle": n, "kind": kind, "tool": tool,
                               "status": "HANG", "detail": text[:400]}
                        out.write(json.dumps(rec) + "\n")
                        print("HANG at cycle %d %s %s" % (n, kind, tool), flush=True)
                        return 3
                    if status != "ok":
                        failures.append({"kind": kind, "tool": tool,
                                         "status": status, "detail": text[:300]})
            rec = {"cycle": n, "elapsed": round(time.time() - t0, 2),
                   "rss_kb": soffice_rss_kb(), "failures": failures}
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print("cycle %3d  %5.1fs  rss=%s kB  failures=%d%s" % (
                n, rec["elapsed"], rec["rss_kb"], len(failures),
                "  " + ", ".join("%s:%s" % (f["tool"], f["status"]) for f in failures)
                if failures else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
