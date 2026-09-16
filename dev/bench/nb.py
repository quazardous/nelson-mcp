#!/usr/bin/env python3
"""nb — call Nelson tools the way an MCP agent would, and keep the evidence.

    nb.py tools [FILTER]            list advertised tools (name, params)
    nb.py call TOOL [JSON_ARGS]     call one tool, print a compact result
    nb.py health                    one /health probe

Every call is appended to $NB_TRACE (default dev/bench/results/trace.jsonl):
tool, args, status, elapsed, response size, scenario ($NB_SCENARIO). If a call
times out and /health does not answer either, LibreOffice is treated as hung:
a gdb backtrace of every thread is saved next to the trace before exiting 3.

Talks to the wbox dev instance on port 8767 unless NB_PORT says otherwise.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("NB_PORT", "8767"))
BASE = "http://localhost:%d" % PORT
TRACE = os.environ.get("NB_TRACE", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results", "trace.jsonl"))
SCENARIO = os.environ.get("NB_SCENARIO", "")
TIMEOUT = float(os.environ.get("NB_TIMEOUT", "120"))
MAXPRINT = int(os.environ.get("NB_MAXPRINT", "1500"))


def _post(payload, timeout):
    req = urllib.request.Request(
        BASE + "/mcp", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def health(timeout=5):
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _soffice_pid():
    out = subprocess.run(["pgrep", "-f", "UserInstallation=file:///tmp/lo_dev_profile"],
                         capture_output=True, text=True).stdout.split()
    pids = [p for p in out
            if open("/proc/%s/comm" % p).read().strip() == "soffice.bin"]
    return pids[0] if pids else None


def capture_hang(reason):
    pid = _soffice_pid()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(os.path.dirname(TRACE), "hang-%s.bt.txt" % stamp)
    if pid:
        with open(path, "w") as f:
            f.write("# %s\n# scenario=%s\n" % (reason, SCENARIO))
            f.flush()
            subprocess.run(["timeout", "90", "gdb", "-p", pid, "-batch",
                            "-ex", "set pagination off",
                            "-ex", "thread apply all bt 40"],
                           stdout=f, stderr=subprocess.STDOUT)
    return path if pid else None


def trace(rec):
    os.makedirs(os.path.dirname(TRACE), exist_ok=True)
    with open(TRACE, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def call(tool, args):
    payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 10**9,
               "method": "tools/call",
               "params": {"name": tool, "arguments": args}}
    t0 = time.time()
    rec = {"ts": time.strftime("%H:%M:%S"), "scenario": SCENARIO,
           "tool": tool, "args": args}
    try:
        raw = _post(payload, TIMEOUT)
    except Exception as e:
        rec.update(elapsed=round(time.time() - t0, 2), status="transport_error",
                   error=str(e))
        h = health()
        if "error" in h:
            rec["hang_bt"] = capture_hang("call %s timed out; /health dead" % tool)
            rec["status"] = "HANG"
        trace(rec)
        print(json.dumps(rec, ensure_ascii=False))
        sys.exit(3 if rec["status"] == "HANG" else 2)

    elapsed = round(time.time() - t0, 2)
    msg = json.loads(raw)
    if "error" in msg:
        result = {"status": "rpc_error", "error": msg["error"]}
    else:
        content = msg["result"].get("content") or [{}]
        text = content[0].get("text", "")
        try:
            result = json.loads(text)
        except Exception:
            result = {"status": "non_json", "text": text}
    rec.update(elapsed=elapsed, bytes=len(raw),
               status=result.get("status", "?"),
               error=result.get("error") or result.get("message")
               if result.get("status") != "ok" else None)
    trace(rec)
    out = json.dumps(result, ensure_ascii=False)
    head = "[%s %.2fs %dB]" % (rec["status"], elapsed, len(raw))
    print(head, out if len(out) <= MAXPRINT else out[:MAXPRINT] + " …(%d chars)" % len(out))


def tools(flt=""):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    res = json.loads(_post(payload, 30))["result"]["tools"]
    print("%d tools" % len(res))
    for t in sorted(res, key=lambda t: t["name"]):
        if flt and flt not in t["name"]:
            continue
        props = list((t.get("inputSchema") or {}).get("properties", {}))
        props = [p for p in props if p != "_document"]
        print("  %-28s %s" % (t["name"], ", ".join(props)))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "call":
        call(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
    elif cmd == "tools":
        tools(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "health":
        print(json.dumps(health()))
    else:
        print(__doc__)
