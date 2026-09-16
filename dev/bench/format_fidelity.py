#!/usr/bin/env python3
"""format_fidelity — what survives reading a document out and writing it back.

    format_fidelity.py [DOC ...]

For each document and each exchange format (html, markdown), through Nelson
exactly as an agent would:

  1. open a fresh copy, count what it holds (over UNO, outside Nelson);
  2. text_get_range scope=full in that format (max 500 000 characters);
  3. text_apply_range target=full with that content, in that format;
  4. count again, and report what changed.

Also times the export of each document in each format, three times.

With no argument it builds a small "rich" document first — colours, fonts,
underline, a footnote, a comment, a hyperlink, a table with merged cells —
because the bench documents do not carry all of those. Talks to the wbox dev
instance: Nelson on 8767 (via nb.py), UNO on 2002. Results go to
results/format-fidelity-<stamp>.json.
"""

import json
import os
import shutil
import sys
import time

import uno
from com.sun.star.beans import PropertyValue

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work", "fidelity")
RESULTS = os.path.join(HERE, "results")
sys.path.insert(0, HERE)
import nb  # noqa: E402  (the tracer: its HTTP client and port)


def pv(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def desktop():
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    ctx = resolver.resolve(
        "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
    return ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)


def call(tool, args):
    """Call a Nelson tool and return its parsed result (no printing, no
    argv limits: documents are hundreds of kilobytes)."""
    payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 10**9,
               "method": "tools/call",
               "params": {"name": tool, "arguments": args}}
    msg = json.loads(nb._post(payload, 300))
    if "error" in msg:
        return {"status": "rpc_error", "error": msg["error"]}
    text = (msg["result"].get("content") or [{}])[0].get("text", "")
    try:
        return json.loads(text)
    except ValueError:
        return {"status": "non_json", "text": text[:200]}


def find(desk, path):
    url = uno.systemPathToFileUrl(path)
    comps = desk.getComponents().createEnumeration()
    while comps.hasMoreElements():
        c = comps.nextElement()
        try:
            if c.getURL() == url:
                return c
        except Exception:
            continue
    return None


def census(doc):
    """What a document holds that an agent's round trip could lose."""
    out = {"characters": 0, "paragraphs": 0, "headings": 0, "tables": 0,
           "merged_cells": 0, "footnotes": 0, "comments": 0, "links": 0,
           "bold_runs": 0, "italic_runs": 0, "underline_runs": 0,
           "coloured_runs": 0, "fonts": set(), "list_paragraphs": 0,
           "images": 0}
    text = doc.getText()
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        el = enum.nextElement()
        if not el.supportsService("com.sun.star.text.Paragraph"):
            continue
        out["paragraphs"] += 1
        out["characters"] += len(el.getString())
        if el.getPropertyValue("OutlineLevel") > 0:
            out["headings"] += 1
        try:
            if el.getPropertyValue("NumberingRules") is not None and \
                    el.getPropertyValue("NumberingIsNumber"):
                out["list_paragraphs"] += 1
        except Exception:
            pass
        portions = el.createEnumeration()
        while portions.hasMoreElements():
            r = portions.nextElement()
            if not r.getString().strip():
                continue
            if r.getPropertyValue("CharWeight") >= 150:
                out["bold_runs"] += 1
            if uno.Enum("com.sun.star.awt.FontSlant", "ITALIC") == \
                    r.getPropertyValue("CharPosture"):
                out["italic_runs"] += 1
            if r.getPropertyValue("CharUnderline") != 0:
                out["underline_runs"] += 1
            if r.getPropertyValue("CharColor") not in (-1, 0):
                out["coloured_runs"] += 1
            if r.getPropertyValue("HyperLinkURL"):
                out["links"] += 1
            out["fonts"].add(r.getPropertyValue("CharFontName"))
    tables = doc.getTextTables()
    out["tables"] = tables.getCount()
    for i in range(tables.getCount()):
        t = tables.getByIndex(i)
        names = t.getCellNames()
        rows = t.getRows().getCount()
        cols = t.getColumns().getCount()
        out["merged_cells"] += max(0, rows * cols - len(names))
    out["footnotes"] = doc.getFootnotes().getCount()
    try:
        out["images"] = doc.getGraphicObjects().getCount()
    except Exception:
        pass
    fields = doc.getTextFields().createEnumeration()
    while fields.hasMoreElements():
        if fields.nextElement().supportsService(
                "com.sun.star.text.textfield.Annotation"):
            out["comments"] += 1
    out["fonts"] = sorted(out["fonts"])
    return out


