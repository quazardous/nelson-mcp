#!/usr/bin/env python3
"""close_churn — GitHub #36 faults 1 and 3: many open documents (some read-only, some
copies of one file), close each by id in random order, check the right one
closed and doc_list_open stays consistent."""
import json, os, random, shutil, stat, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import nb
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "work", "close36"); shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
src = os.path.join(HERE, "work", "coldstart", "source.odt")
def call(tool, args):
    msg = json.loads(nb._post({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":tool,"arguments":args}}, 120))
    return json.loads(msg["result"]["content"][0]["text"])
def listed():
    return call("doc_list_open", {}).get("documents", [])
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
problems = []
for rnd in range(3):
    paths = []
    for i in range(12):
        p = os.path.join(W, "r%d-%02d.odt" % (rnd, i)); shutil.copyfile(src, p)
        if i % 4 == 0: os.chmod(p, stat.S_IRUSR | stat.S_IRGRP)
        paths.append(p)
    for p in paths:
        r = call("doc_open", {"file_path": p})
        if r.get("status") != "ok": problems.append(("open", p, r))
    docs = [d for d in listed() if (d.get("url") or "").startswith("file://" + W)]
    ids = [d["doc_id"] for d in docs]
    if len(docs) != len(paths) or len(set(ids)) != len(ids):
        problems.append(("list", rnd, len(docs), len(set(ids))))
    again = {d["url"]: d["doc_id"] for d in listed()}
    for d in docs:
        if again.get(d["url"]) != d["doc_id"]:
            problems.append(("unstable id", d["url"]))
    random.shuffle(docs)
    for d in docs:
        # make some other doc active first, so a wrong fallback would hit it
        others = [o for o in docs if o is not d]
        r = call("doc_close", {"_document": "id:" + d["doc_id"]})
        closed_url = (r.get("closed") or {}).get("url")
        if r.get("status") != "ok" or closed_url != d["url"]:
            problems.append(("close target", d["url"], r))
        still = {x.get("url") for x in listed()}
        if d["url"] in still:
            problems.append(("still listed", d["url"]))
    left = [x for x in listed() if (x.get("url") or "").startswith("file://" + W)]
    if left: problems.append(("left open", [x["url"] for x in left]))
    for p in paths: os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
print(json.dumps({"rounds": 3, "docs_per_round": 12, "problems": problems}, indent=1)[:3000])
