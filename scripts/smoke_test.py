#!/usr/bin/env python3
# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Live smoke test — install the .oxt, run LibreOffice, exercise the server.

`make test` only covers pure-Python framework logic; it never starts
LibreOffice, so it cannot see the failures that actually happen. This does
the real thing: installs the built extension into a throwaway profile,
starts LibreOffice headless, and drives it over MCP.

The checks are not hypothetical. Each one is a bug that reached a release
and was caught by hand:

    #19  save_document_as overwrote the original file (data loss)
    #20  a copied file kept its doc_id, so id: targeted the wrong document
    #21  .xlsx cell comments read back empty after a reopen
    #22  an MCP edit switched change recording on for the whole document
    #11  50 read-only tools were silently reclassified as mutations

Where it can, it checks something other than the tool's own answer — the
bytes on disk, or the live document through the UNO socket. A tool
reporting on itself cannot catch a bug in how it reports.

    python3 scripts/smoke_test.py [--keep] [--port N] [--verbose]

Exit code 0 = every check passed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PORT = 8769
UNO_PORT = 2003
BOOT_TIMEOUT = 90


# ── plumbing ─────────────────────────────────────────────────────────────

class Fail(Exception):
    """A check failed."""


class Harness:
    def __init__(self, port, uno_port, verbose=False, keep=False):
        self.port = port
        self.uno_port = uno_port
        self.verbose = verbose
        self.keep = keep
        self.profile = tempfile.mkdtemp(prefix="nelson-smoke-")
        self.workdir = tempfile.mkdtemp(prefix="nelson-smoke-docs-")
        self.log_path = os.path.join(self.profile, "nelson.log")
        self.proc = None
        self._id = 0
        # Substrings of log errors a check provoked deliberately. Without
        # this the harness cannot test an error path at all: asserting a
        # clean log and asserting good error handling would contradict.
        self._expected_errors = []

    # -- lifecycle --------------------------------------------------

    def oxt(self):
        for name in ("nelson.oxt",):
            p = os.path.join(ROOT, "build", name)
            if os.path.exists(p):
                return p
        raise Fail("no build/nelson.oxt — run `make build` first")

    def install(self):
        oxt = self.oxt()
        # The Windows payload is the one packaging mistake that survives a
        # green build, so check it here too rather than only at release.
        with zipfile.ZipFile(oxt) as z:
            if not any(n.startswith("plugin/lib/pysqlite3/") for n in z.namelist()):
                raise Fail("%s has no bundled pysqlite3 — it would fail on "
                           "Windows (run scripts/fetch_sqlite3.py)" % oxt)
        unopkg = self._find("unopkg")
        self._run([unopkg, "add", "-f", oxt,
                   "-env:UserInstallation=file://%s" % self.profile])

    def launch(self):
        soffice = self._find("soffice")
        env = dict(os.environ)
        env["NELSON_LOG_PATH"] = self.log_path
        env["NELSON_SET_CONFIG"] = (
            "core.log_level=DEBUG,http.port=%d" % self.port)
        cmd = [
            soffice, "--headless", "--nologo", "--norestore", "--nolockcheck",
            "-env:UserInstallation=file://%s" % self.profile,
            "--accept=socket,host=localhost,port=%d;urp;" % self.uno_port,
        ]
        self.proc = subprocess.Popen(
            cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._wait_healthy()

    def _wait_healthy(self):
        deadline = time.time() + BOOT_TIMEOUT
        last = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        "http://localhost:%d/health" % self.port, timeout=3):
                    return
            except Exception as e:                       # not up yet
                last = e
                time.sleep(1)
        raise Fail("server never answered /health on port %d within %ds (%s)"
                   % (self.port, BOOT_TIMEOUT, last))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.keep:
            print("\nkept: profile=%s docs=%s" % (self.profile, self.workdir))
            return
        for d in (self.profile, self.workdir):
            shutil.rmtree(d, ignore_errors=True)

    # -- talking to it ----------------------------------------------

    def rpc(self, method, params=None):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id,
                           "method": method, "params": params or {}})
        req = urllib.request.Request(
            "http://localhost:%d/mcp" % self.port,
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"})
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode("utf-8"))
        if "error" in payload:
            raise Fail("%s -> %s" % (method, payload["error"]))
        return payload["result"]

    def call(self, tool, **args):
        """Call a tool and return its parsed result."""
        res = self.rpc("tools/call", {"name": tool, "arguments": args})
        content = res.get("content") or []
        if not content:
            raise Fail("%s returned no content" % tool)
        return json.loads(content[0]["text"])

    def expect_error(self, substring):
        """Tolerate log errors containing *substring* for this run."""
        self._expected_errors.append(substring)

    def reset(self):
        """Close every open document.

        Checks must not inherit each other's documents: `doc_create` returns
        before the new document is necessarily the active one, so a leftover
        document from an earlier check can absorb the next call and make the
        run non-deterministic. A flaky check is worse than no check.
        """
        for _ in range(25):
            try:
                docs = self.call("doc_list_open").get("documents") or []
            except Fail:
                return
            if not docs:
                return
            try:
                self.call("doc_close", save=False)
            except Fail:
                return

    def tool_names(self):
        return {t["name"] for t in self.rpc("tools/list")["tools"]}

    def uno_record_changes(self):
        """Read RecordChanges per document straight from LibreOffice.

        Out-of-band on purpose: Nelson exposes no tool for this on Calc, and
        a tool answering about itself proves less than an outside look.
        Returns None when the uno module is unavailable.
        """
        script = (
            "import uno\n"
            "l=uno.getComponentContext()\n"
            "c=l.ServiceManager.createInstanceWithContext("
            "'com.sun.star.bridge.UnoUrlResolver',l).resolve("
            "'uno:socket,host=localhost,port=%d;urp;StarOffice.ComponentContext')\n"
            "d=c.ServiceManager.createInstanceWithContext("
            "'com.sun.star.frame.Desktop',c)\n"
            "e=d.getComponents().createEnumeration()\n"
            "out=[]\n"
            "while e.hasMoreElements():\n"
            "    doc=e.nextElement()\n"
            "    try: out.append([doc.getURL(), bool(doc.getPropertyValue('RecordChanges'))])\n"
            "    except Exception: pass\n"
            "import json; print(json.dumps(out))\n" % self.uno_port)
        try:
            r = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True, timeout=60)
        except Exception:
            return None
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return None

    def log_errors(self):
        if not os.path.exists(self.log_path):
            return ["no log written at %s" % self.log_path]
        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            errors = [l.rstrip() for l in f if "[ERROR]" in l]
        return [e for e in errors
                if not any(x in e for x in self._expected_errors)]

    def doc(self, name):
        return os.path.join(self.workdir, name)

    # -- helpers ----------------------------------------------------

    def _find(self, binary):
        found = shutil.which(binary)
        if found:
            return found
        for p in ("/usr/lib64/libreoffice/program/", "/usr/lib/libreoffice/program/",
                  "/opt/libreoffice/program/"):
            cand = os.path.join(p, binary)
            if os.path.exists(cand):
                return cand
        raise Fail("%s not found on PATH" % binary)

    def _run(self, cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise Fail("%s failed: %s" % (cmd[0], (r.stderr or r.stdout)[:400]))
        return r.stdout


# ── the checks ───────────────────────────────────────────────────────────

def check_handshake(h):
    """initialize advertises what clients rely on."""
    res = h.rpc("initialize", {"protocolVersion": "2024-11-05",
                               "capabilities": {},
                               "clientInfo": {"name": "smoke", "version": "0"}})
    caps = res.get("capabilities", {})
    if not caps.get("tools", {}).get("listChanged"):
        raise Fail("tools.listChanged is not advertised (#24) — clients will "
                   "cache the tool list and miss the Writer/Calc switch")
    version = res.get("serverInfo", {}).get("version")
    expected = _declared_version()
    if version != expected:
        raise Fail("server reports %r, plugin/version.py says %r"
                   % (version, expected))
    return "version %s, listChanged advertised" % version


def check_tools_listed(h):
    names = h.tool_names()
    if len(names) < 20:
        raise Fail("only %d tools advertised — discovery likely broke" % len(names))
    return "%d tools with no document open" % len(names)


def check_doc_type_filtering(h):
    """The tool list narrows to the active document."""
    h.reset()
    h.call("doc_create", doc_type="writer")
    writer = h.tool_names()
    h.call("doc_create", doc_type="calc")
    calc = h.tool_names()
    if "text_read" not in writer:
        raise Fail("Writer session does not advertise text_read")
    if "text_read" in calc:
        raise Fail("Calc session advertises the Writer-only text_read")
    if "calc_sheet" not in calc:
        raise Fail("Calc session does not advertise calc_sheet")
    return "writer=%d calc=%d, correctly filtered" % (len(writer), len(calc))


def check_alias_still_resolves(h):
    """Renamed tools keep their former names callable but unadvertised (#11)."""
    h.reset()
    h.call("doc_create", doc_type="writer")
    names = h.tool_names()
    if "read_paragraphs" in names:
        raise Fail("the deprecated name read_paragraphs is being advertised")
    if "text_read" not in names:
        raise Fail("text_read is missing")
    h.call("text_insert", paragraph_index=0, text="alias check")
    old = h.call("read_paragraphs", start_index=0, count=1)
    if old.get("status") != "ok":
        raise Fail("deprecated alias read_paragraphs no longer works: %s" % old)
    return "old name callable, not advertised"


def check_mutation_classification(h):
    """Reads must not be treated as writes (#11).

    A misclassified read opens an undo context, burns an action id and — on
    older builds — switched change recording on. It is invisible unless you
    look for the action id, which is how it survived a release.
    """
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_insert", paragraph_index=0, text="mutation check")
    offenders = []
    for tool, args in (("text_read", {"start_index": 0, "count": 1}),
                       ("nav_outline", {}),
                       ("doc_info", {}),
                       ("image_list", {}),
                       ("table_list", {})):
        if "_action_id" in h.call(tool, **args):
            offenders.append(tool)
    if offenders:
        raise Fail("read-only tools classified as mutations: %s"
                   % ", ".join(offenders))
    if "_action_id" not in h.call("text_insert", paragraph_index=0, text="x"):
        raise Fail("text_insert is not classified as a mutation")
    return "5 reads clean, write still tracked"


def check_round_trip(h):
    """Write, save, reopen, read back — checked against the file itself."""
    path = h.doc("round_trip.odt")
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_insert", paragraph_index=0, text="ROUND TRIP MARKER")
    h.call("doc_save", path=path)
    if not os.path.exists(path):
        raise Fail("doc_save reported success but %s does not exist" % path)
    with zipfile.ZipFile(path) as z:                     # ground truth
        content = z.read("content.xml").decode("utf-8", "replace")
    if "ROUND TRIP MARKER" not in content:
        raise Fail("text is not in content.xml — saved file lost it")
    h.call("doc_close", save=False)
    h.call("doc_open", file_path=path)
    back = h.call("text_read", start_index=0, count=1)
    text = (back.get("paragraphs") or [{}])[0].get("text", "")
    if "ROUND TRIP MARKER" not in text:
        raise Fail("text did not survive the reopen: %r" % text)
    return "content.xml and reopen both carry the text"


def check_save_as_keeps_original(h):
    """save_document_as must not write through to the source file (#19)."""
    a, b = h.doc("original.odt"), h.doc("saved_as.odt")
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_insert", paragraph_index=0, text="ORIGINAL")
    h.call("doc_save", path=a)
    before = _digest(a)
    h.call("doc_save_as", target_path=b)
    h.call("text_insert", paragraph_index=0, text="EDITED AFTER SAVE AS")
    h.call("doc_save")
    if _digest(a) != before:
        raise Fail("the original file changed after save_as + save — #19 is back")
    if not os.path.exists(b):
        raise Fail("save_as target %s was not written" % b)
    with zipfile.ZipFile(b) as z:
        if "EDITED AFTER SAVE AS" not in z.read("content.xml").decode("utf-8", "replace"):
            raise Fail("the edit did not land in the save_as target")
    return "original untouched, edit landed in the new file"


def check_doc_ids_distinct(h):
    """A copied file must not keep the original's doc_id (#20)."""
    a, b = h.doc("id_a.odt"), h.doc("id_b.odt")
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_insert", paragraph_index=0, text="id test")
    h.call("doc_save", path=a)
    h.call("doc_close", save=False)
    shutil.copyfile(a, b)                                # byte-identical copy
    h.call("doc_open", file_path=a)
    h.call("doc_open", file_path=b)
    docs = h.call("doc_list_open").get("documents", [])
    ids = [d.get("doc_id") for d in docs if d.get("url")]
    if len(ids) != len(set(ids)):
        raise Fail("two open documents share a doc_id — #20 is back: %s" % ids)
    return "%d open documents, all ids distinct" % len(ids)


def check_recording_not_forced(h):
    """An MCP edit must not switch change recording on (#22)."""
    h.reset()
    h.call("doc_create", doc_type="calc")
    h.call("calc_write_range", start_cell="A1", values=[["recording check"]])
    state = h.uno_record_changes()
    if state is None:
        return "SKIPPED — uno module unavailable for the out-of-band check"
    on = [url or "(unsaved)" for url, rec in state if rec]
    if on:
        raise Fail("change recording was switched on by an MCP edit (#22): %s"
                   % ", ".join(on))
    return "checked %d documents via UNO, none forced into recording" % len(state)


def check_search_backends_agree(h):
    """Both search backends must see the same document (#28).

    The index used to cover body paragraphs only, so a caption inside a
    text frame was found by the direct scan and missed entirely by the
    index-backed search — which answered "nothing found" rather than
    "not covered".
    """
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_insert", paragraph_index=0, text="body mentions Kilimanjaro")
    h.call("table_create", rows=2, cols=2, paragraph_index=0)
    tables = h.call("table_list").get("tables") or []
    if tables:
        h.call("table_write_cell", table_name=tables[0]["name"],
               cell="B2", value="Zanzibar")

    direct = h.call("text_search", pattern="Kilimanjaro", backend="direct")
    if not direct.get("count"):
        raise Fail("the direct backend cannot find body text")

    idx = h.call("text_search_fulltext", query="Kilimanjaro")
    if not idx.get("total_found"):
        raise Fail("the index backend missed body text the direct one found")

    if tables:
        cell = h.call("text_search_fulltext", query="Zanzibar")
        if not cell.get("total_found"):
            raise Fail("table cell text is not indexed (#28)")

    coverage = (idx.get("index") or {}).get("searched")
    if not coverage:
        raise Fail("the index no longer reports what it searched — an empty "
                   "result must be distinguishable from 'not covered'")
    return "both backends agree; index covers %s" % ", ".join(coverage)


def check_sheet_qualified_refs(h):
    """Cross-sheet references must resolve, and land on the named sheet (#30).

    The parser had no room for a sheet prefix, so every qualified reference
    was rejected and nothing but the active sheet could be addressed. The
    part worth guarding is not that it parses but that a qualified write
    goes to the named sheet and not the active one.
    """
    h.reset()
    h.call("doc_create", doc_type="calc")
    h.call("calc_sheet", action="create", sheet_name="Summary")
    h.call("calc_sheet", action="create", sheet_name="Data Sheet")

    h.call("calc_write_range", start_cell="Summary.B2", values=[["MARKER"]])

    for ref in ("Summary.B2", "Summary.B2:B2", "'Summary'.B2", "Summary!B2"):
        got = h.call("calc_read_range", range_name=ref)
        if got.get("status") != "ok":
            raise Fail("%s was rejected: %s" % (ref, got.get("error")))
        cell = got["result"][0][0]
        if cell.get("value") != "MARKER":
            raise Fail("%s read %r, expected MARKER — it resolved the wrong "
                       "sheet" % (ref, cell.get("value")))

    # The write must not have touched the active sheet.
    active = h.call("calc_read_range", range_name="B2")["result"][0][0]
    if active.get("value"):
        raise Fail("a sheet-qualified write also landed on the active sheet: "
                   "%r" % active.get("value"))

    # A quoted name with a space, and a chart over data on another sheet.
    h.call("calc_write_range", start_cell="'Data Sheet'.A1",
           values=[["a", 1], ["b", 2]])
    chart = h.call("calc_chart", action="create",
                   data_range="'Data Sheet'.A1:B2", chart_type="bar")
    if chart.get("status") != "ok":
        raise Fail("a chart over another sheet's data failed: %s" % chart)

    h.expect_error("No sheet named 'Nope'")
    bad = h.call("calc_read_range", range_name="Nope.A1")
    if bad.get("status") == "ok":
        raise Fail("an unknown sheet was accepted")
    return "4 syntaxes resolve, write stays on its sheet, cross-sheet chart ok"


def check_log_clean(h):
    errors = h.log_errors()
    if errors:
        raise Fail("%d error(s) in the log:\n    %s"
                   % (len(errors), "\n    ".join(errors[:5])))
    return "no errors logged"


CHECKS = [
    ("handshake", check_handshake),
    ("tools listed", check_tools_listed),
    ("doc-type filtering", check_doc_type_filtering),
    ("deprecated aliases", check_alias_still_resolves),
    ("mutation classification", check_mutation_classification),
    ("document round-trip", check_round_trip),
    ("save-as keeps original", check_save_as_keeps_original),
    ("doc_id uniqueness", check_doc_ids_distinct),
    ("recording not forced", check_recording_not_forced),
    ("search backends agree", check_search_backends_agree),
    ("sheet-qualified refs", check_sheet_qualified_refs),
    ("log clean", check_log_clean),          # last: sees everything above
]


# ── helpers ──────────────────────────────────────────────────────────────

def _declared_version():
    ns = {}
    with open(os.path.join(ROOT, "plugin", "version.py"), encoding="utf-8") as f:
        exec(f.read(), ns)                               # noqa: S102
    return ns["EXTENSION_VERSION"]


def _digest(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ── main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--uno-port", type=int, default=UNO_PORT)
    ap.add_argument("--keep", action="store_true",
                    help="keep the profile and documents for inspection")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    h = Harness(args.port, args.uno_port, args.verbose, args.keep)
    print("Nelson smoke test — profile %s" % h.profile)

    failures = []
    try:
        print("  installing extension ...", flush=True)
        h.install()
        print("  starting LibreOffice headless ...", flush=True)
        h.launch()
        print("  server up on port %d\n" % h.port, flush=True)

        for name, fn in CHECKS:
            try:
                detail = fn(h)
                print("  PASS  %-26s %s" % (name, detail or ""))
            except Fail as e:
                failures.append((name, str(e)))
                print("  FAIL  %-26s %s" % (name, e))
            except Exception as e:                       # unexpected
                failures.append((name, "%s: %s" % (type(e).__name__, e)))
                print("  ERROR %-26s %s: %s" % (name, type(e).__name__, e))
    except Fail as e:
        print("\nsetup failed: %s" % e)
        h.stop()
        return 2
    finally:
        if not failures:
            h.stop()

    if failures:
        print("\n%d of %d checks failed:" % (len(failures), len(CHECKS)))
        for name, why in failures:
            print("  - %s: %s" % (name, why))
        h.stop()
        return 1

    print("\nall %d checks passed" % len(CHECKS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