def build_rich(desk, path):
    doc = desk.loadComponentFromURL("private:factory/swriter", "_blank", 0,
                                    (pv("Hidden", True),))
    text = doc.getText()
    cur = text.createTextCursor()

    def para(s, style="Text body", **props):
        cur.gotoEnd(False)
        cur.setPropertyValue("ParaStyleName", style)
        start = cur.getEnd()
        text.insertString(cur, s, False)
        rng = text.createTextCursorByRange(start)
        rng.gotoEnd(True)
        for k, v in props.items():
            rng.setPropertyValue(k, v)
        cur.gotoEnd(False)
        text.insertControlCharacter(cur, 0, False)

    para("Rich document", "Heading 1")
    para("Red text in a serif font.", CharColor=0xCC0000,
         CharFontName="Liberation Serif")
    para("Bold words.", CharWeight=150.0)
    para("Italic words.",
         CharPosture=uno.Enum("com.sun.star.awt.FontSlant", "ITALIC"))
    para("Underlined words.", CharUnderline=1)
    para("A link to example.org.", HyperLinkURL="https://example.org")
    para("Section two", "Heading 2")
    para("Paragraph with a footnote.")
    cur.gotoEnd(False)
    note = doc.createInstance("com.sun.star.text.Footnote")
    text.insertTextContent(cur, note, False)
    note.getText().setString("The footnote text.")
    text.insertControlCharacter(cur, 0, False)
    para("Paragraph with a comment.")
    cur.gotoEnd(False)
    ann = doc.createInstance("com.sun.star.text.textfield.Annotation")
    ann.Content = "A reviewer's comment."
    ann.Author = "Reviewer"
    text.insertTextContent(cur, ann, False)
    text.insertControlCharacter(cur, 0, False)
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(3, 3)
    cur.gotoEnd(False)
    text.insertTextContent(cur, table, False)
    for name, value in (("A1", "Region"), ("B1", "Q1"), ("C1", "Q2"),
                        ("A2", "North"), ("B2", "3"), ("C2", "4"),
                        ("A3", "Total"), ("B3", "7")):
        table.getCellByName(name).setString(value)
    tc = table.createCursorByCellName("B3")
    tc.goRight(1, True)
    tc.mergeRange()
    para("End.")
    doc.storeToURL(uno.systemPathToFileUrl(path),
                   (pv("FilterName", "writer8"),))
    # Left open on purpose: closing a document over UNO while LibreOffice
    # updates its menus aborted it (dev/bugs/writer-crash-after-external-close.md).
    return doc


def export_times(path):
    """Seconds for text_get_range scope=full, three runs per format — what an
    agent waits for — on a fresh copy opened through Nelson."""
    copy = os.path.join(WORK, "timing" + os.path.splitext(path)[1])
    shutil.copyfile(path, copy)
    call("doc_open", {"file_path": copy})
    time.sleep(5)                     # let LibreOffice finish laying it out
    out = {}
    try:
        for fmt in ("html", "markdown"):
            runs, size = [], 0
            for _ in range(3):
                t = time.time()
                got = call("text_get_range", {"_document": "path:" + copy,
                                              "scope": "full", "format": fmt,
                                              "max_chars": 500000})
                runs.append(round(time.time() - t, 2))
                size = got.get("content_total_length") or got.get("length")
            out[fmt] = {"seconds": runs, "characters": size}
    finally:
        call("doc_close", {"_document": "path:" + copy})
    return out


def diff(before, after):
    lost = {}
    for k, v in before.items():
        w = after.get(k)
        if k == "fonts":
            gone = sorted(set(v) - set(w or []))
            if gone:
                lost[k] = gone
        elif v != w:
            lost[k] = [v, w]
    return lost


def round_trip(desk, source, fmt):
    name = "%s-%s%s" % (os.path.splitext(os.path.basename(source))[0], fmt,
                        os.path.splitext(source)[1])
    path = os.path.join(WORK, name)
    shutil.copyfile(source, path)
    opened = call("doc_open", {"file_path": path})
    doc = find(desk, path)
    if doc is None:
        return {"error": "not open: %s" % opened}
    before = census(doc)
    got = call("text_get_range", {"_document": "path:" + path,
                                  "scope": "full", "format": fmt,
                                  "max_chars": 500000})
    content = got.get("content", "")
    applied = call("text_apply_range", {"_document": "path:" + path,
                                        "target": "full", "format": fmt,
                                        "content": content})
    after = census(find(desk, path))
    call("doc_close", {"_document": "path:" + path})
    return {"read_bytes": len(content.encode("utf-8")),
            "read_truncated": got.get("truncated"),
            "apply_status": applied.get("status"),
            "before": before, "after": after,
            "changed": diff(before, after)}


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    desk = desktop()
    docs = sys.argv[1:]
    if not docs:
        rich = os.path.join(WORK, "rich.odt")
        builder = build_rich(desk, rich)  # noqa: F841  (kept open)
        docs = [rich, os.path.join(HERE, "docs", "gdpr.docx")]
    report = {}
    for source in docs:
        source = os.path.abspath(source)
        entry = {"export": export_times(source)}
        for fmt in ("html", "markdown"):
            entry[fmt] = round_trip(desk, source, fmt)
        report[os.path.basename(source)] = entry
        print(os.path.basename(source), flush=True)
        for fmt in ("html", "markdown"):
            r = entry[fmt]
            print("  %-8s read %s B, changed: %s" % (
                fmt, r.get("read_bytes"), json.dumps(r.get("changed"))))
        print("  export  ", json.dumps(entry["export"]))
    out = os.path.join(RESULTS, "format-fidelity-%s.json"
                       % time.strftime("%Y%m%d-%H%M%S"))
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print("->", out)


if __name__ == "__main__":
    main()
