#!/usr/bin/env python3
# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cold-start LibreOffice with a document, over and over, and catch hangs.

    coldstart_test.py [RUNS] [--timeout SECONDS]

GitHub #35/#37: started with a document on the command line, LibreOffice
sometimes never came up — the main thread in SynchronousDispatch while
Nelson was bootstrapping. Each run here:

  1. stops the wbox dev instance (and any soffice left on its profile);
  2. starts it with a fresh copy of a Writer document on the command line —
     the SynchronousDispatch path — under the real GUI, offscreen;
  3. polls /health every 0.5 s during the whole start, as MCP clients and
     launchers do;
  4. once Nelson answers, asks doc_list_open for the document.

A run that does not reach step 4 within the timeout is a hang: a gdb
backtrace of every thread is saved next to the results, then the instance
is killed. Results: dev/bench/results/coldstart-<stamp>.jsonl, and a summary
on stdout. Exit status 1 if any run hung.

Uses the dev profile (/tmp/lo_dev_profile, Nelson on 8767): deploy first
(make wbox-deploy) so it runs the code under test.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "dev", "lo-wbox", "config.yaml")
RESULTS = os.path.join(ROOT, "dev", "bench", "results")
WORK = os.path.join(ROOT, "dev", "bench", "work", "coldstart")
PROFILE = "/tmp/lo_dev_profile"
PORT = 8767
COMMAND = ("soffice --nologo --norestore "
           "-env:UserInstallation=file://%s "
           "--accept=\"socket,host=localhost,port=2002;urp;\" %s")


def wbox_python():
    env = os.environ.get("WBOX_PYTHON")
    if env:
        return env
    exe = shutil.which("wbox-mcp")
    if exe:
        with open(exe) as f:
            first = f.readline().strip()
        if first.startswith("#!"):
            return first[2:]
    sys.exit("wbox-mcp not found: set WBOX_PYTHON")


def ctl(*args):
    return subprocess.run(
        [wbox_python(), os.path.join(ROOT, "scripts", "wbox_ctl.py")]
        + list(args), capture_output=True, text=True, timeout=120)


def soffice_pids():
    out = subprocess.run(["pgrep", "-f", "UserInstallation=file://" + PROFILE],
                         capture_output=True, text=True).stdout.split()
    pids = []
    for pid in out:
        try:
            with open("/proc/%s/comm" % pid) as f:
                if f.read().strip() == "soffice.bin":
                    pids.append(pid)
        except OSError:
            continue
    return pids


def stop():
    ctl("down", CONFIG)
    for pid in soffice_pids():
        subprocess.run(["kill", "-9", pid])
    time.sleep(1)


def get(path, timeout):
    with urllib.request.urlopen("http://localhost:%d%s" % (PORT, path),
                                timeout=timeout) as r:
        return json.loads(r.read())


def call(tool, args, timeout):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": args}}
    req = urllib.request.Request(
        "http://localhost:%d/mcp" % PORT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        msg = json.loads(r.read())
    return json.loads(msg["result"]["content"][0]["text"])


def backtrace(path, reason):
    pids = soffice_pids()
    with open(path, "w") as f:
        f.write("# %s\n" % reason)
        f.flush()
        for pid in pids:
            subprocess.run(["timeout", "90", "gdb", "-p", pid, "-batch",
                            "-ex", "set pagination off",
                            "-ex", "thread apply all bt 40"],
                           stdout=f, stderr=subprocess.STDOUT)
    return path if pids else None


def one_run(n, source, timeout, stamp):
    doc = os.path.join(WORK, "cold-%03d.odt" % n)
    shutil.copyfile(source, doc)
    stop()
    started = time.time()
    # Poll /health from the very start, in parallel with the launch: wbox's
    # "up" returns only once the window exists, after the window where the
    # deadlock happens, and clients do not wait for it either.
    early = {"polls": 0}
    launched = threading.Event()

    def early_polls():
        while not launched.is_set():
            early["polls"] += 1
            try:
                get("/health", timeout=2)
            except Exception:
                pass
            time.sleep(0.5)

    poller = threading.Thread(target=early_polls, daemon=True)
    poller.start()
    up = ctl("up", CONFIG, "-s", "app.command=" + COMMAND % (PROFILE, doc))
    launched.set()
    poller.join(5)
    record = {"run": n, "up_ok": up.returncode == 0,
              "up_s": round(time.time() - started, 1),
              "early_polls": early["polls"]}
    health_at = doc_at = None
    polls = failures = 0
    while time.time() - started < timeout:
        polls += 1
        try:
            if health_at is None:
                get("/health", timeout=2)
                health_at = time.time() - started
            listed = call("doc_list_open", {}, timeout=10)
            urls = [d.get("url") or "" for d in listed.get("documents", [])]
            if any(u.endswith(os.path.basename(doc)) for u in urls):
                doc_at = time.time() - started
                break
        except Exception:
            failures += 1
        time.sleep(0.5)
    record.update(health_s=round(health_at, 1) if health_at else None,
                  document_s=round(doc_at, 1) if doc_at else None,
                  polls=polls, failed_polls=failures,
                  hung=doc_at is None)
    if doc_at is None:
        record["backtrace"] = backtrace(
            os.path.join(RESULTS, "coldstart-%s-run%03d.bt.txt" % (stamp, n)),
            "cold start run %d: no document after %ds (health at %s)"
            % (n, timeout, health_at))
    stop()
    return record


def main():
    args = sys.argv[1:]
    timeout = 90
    if "--timeout" in args:
        i = args.index("--timeout")
        timeout = int(args[i + 1])
        del args[i:i + 2]
    runs = int(args[0]) if args else 10
    os.makedirs(RESULTS, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    source = os.path.join(WORK, "source.odt")
    if not os.path.exists(source):
        bench = os.path.join(ROOT, "dev", "bench", "docs", "gdpr.docx")
        sys.exit("need %s (a Writer document to open); copy one there, "
                 "e.g. %s converted to .odt" % (source, bench))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(RESULTS, "coldstart-%s.jsonl" % stamp)
    hangs = 0
    with open(out_path, "w") as out:
        for n in range(1, runs + 1):
            rec = one_run(n, source, timeout, stamp)
            hangs += rec["hung"]
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print("run %3d  health %5s s  document %5s s  %s" % (
                n, rec["health_s"], rec["document_s"],
                "HUNG -> %s" % rec.get("backtrace") if rec["hung"] else "ok"),
                flush=True)
    print("%d run(s), %d hang(s) -> %s" % (runs, hangs, out_path))
    return 1 if hangs else 0


if __name__ == "__main__":
    sys.exit(main())
