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
    CORS any web page could drive LibreOffice through the MCP endpoint
    #38  a stale session got 409, so no client ever re-initialized by itself
    #34  the call right after doc_open targeted no document, or the previous one

Where it can, it checks something other than the tool's own answer — the
bytes on disk, or the live document through the UNO socket. A tool
reporting on itself cannot catch a bug in how it reports.

    python3 scripts/smoke_test.py [--keep] [--port N] [--verbose] [--wbox]

`--wbox` runs LibreOffice with its real GUI inside a nested wbox compositor
instead of `soffice --headless`. Headless mode never starts the VCL event loop,
so it cannot see what depends on it — the cold-start dispatch behind #35/#37,
the first-document race of #34. The compositor is offscreen by default; set
WBOX_VISIBLE=1 to watch it.

Exit code 0 = every check passed.
"""

import argparse
import json
import re
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
WBOX_INSTANCE = "nelson-smoke"


def _wbox_python():
    """The interpreter wbox is installed under — it is not the system one."""
    explicit = os.environ.get("WBOX_PYTHON")
    if explicit:
        return explicit
    launcher = shutil.which("wbox-mcp")
    if launcher:
        with open(launcher, encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
        if first.startswith("#!"):
            return first[2:].split()[0]
    raise RuntimeError("wbox not found: install wbox-mcp or set WBOX_PYTHON")


# ── plumbing ─────────────────────────────────────────────────────────────

class Fail(Exception):
    """A check failed."""


class Harness:
    def __init__(self, port, uno_port, verbose=False, keep=False, wbox=False):
        self.port = port
        self.uno_port = uno_port
        self.verbose = verbose
        self.keep = keep
        self.wbox = wbox
        self.wbox_config = None
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
        if self.wbox:
            # A GUI LibreOffice on a fresh profile opens the first-run wizard
            # and blocks. Seed before unopkg touches the profile, while the
            # registry file does not exist yet and nothing can be lost.
            self._run([sys.executable,
                       os.path.join(ROOT, "dev", "lo-wbox", "scripts",
                                    "seed_registry.py"), self.profile])
        unopkg = self._find("unopkg")
        self._run([unopkg, "add", "-f", oxt,
                   "-env:UserInstallation=file://%s" % self.profile])

    def launch(self):
        soffice = self._find("soffice")
        env = dict(os.environ)
        env["NELSON_LOG_PATH"] = self.log_path
        # The config API lets check_auth_token turn the token on and off live
        # on this throwaway instance, so every other check still runs against
        # the default, token-less configuration most users have.
        env["NELSON_SET_CONFIG"] = (
            "core.log_level=DEBUG,http.port=%d,http.enable_config_api=true"
            % self.port)
        cmd = [
            soffice, "--nologo", "--norestore", "--nolockcheck",
            "-env:UserInstallation=file://%s" % self.profile,
            "--accept=socket,host=localhost,port=%d;urp;" % self.uno_port,
        ]
        if self.wbox:
            self._wbox_up(cmd, env)
        else:
            cmd.insert(1, "--headless")
            self.proc = subprocess.Popen(
                cmd, env=env, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        self._wait_healthy()

    def _wbox(self, action):
        ctl = os.path.join(ROOT, "scripts", "wbox_ctl.py")
        r = subprocess.run([_wbox_python(), ctl, action, self.wbox_config],
                           capture_output=True, text=True, timeout=120)
        if self.verbose or r.returncode != 0:
            print("    wbox %s: %s%s" % (action, r.stdout.strip(),
                                       r.stderr.strip()))
        return r

    def _wbox_up(self, cmd, env):
        # JSON is valid YAML, and it sidesteps quoting the ';' and ':' in the
        # soffice arguments. Only the variables Nelson reads are passed: wbox
        # builds the rest of the environment for the nested session itself.
        config = {
            "name": WBOX_INSTANCE,
            "compositor": "labwc",
            "screen": "1280x800",
            "input_backend": "hybrid",
            "app": {
                "command": cmd,
                "env": {k: env[k] for k in
                        ("NELSON_LOG_PATH", "NELSON_SET_CONFIG")},
            },
        }
        self.wbox_config = os.path.join(self.profile, "wbox.yaml")
        with open(self.wbox_config, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        self._wbox("down")               # a previous run may have crashed
        if self._wbox("up").returncode != 0:
            raise Fail("wbox could not start the compositor")

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
        if self.wbox and self.wbox_config:
            self._wbox("down")
            # A hung soffice.bin outlives the compositor that launched it.
            subprocess.run(["pkill", "-9", "-f",
                            "UserInstallation=file://%s" % self.profile],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def uno_append_heading(self, url_suffix, text):
        """Append a Heading 1 to an open document, from outside Nelson.

        Stands in for the user typing in the GUI: Nelson's caches must see
        a change no tool made. Returns False when uno is unavailable.
        """
        script = (
            "import uno, sys\n"
            "l=uno.getComponentContext()\n"
            "c=l.ServiceManager.createInstanceWithContext("
            "'com.sun.star.bridge.UnoUrlResolver',l).resolve("
            "'uno:socket,host=localhost,port=%d;urp;StarOffice.ComponentContext')\n"
            "d=c.ServiceManager.createInstanceWithContext("
            "'com.sun.star.frame.Desktop',c)\n"
            "e=d.getComponents().createEnumeration()\n"
            "while e.hasMoreElements():\n"
            "    doc=e.nextElement()\n"
            "    if doc.getURL().endswith(%r):\n"
            "        t=doc.getText(); cur=t.createTextCursor(); cur.gotoEnd(False)\n"
            "        t.insertControlCharacter(cur, 0, False)\n"
            "        cur.setPropertyValue('ParaStyleName', 'Heading 1')\n"
            "        t.insertString(cur, %r, False)\n"
            "        print('ok'); sys.exit(0)\n"
            "print('missing'); sys.exit(2)\n" % (self.uno_port, url_suffix, text))
        try:
            r = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True, timeout=60)
        except Exception:
            return False
        return r.returncode == 0

    def uno_run(self, body):
        """Run *body* in a Python connected to LibreOffice over UNO.

        *body* sees ``desktop`` and prints one JSON line. Returns the parsed
        value, or None when uno is unavailable or the script failed.
        """
        script = (
            "import uno, json\n"
            "from com.sun.star.beans import PropertyValue\n"
            "l=uno.getComponentContext()\n"
            "c=l.ServiceManager.createInstanceWithContext("
            "'com.sun.star.bridge.UnoUrlResolver',l).resolve("
            "'uno:socket,host=localhost,port=%d;urp;StarOffice.ComponentContext')\n"
            "desktop=c.ServiceManager.createInstanceWithContext("
            "'com.sun.star.frame.Desktop',c)\n" % self.uno_port) + body
        self.uno_last_error = None
        try:
            r = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                self.uno_last_error = (r.stderr.strip().splitlines() or ["?"])[-1]
                return None
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as e:
            self.uno_last_error = str(e)
            return None

    def set_config(self, key, value):
        """Change a setting live through /api/config (smoke enables it)."""
        req = urllib.request.Request(
            "http://localhost:%d/api/config" % self.port, method="POST",
            data=json.dumps({key: value}).encode())
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                raise Fail("setting %s returned %s" % (key, r.status))

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


def check_open_is_active(h):
    """#34: the document doc_open returns is the one the next call targets.

    Opened as the first document, so the Start Center is the current
    component when doc_open starts — the case that raced. The very next call
    names no document, exactly as braklo's failing sequence did.
    """
    path = h.doc("open_active.odt")
    h.reset()
    h.call("doc_create", doc_type="writer", path=path)
    h.reset()
    opened = h.call("doc_open", file_path=path)
    if opened.get("status") != "ok":
        raise Fail("doc_open failed: %s" % opened)
    info = h.call("doc_info")
    if info.get("status") != "ok":
        raise Fail("call right after doc_open failed: %s" % info)
    want = opened.get("file_url")
    if info.get("file_url") != want:
        raise Fail("call right after doc_open targeted %r, not the document "
                   "just opened (%r)" % (info.get("file_url"), want))
    if "warning" in opened:
        raise Fail("doc_open says the document is not active: %s"
                   % opened["warning"])
    # One document per answer: _resolved used to name whatever was active
    # before the call, next to the new document's doc_id (#2626).
    resolved = (opened.get("_resolved") or {}).get("doc_id")
    if resolved is not None and resolved != opened.get("doc_id"):
        raise Fail("doc_open names two documents: doc_id %s, _resolved %s"
                   % (opened.get("doc_id"), resolved))
    closed = h.call("doc_close")
    if (closed.get("_resolved") or {}).get("doc_id") != info.get(
            "_resolved", {}).get("doc_id"):
        raise Fail("doc_close's _resolved is not the document it closed: %s"
                   % closed.get("_resolved"))
    return "first opened document is the active one; one document per answer"


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


def check_origin_rejected(h):
    """A browser page must not be able to drive LibreOffice.

    The server binds to localhost, which protects nothing by itself: a page
    the user happens to be visiting can POST to the MCP endpoint. What stops
    it is Origin validation plus never answering `Allow-Origin: *`, which the
    MCP Streamable HTTP spec requires. A unit test cannot see this — it is a
    property of the real HTTP response.
    """
    url = "http://localhost:%d/mcp" % h.port
    evil = "https://evil.example"
    body = json.dumps({"jsonrpc": "2.0", "id": 9001,
                       "method": "tools/list", "params": {}}).encode("utf-8")

    def send(method, origin):
        req = urllib.request.Request(url, method=method)
        if method == "POST":
            req.data = body
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json, text/event-stream")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.headers

    status, headers = send("POST", evil)
    if status != 403:
        raise Fail("POST from %s returned %s, expected 403" % (evil, status))
    if headers.get("Access-Control-Allow-Origin"):
        raise Fail("refused origin still got Allow-Origin: %s"
                   % headers.get("Access-Control-Allow-Origin"))

    pre_status, pre_headers = send("OPTIONS", evil)
    if pre_status != 403:
        raise Fail("preflight from %s returned %s, expected 403"
                   % (evil, pre_status))
    if pre_headers.get("Access-Control-Allow-Origin"):
        raise Fail("refused preflight still got Allow-Origin")

    # The contrast that matters: an MCP client sends no Origin and is fine.
    ok_status, ok_headers = send("POST", None)
    if ok_status != 200:
        raise Fail("POST without Origin returned %s, expected 200" % ok_status)
    if ok_headers.get("Access-Control-Allow-Origin") == "*":
        raise Fail("server still answers Allow-Origin: *")

    h.expect_error("Rejected")
    return "browser origin refused (403), MCP client unaffected"


def check_session_semantics(h):
    """#38: a restarted server must tell clients to re-initialize.

    A session id from before a LibreOffice restart used to get 409, which no
    client acts on — so every client stayed silently dead. The Streamable HTTP
    spec makes 404 the signal a client MUST answer with a fresh initialize.
    """
    url = "http://localhost:%d/mcp" % h.port
    stale = "00000000-dead-beef-0000-000000000000"

    def send(method, session, rpc_method=None):
        req = urllib.request.Request(url, method=method)
        if rpc_method:
            req.data = json.dumps({"jsonrpc": "2.0", "id": 9002,
                                   "method": rpc_method,
                                   "params": {}}).encode("utf-8")
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json, text/event-stream")
        if session:
            req.add_header("Mcp-Session-Id", session)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    status = send("POST", stale, "tools/list")
    if status != 404:
        raise Fail("stale session on tools/list returned %s, expected 404 "
                   "(clients only re-initialize on 404)" % status)

    # The recovery the 404 asks for has to actually work on the same URL.
    status = send("POST", stale, "initialize")
    if status != 200:
        raise Fail("initialize carrying a stale session returned %s, "
                   "expected 200" % status)

    # One session id serves every client: DELETE must not pretend to end it.
    status = send("DELETE", stale)
    if status != 405:
        raise Fail("DELETE /mcp returned %s, expected 405" % status)

    return "stale session 404, re-initialize 200, DELETE 405"


def check_auth_token(h):
    """Once an access token is set, nothing gets in without it.

    Set live through the config API, so this also proves the token applies
    without a restart. Restored at the end: the checks after this one, and the
    default configuration, are token-less.
    """
    base = "http://localhost:%d" % h.port
    token = "smoke-%s" % os.urandom(8).hex()
    body = json.dumps({"jsonrpc": "2.0", "id": 9003, "method": "tools/list",
                       "params": {}}).encode("utf-8")

    def send(path, authorization=None, method="POST", data=body):
        req = urllib.request.Request(base + path, method=method)
        if data is not None:
            req.data = data
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json, text/event-stream")
        if authorization:
            req.add_header("Authorization", authorization)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def set_token(value, authorization=None):
        status = send("/api/config", authorization,
                      data=json.dumps({"http.auth_token": value}).encode())
        if status != 200:
            raise Fail("setting http.auth_token through /api/config returned "
                       "%s" % status)

    if send("/mcp") != 200:
        raise Fail("default configuration should need no token")

    set_token(token)
    try:
        bearer = "Bearer %s" % token
        results = {
            "no token": send("/mcp"),
            "wrong token": send("/mcp", "Bearer wrong"),
            "bearer": send("/mcp", bearer),
            "query token": send("/mcp?token=%s" % token),
            "health, no token": send("/health", method="GET", data=None),
        }
        expected = {"no token": 401, "wrong token": 401, "bearer": 200,
                    "query token": 200, "health, no token": 401}
        wrong = {k: v for k, v in results.items() if v != expected[k]}
        if wrong:
            raise Fail("with a token set: %s (expected %s)"
                       % (wrong, {k: expected[k] for k in wrong}))
    finally:
        set_token("", "Bearer %s" % token)

    if send("/mcp") != 200:
        raise Fail("clearing the token did not reopen the server to local "
                   "clients")
    h.expect_error("Rejected unauthenticated")
    return "401 without it, 200 with header or ?token=, applied live"


def check_heading_bookmarks(h):
    """#2644: navigation's _mcp_ bookmarks obey writer.nav.heading_bookmarks.

    For each value, navigate a saved document, then save it again and look
    inside the file. Navigation must never mark the document modified, and
    only `keep` may leave _mcp_ bookmarks in content.xml.
    """
    base = "http://localhost:%d" % h.port
    html = "<h1>One</h1><p>a</p><h2>Two</h2><p>b</p><h1>Three</h1><p>c</p>"

    def set_mode(value):
        req = urllib.request.Request(
            base + "/api/config", method="POST",
            data=json.dumps({"writer.nav.heading_bookmarks": value}).encode())
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                raise Fail("setting heading_bookmarks returned %s" % r.status)

    def bookmarks(tree):
        return [c.get("bookmark") for c in tree.get("children", [])]

    seen = {}
    try:
        for mode in ("strip_on_save", "keep", "off"):
            set_mode(mode)
            path = h.doc("bookmarks_%s.odt" % mode)
            h.reset()
            h.call("doc_create", doc_type="writer", path=path)
            h.call("text_apply_range", target="full", content=html)
            h.call("doc_save")
            if h.call("doc_info").get("is_modified"):
                raise Fail("%s: document still modified right after saving"
                           % mode)
            first = bookmarks(h.call("nav_tree"))
            if h.call("doc_info").get("is_modified"):
                raise Fail("%s: navigating marked the document modified"
                           % mode)
            if mode == "off":
                if any(first):
                    raise Fail("off: nav_tree created bookmarks %s" % first)
            elif not all(first):
                raise Fail("%s: headings got no bookmark: %s" % (mode, first))
            h.call("text_insert", paragraph_index=1, text="edit")
            h.call("doc_save")
            with zipfile.ZipFile(path) as z:
                in_file = z.read("content.xml").decode("utf-8", "replace") \
                    .count('text:name="_mcp_')
            after = bookmarks(h.call("nav_tree"))
            if h.call("doc_info").get("is_modified"):
                raise Fail("%s: document modified after save + navigation"
                           % mode)
            if mode != "off" and after != first:
                raise Fail("%s: bookmark names changed across a save: %s -> %s"
                           % (mode, first, after))
            h.call("doc_close", save=False)
            want_in_file = 3 if mode == "keep" else 0
            if in_file != want_in_file:
                raise Fail("%s: %d _mcp_ bookmark(s) in the saved file, "
                           "expected %d" % (mode, in_file, want_in_file))
            seen[mode] = in_file
    finally:
        set_mode("strip_on_save")
    return "in file: %s; never modified, names stable across saves" % seen


def check_calc_sheet_targets(h):
    """Writes and charts go where the caller said (#31, #32, #33).

    #33: a prefix that disagrees with sheet_name is refused on the write
    paths too, an unknown sheet lists the real ones, and a single-cell read
    echoes a clean address. #31: a chart lands on the active sheet (or
    sheet_name), whatever sheet its data is on. #32: charts on two sheets get
    distinct names instead of an empty error.
    """
    h.reset()
    h.call("doc_create", doc_type="calc")
    h.call("calc_sheet", action="create", sheet_name="Summary")
    h.call("calc_sheet", action="create", sheet_name="Data Sheet")
    h.call("calc_write_range", start_cell="'Data Sheet'.A1",
           values=[["a", 1], ["b", 2], ["c", 3]])

    clash = h.call("calc_write_range", start_cell="Summary.B4",
                   values=[["CONFLICT"]], sheet_name="Data Sheet")
    if clash.get("status") == "ok":
        raise Fail("#33: calc_write_range accepted a prefix that disagrees "
                   "with sheet_name")
    for sheet in ("Summary", "Data Sheet"):
        got = h.call("calc_read_range", range_name="'%s'.B4" % sheet)
        if got["result"][0][0].get("value"):
            raise Fail("#33: the refused write still landed on %s" % sheet)
    note = h.call("calc_comment", action="add", cell="Summary.C2",
                  text="conflict", sheet_name="Data Sheet")
    if note.get("status") == "ok":
        raise Fail("#33: calc_comment accepted a prefix that disagrees with "
                   "sheet_name")
    missing = h.call("calc_write_range", start_cell="Nope.A1", values=[["x"]])
    if "Available" not in json.dumps(missing):
        raise Fail("#33: an unknown sheet on write does not list the sheets: "
                   "%s" % missing)
    addr = h.call("calc_read_range", range_name="'Data Sheet'.B2")
    if addr["result"][0][0].get("address") != "B2":
        raise Fail("#33: single-cell read echoes %r, expected 'B2'"
                   % addr["result"][0][0].get("address"))

    h.call("calc_sheet", action="switch", sheet_name="Summary")
    first = h.call("calc_chart", action="create", chart_type="bar",
                   data_range="'Data Sheet'.A1:B3", position="D1")
    if first.get("status") != "ok":
        raise Fail("#31: cross-sheet chart failed: %s" % first)

    def names(sheet):
        listed = h.call("calc_chart", action="list", sheet_name=sheet)
        return [c["name"] for c in listed.get("charts", [])]

    if names("Summary") != [first.get("chart_name")] or names("Data Sheet"):
        raise Fail("#31: chart over 'Data Sheet' data should be on the active "
                   "sheet Summary only; got Summary=%s, Data Sheet=%s"
                   % (names("Summary"), names("Data Sheet")))

    second = h.call("calc_chart", action="create", chart_type="line",
                    data_range="A1:B3", sheet_name="Data Sheet")
    if second.get("status") != "ok":
        raise Fail("#32: a chart on a second sheet failed: %s" % second)
    if second.get("chart_name") == first.get("chart_name"):
        raise Fail("#32: both charts are named %s" % first.get("chart_name"))
    if names("Data Sheet") != [second.get("chart_name")]:
        raise Fail("#31: sheet_name did not place the chart: Data Sheet=%s"
                   % names("Data Sheet"))
    h.expect_error("No sheet named 'Nope'")
    return ("conflicts refused, sheets listed, clean address; charts on "
            "the sheet asked for, names %s/%s"
            % (first.get("chart_name"), second.get("chart_name")))


def check_close_reports_truth(h):
    """doc_close closes the document it is aimed at, and says which (#36).

    Aimed at a document that is not the active one, it must close that one
    and leave the active one open; and it must never report ok for a
    document it did not close.
    """
    a, b = h.doc("close_a.odt"), h.doc("close_b.odt")
    h.reset()
    h.call("doc_create", doc_type="writer", path=a)
    h.call("doc_create", doc_type="writer", path=b)
    h.call("doc_open", file_path=a)                  # A active, B behind

    closed = h.call("doc_close", _document="path:%s" % b)
    if closed.get("status") != "ok":
        raise Fail("closing B failed: %s" % closed)
    closed_url = (closed.get("closed") or {}).get("url") or ""
    if not closed_url.endswith("close_b.odt"):
        raise Fail("doc_close does not say it closed B: %s" % closed)
    urls = [d.get("url") or "" for d in
            h.call("doc_list_open").get("documents", [])]
    if any(u.endswith("close_b.odt") for u in urls):
        raise Fail("B is still open after doc_close reported closing it")
    if not any(u.endswith("close_a.odt") for u in urls):
        raise Fail("doc_close aimed at B closed A instead: open=%s" % urls)

    again = h.call("doc_close", _document="path:%s" % b)
    if again.get("status") == "ok":
        raise Fail("closing an already closed document reported ok: %s"
                   % again)
    return "closed the document aimed at, said so, refused a second close"


def check_heading_content_duplicates(h):
    """nav_heading_content reads the heading asked for, not its namesake.

    It used to walk to the heading by path and then look its title up again,
    so the second "Notes" section returned the first one's text (#2626).
    """
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_apply_range", target="full", content=(
        "<h1>Chapter 1</h1><h2>Notes</h2><p>first notes</p>"
        "<h1>Chapter 2</h1><h2>Notes</h2><p>second notes</p>"))
    out = h.call("nav_outline").get("outline", [])
    try:
        second = out[1]["children"][0]
    except (IndexError, KeyError):
        raise Fail("unexpected outline: %s" % out)
    if second.get("path") != "2.1" or second.get("para_index") is None:
        raise Fail("nav_outline gives no usable path/para_index: %s" % second)
    got = h.call("nav_heading_content", heading_path=second["path"])
    text = " ".join(got.get("paragraphs", []))
    if "second notes" not in text or "first notes" in text:
        raise Fail("path %s returned %r — the other 'Notes' section"
                   % (second["path"], text))
    amb = h.call("nav_heading_content", heading_path="Notes")
    if amb.get("status") == "ok" or "2.1" not in json.dumps(amb):
        raise Fail("an ambiguous title should list the paths: %s" % amb)
    return "path 2.1 reads the second 'Notes'; ambiguous title lists paths"


def check_caches_follow_the_document(h):
    """Caches serve the right document and see edits made outside Nelson.

    The paragraph cache was keyed by the id() of pyuno proxies, which
    Python reuses, and no change ever reached the heading-tree and
    search-index caches (#2642). Churn through documents, then check a
    fresh one is read correctly, and that an edit made over UNO — as the
    user would in the GUI — shows up in nav_tree and the full-text index.
    """
    h.reset()
    for i in range(30):
        h.call("doc_create", doc_type="writer")
        h.call("text_insert", paragraph_index=0, text="churn %d decoy" % i)
        h.call("text_search", pattern="decoy")
        h.call("doc_close")
    h.call("doc_create", doc_type="writer")
    h.call("text_apply_range", target="full",
           content="<p>needle one</p><p>hay</p><p>needle two</p>")
    found = h.call("text_search", pattern="needle").get("count")
    if found != 2:
        raise Fail("after 30 open/close cycles, text_search counts %r "
                   "'needle', expected 2" % found)
    if h.call("text_search", pattern="decoy").get("count"):
        raise Fail("text_search found a closed document's text")

    path = h.doc("outside_edit.odt")
    h.call("doc_create", doc_type="writer", path=path)
    h.call("text_apply_range", target="full",
           content="<h1>Inside</h1><p>written by a tool</p>")
    h.call("doc_save")
    before = [c.get("text") for c in h.call("nav_tree").get("children", [])]
    h.call("text_search_fulltext", query="written")         # build the index
    if not h.uno_append_heading("outside_edit.odt", "Outsider Zebra"):
        return "SKIPPED — uno module unavailable for the out-of-band edit"
    after = [c.get("text") for c in h.call("nav_tree").get("children", [])]
    if "Outsider Zebra" not in [(t or "").strip() for t in after]:
        raise Fail("nav_tree still serves the tree from before an outside "
                   "edit: before %s, after %s" % (before, after))
    hits = h.call("text_search_fulltext", query="zebra").get("total_found")
    if not hits:
        raise Fail("the full-text index missed an edit made outside Nelson")
    return "30 doc churn: counts right; outside edit seen by nav_tree and index"


def check_search_reports_styles(h):
    """Search and read say which style a paragraph has, and filter on it.

    A table of contents repeats every chapter title in body text: without
    the style an agent cannot tell the entry from the heading, and restyles
    both (#2642).
    """
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_apply_range", target="full", content=(
        "<p>CHAPTER 1. Loomings.</p><p>CHAPTER 2. The Carpet-Bag.</p>"
        "<h1>CHAPTER 1. Loomings.</h1><p>Call me Ishmael.</p>"
        "<h1>CHAPTER 2. The Carpet-Bag.</h1><p>I stuffed a shirt.</p>"))
    hits = h.call("text_search", pattern="CHAPTER [0-9]+\\.", regex=True,
                  max_results=10).get("matches", [])
    styles = sorted({m.get("style") or "" for m in hits})
    if len(hits) != 4 or len(styles) != 2 or not all(styles):
        raise Fail("expected 4 matches in 2 named styles, got %s"
                   % [(m.get("paragraph_index"), m.get("style")) for m in hits])
    heading = next(st for st in styles if "1" in st)
    toc = next(st for st in styles if st != heading)
    only = h.call("text_search", pattern="CHAPTER", style=heading.lower())
    if only.get("count") != 2 or any(m.get("style") != heading
                                     for m in only.get("matches", [])):
        raise Fail("style=%r did not keep just the headings: %s"
                   % (heading, only))
    skip = h.call("text_search", pattern="CHAPTER", exclude_style=toc)
    if skip.get("count") != 2:
        raise Fail("exclude_style=%r left %s matches" % (toc, skip.get("count")))
    read = h.call("text_read", start_index=2, count=1).get("paragraphs", [])
    if not read or read[0].get("style") != heading:
        raise Fail("text_read does not report the style: %s" % read)
    return "styles %s told apart; style and exclude_style filter" % styles


def check_style_set(h):
    """style_set changes a style, reports before/after, and it is saved (#2647).

    "Change the font of the body text" had no tool at all: styles were
    read-only.
    """
    path = h.doc("styled.odt")
    h.reset()
    h.call("doc_create", doc_type="writer", path=path)
    h.call("text_apply_range", target="full",
           content="<h1>Title</h1><p>Body text to restyle.</p>")
    body = h.call("text_read", start_index=1, count=1)["paragraphs"][0]
    style = body.get("style")
    changed = h.call("style_set", style_name=style, properties={
        "font_name": "Liberation Serif", "font_size": 13, "bold": True,
        "align": "justify", "space_after": 3})
    if changed.get("status") != "ok":
        raise Fail("style_set on %r failed: %s" % (style, changed))
    after = changed.get("after", {})
    want = {"font_name": "Liberation Serif", "font_size": 13.0, "bold": True,
            "align": "justify", "space_after": 3.0}
    if after != want:
        raise Fail("style_set after=%s, expected %s" % (after, want))
    info = h.call("style_info", style_name=style, family="ParagraphStyles")
    if info.get("CharFontName") != "Liberation Serif":
        raise Fail("style_info does not see the new font: %s" % info)
    h.call("doc_save")
    with zipfile.ZipFile(path) as z:
        styles_xml = z.read("styles.xml").decode("utf-8", "replace")
    if 'style:font-name="Liberation Serif"' not in styles_xml:
        raise Fail("the saved styles.xml does not carry the new font")

    bad = h.call("style_set", style_name=style, properties={"align": "middle"})
    if bad.get("status") == "ok" or "left" not in json.dumps(bad):
        raise Fail("an invalid value was not refused with the choices: %s"
                   % bad)
    missing = h.call("style_set", style_name="Text bodyy",
                     properties={"bold": True})
    if missing.get("code") != "style_not_found" or not missing.get("similar"):
        raise Fail("a misspelt style gave no suggestion: %s" % missing)
    odd = h.call("style_set", style_name=style,
                 properties={"font_name": "No Such Font Nelson"})
    if odd.get("status") != "ok":
        raise Fail("an unknown font was refused instead of warned: %s" % odd)
    warned = "warning" in odd
    return "%r restyled and saved; bad value and misspelt name refused; " \
           "unknown font %s" % (style, "warned" if warned
                                else "not warned (font list unavailable)")


def check_listing_leaves_documents_alone(h):
    """Nelson reads a document without marking it modified or writing to it.

    get_doc_id stored a NelsonDocId property in every document it touched —
    doc_list_open, _resolved, id: addressing — which set the modified flag on
    documents the agent had only listed and left the id in the saved file
    (#2627). The document is opened and checked from outside Nelson.
    """
    path = h.doc("untouched.odt")
    h.reset()
    h.call("doc_create", doc_type="writer", path=path)
    h.call("text_insert", paragraph_index=0, text="leave me alone")
    h.call("doc_save")
    h.call("doc_close")

    opened = h.uno_run(
        "p=PropertyValue(); p.Name='Hidden'; p.Value=False\n"
        "d=desktop.loadComponentFromURL(%r,'_blank',0,(p,))\n"
        "print(json.dumps(bool(d.isModified())))\n"
        % ("file://" + path))
    if opened is None:
        return "SKIPPED — uno module unavailable for the out-of-band check"

    listed = h.call("doc_list_open").get("documents", [])
    mine = [d for d in listed if (d.get("url") or "").endswith("untouched.odt")]
    if not mine or not mine[0].get("doc_id"):
        raise Fail("doc_list_open does not list the document: %s" % listed)
    doc_id = mine[0]["doc_id"]
    h.call("doc_info", _document="id:%s" % doc_id)
    again = h.call("doc_list_open").get("documents", [])
    if doc_id not in [d.get("doc_id") for d in again]:
        raise Fail("doc_id changed between two doc_list_open calls")

    modified = h.uno_run(
        "e=desktop.getComponents().createEnumeration()\n"
        "out=None\n"
        "while e.hasMoreElements():\n"
        "    d=e.nextElement()\n"
        "    try:\n"
        "        url=d.getURL()\n"
        "    except Exception:\n"
        "        continue\n"                    # Start Center and the like
        "    if url.endswith('untouched.odt'):\n"
        "        out=[bool(d.isModified()), "
        "d.getDocumentProperties().getUserDefinedProperties()"
        ".getPropertySetInfo().hasPropertyByName('NelsonDocId')]\n"
        "print(json.dumps(out))\n")
    if modified is None:
        raise Fail("could not read the document back over UNO: %s"
                   % h.uno_last_error)
    if modified[0]:
        raise Fail("listing and addressing the document marked it modified")
    if modified[1]:
        raise Fail("a NelsonDocId property was written into the document")

    h.call("doc_save", _document="id:%s" % doc_id)
    with zipfile.ZipFile(path) as z:
        meta = z.read("meta.xml").decode("utf-8", "replace")
    if "NelsonDocId" in meta:
        raise Fail("the saved file carries NelsonDocId")
    return "listed, addressed by id and saved: never modified, no NelsonDocId"


def check_reads_are_capped(h):
    """Large reads are capped by the settings and say so (#2628, GH #39).

    writer.max_content_chars and calc.max_rows_display were shown in Options
    and never read: a 60 000-character document came back whole, and a
    spreadsheet read had no limit at all.
    """
    h.reset()
    h.call("doc_create", doc_type="writer")
    para = "<p>%s</p>" % ("lorem ipsum dolor sit amet " * 4)
    h.call("text_apply_range", target="full", content=para * 600)
    full = h.call("text_get_range", scope="full")
    if not full.get("truncated") or full["length"] > 50000 + 40:
        raise Fail("a ~65 000-character document was not capped at 50 000: "
                   "length %s, truncated %s"
                   % (full.get("length"), full.get("truncated")))
    if full["content"].rstrip().endswith("<p") or not full.get("hint"):
        raise Fail("capped content is cut badly or gives no hint")
    whole = h.call("text_get_range", scope="full", max_chars=200000)
    if whole.get("truncated") or whole["length"] != full.get(
            "content_total_length"):
        raise Fail("max_chars=200000 did not return the whole content: %s"
                   % {k: whole.get(k) for k in ("length", "truncated")})
    h.set_config("writer.max_content_chars", 20000)
    try:
        small = h.call("text_get_range", scope="full")
        if small.get("length", 0) > 20000 + 40:
            raise Fail("changing Max Content Size had no effect: length %s"
                       % small.get("length"))
    finally:
        h.set_config("writer.max_content_chars", 50000)

    h.reset()
    h.call("doc_create", doc_type="calc")
    rows = [["r%d" % i, i] for i in range(1, 1501)]
    h.call("calc_write_range", start_cell="A1", values=rows)
    first = h.call("calc_read_range", range_name="A1:B1500")
    if not first.get("truncated") or len(first["result"]) != 1000:
        raise Fail("1500 rows were not capped at 1000: %s rows, truncated %s"
                   % (len(first.get("result", [])), first.get("truncated")))
    if first.get("next_range") != "A1001:B1500":
        raise Fail("next_range is %r, expected A1001:B1500"
                   % first.get("next_range"))
    rest = h.call("calc_read_range", range_name=first["next_range"])
    got = [[c["value"] for c in row] for row in first["result"] + rest["result"]]
    if rest.get("truncated") or got != [[r[0], float(r[1])] for r in rows]:
        raise Fail("reading next_range did not complete the data exactly")
    h.set_config("calc.max_rows_display", 200)
    try:
        few = h.call("calc_read_range", range_name="A1:B1500")
        if len(few.get("result", [])) != 200:
            raise Fail("changing Max Rows Display had no effect: %s rows"
                       % len(few.get("result", [])))
    finally:
        h.set_config("calc.max_rows_display", 1000)
    return ("Writer capped at 50 000 with hint, max_chars and the setting "
            "apply; Calc 1000 + next_range = all 1500 rows, setting applies")


def check_markdown_exchange(h):
    """Markdown in, Markdown out, and the setting chooses the default (#2650).

    Markdown given to text_apply_range went through the HTML filter and
    landed as literal '#' and '**' (#2635); and the format setting was read
    but never declared, so reads were always HTML.
    """
    h.reset()
    h.call("doc_create", doc_type="writer")
    md = ("# Quarterly Report\n\nSales reached **4.2 million**.\n\n"
          "## Regions\n\n- North\n- South\n\n"
          "| Region | Sales |\n|---|---|\n| North | 3 |\n| South | 1 |\n")
    applied = h.call("text_apply_range", target="full", content=md)
    if applied.get("status") != "ok":
        raise Fail("text_apply_range refused Markdown: %s" % applied)
    outline = [n.get("title") for n in _flatten_outline(
        h.call("nav_outline").get("outline", []))]
    if outline[:2] != ["Quarterly Report", "Regions"]:
        raise Fail("Markdown headings did not become headings: %s" % outline)
    text = " ".join(p.get("text", "") for p in
                    h.call("text_read", count=20).get("paragraphs", []))
    if "**" in text or "# " in text:
        raise Fail("Markdown syntax landed literally: %r" % text[:200])
    bold = h.uno_run(
        "d=desktop.getCurrentComponent()\n"
        "import json\n"
        "out=None\n"
        "e=d.getText().createEnumeration()\n"
        "while e.hasMoreElements():\n"
        "    p=e.nextElement()\n"
        "    if not p.supportsService('com.sun.star.text.Paragraph'): continue\n"
        "    for r in p.createEnumeration():\n"
        "        if '4.2 million' in r.getString():\n"
        "            out=r.getPropertyValue('CharWeight')\n"
        "print(json.dumps(out))\n")
    if bold is not None and bold < 150:
        raise Fail("**4.2 million** is not bold (CharWeight %s)" % bold)
    tables = h.call("table_list").get("tables") or []

    as_md = h.call("text_get_range", scope="full", format="markdown")
    as_html = h.call("text_get_range", scope="full", format="html")
    if as_md.get("format") != "markdown" or "# Quarterly Report" not in \
            as_md.get("content", ""):
        raise Fail("format=markdown did not return Markdown: %s"
                   % as_md.get("content", "")[:120])
    if as_html.get("format") != "html" or "<h1" not in as_html.get(
            "content", "").lower():
        raise Fail("format=html did not return HTML")

    h.set_config("core.document_format", "markdown")
    try:
        default = h.call("text_get_range", scope="full")
        if default.get("format") != "markdown":
            raise Fail("the Document format setting did not change the "
                       "default: %s" % default.get("format"))
    finally:
        h.set_config("core.document_format", "html")

    # Round trip: read as Markdown, write it back, same structure.
    h.call("text_apply_range", target="full", content=as_md["content"],
           format="markdown")
    again = [n.get("title") for n in _flatten_outline(
        h.call("nav_outline").get("outline", []))]
    tables_again = h.call("table_list").get("tables") or []
    if again != outline or len(tables_again) != len(tables):
        raise Fail("Markdown round trip changed the structure: headings "
                   "%s -> %s, tables %d -> %d"
                   % (outline, again, len(tables), len(tables_again)))
    return ("Markdown imported as headings%s%s; formats and setting "
            "apply; round trip keeps %d headings, %d table(s)"
            % ("" if bold is None else ", bold",
               ", table" if tables else " (no table: filter)",
               len(again), len(tables_again)))


def _flatten_outline(nodes):
    for n in nodes:
        yield n
        yield from _flatten_outline(n.get("children", []))


def check_report_building_blocks(h):
    """Page numbers, a table of contents and a page break (#2634).

    "Page <page>" in a footer used to stay literal text, and nothing could
    insert a table of contents or a page break. Saved as .docx and read in
    the XML, so the fields are real ones Word understands.
    """
    path = h.doc("report.docx")
    h.reset()
    h.call("doc_create", doc_type="writer")
    h.call("text_apply_range", target="full", content=(
        "<h1>Quarterly Report</h1><p>Intro.</p>"
        "<h2>Sales</h2><p>Up.</p><h2>Costs</h2><p>Down.</p>"))
    foot = h.call("header_footer_set", region="footer",
                  text="Page {page} of {pages}")
    if foot.get("status") != "ok" or foot.get("fields") != ["page", "pages"]:
        raise Fail("footer fields not inserted: %s" % foot)
    bad = h.call("header_footer_set", region="header", text="{chapter}")
    if bad.get("status") == "ok" or "{page}" not in json.dumps(bad):
        raise Fail("an unknown field was not refused with the known ones")

    toc = h.call("doc_insert_toc", position="after_heading")
    if toc.get("status") != "ok" or toc.get("entries", 0) < 3:
        raise Fail("table of contents not inserted or empty: %s" % toc)
    again = h.call("doc_insert_toc")
    if again.get("code") != "toc_exists":
        raise Fail("a second table of contents was not refused: %s" % again)

    paras = h.call("text_read", count=40).get("paragraphs", [])
    costs = next((p["index"] for p in paras if p.get("text") == "Costs"), None)
    if costs is None:
        raise Fail("cannot find the Costs heading: %s" % paras)
    brk = h.call("text_insert_break", paragraph_index=costs, type="page")
    if brk.get("status") != "ok":
        raise Fail("text_insert_break failed: %s" % brk)

    saved = h.call("doc_save_as", target_path=path)
    if saved.get("status") != "ok":
        raise Fail("saving as .docx failed: %s" % saved)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        footers = "".join(z.read(n).decode("utf-8", "replace")
                          for n in names if n.startswith("word/footer"))
        body = z.read("word/document.xml").decode("utf-8", "replace")
    missing = [w for w, where in (("PAGE", footers), ("NUMPAGES", footers))
               if w not in where]
    # Word stores a table of contents as a TOC field built from outline
    # levels ("TOC \\o", possibly with other switches between).
    if not re.search(r"TOC\s[^<]*\\o", body):
        missing.append("TOC field")
    if "Page {page}" in footers or "<page>" in footers:
        missing.append("literal token left in the footer")
    if 'w:type="page"' not in body and "w:pageBreakBefore" not in body:
        missing.append("page break")
    if missing:
        at = body.find("TOC")
        raise Fail("the saved .docx lacks: %s (TOC context: %r)"
                   % (", ".join(missing), body[max(0, at - 80):at + 120]))
    return ("footer PAGE/NUMPAGES fields, TOC with %d entries, page break — "
            "all in the .docx" % toc["entries"])


def check_close_after_rewrite(h):
    """Closing a rewritten document does not abort LibreOffice (#2651).

    doc_close ran inside the undo context Nelson opens around every
    mutation, so the document was destroyed with a list action still open;
    after full rewrites involving a table, ~SfxUndoArray aborted the whole
    office. Three rewrite-and-close rounds, then LibreOffice must answer.
    """
    md = ("# Report\n\nSome **bold** text.\n\n"
          "| Region | Sales |\n|---|---|\n| North | 3 |\n| South | 1 |\n")
    for round_ in range(3):
        h.reset()
        h.call("doc_create", doc_type="writer")
        h.call("text_apply_range", target="full", content=md)
        h.call("text_apply_range", target="full", content=md + "\nMore.\n")
        closed = h.call("doc_close")
        if closed.get("status") != "ok":
            raise Fail("round %d: doc_close failed: %s" % (round_ + 1, closed))
        listed = h.call("doc_list_open")
        if listed.get("status") != "ok":
            raise Fail("round %d: LibreOffice stopped answering after "
                       "doc_close: %s" % (round_ + 1, listed))
    return "3 rewrite-and-close rounds, LibreOffice still answering"


def check_array_formulas(h):
    """FILTER/SORT results come back whole, or not at all (#2631).

    LibreOffice does not spill: written to one cell, =SORT(FILTER(...))
    showed one value and dropped the rest, with status ok.
    """
    h.reset()
    h.call("doc_create", doc_type="calc")
    rows = [["country", "year", "co2"]]
    data = [["A", 2021, 5], ["B", 2022, 30], ["C", 2022, 10], ["D", 2020, 7],
            ["E", 2022, 20], ["F", 2021, 1], ["G", 2022, 40]]
    rows += data
    h.call("calc_write_range", start_cell="A1", values=rows)
    expected = sorted([r for r in data if r[1] == 2022], key=lambda r: -r[2])

    res = h.call("calc_write_formula", range_name="E1",
                 formula_or_values="=SORT(FILTER(A2:C8;B2:B8=2022);3;-1)")
    if res.get("status") != "ok" or res.get("rows") != len(expected) \
            or res.get("columns") != 3:
        raise Fail("array formula not entered over its result: %s" % res)
    got = h.call("calc_read_range", range_name="E1:G%d" % len(expected))
    values = [[c["value"] for c in row] for row in got["result"]]
    want = [[r[0], float(r[1]), float(r[2])] for r in expected]
    if values != want:
        raise Fail("array result %s, expected %s" % (values, want))
    last = got["result"][-1][-1]
    if last.get("array_range") != "E1:G%d" % len(expected):
        raise Fail("calc_read_range does not report the array range: %s"
                   % last)

    none = h.call("calc_write_formula", range_name="J1",
                  formula_or_values="=FILTER(A2:C8;B2:B8=1999)")
    if none.get("code") != "formula_error":
        raise Fail("a FILTER with no match was not reported: %s" % none)

    h.call("calc_write_range", start_cell="M2", values=[["keep me"]])
    blocked = h.call("calc_write_formula", range_name="L1",
                     formula_or_values="=SORT(FILTER(A2:C8;B2:B8=2022);3;-1)")
    kept = h.call("calc_read_range", range_name="L1")["result"][0][0]
    if blocked.get("code") != "target_not_empty" or kept.get("value"):
        raise Fail("an occupied target was overwritten or not refused: %s"
                   % blocked)

    scalar = h.call("calc_write_formula", range_name="I1",
                    formula_or_values="=SUM(FILTER(C2:C8;B2:B8=2022))")
    total = h.call("calc_read_range", range_name="I1")["result"][0][0]
    if scalar.get("array") or total.get("value") != 100.0 \
            or total.get("array_range"):
        raise Fail("=SUM(FILTER()) should stay a single cell worth 100: %s %s"
                   % (scalar, total))

    small = h.call("calc_write_formula", range_name="E20:G21",
                   formula_or_values="=SORT(FILTER(A2:C8;B2:B8=2022);3;-1)")
    if "cut" not in (small.get("warning") or ""):
        raise Fail("a too-small explicit range gave no warning: %s" % small)
    return ("SORT(FILTER) over E1:G%d with the right values; no-match error, "
            "occupied target refused, SUM(FILTER) scalar, cut range warned"
            % len(expected))


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
    ("open is active (#34)", check_open_is_active),
    ("save-as keeps original", check_save_as_keeps_original),
    ("doc_id uniqueness", check_doc_ids_distinct),
    ("listing leaves documents alone", check_listing_leaves_documents_alone),
    ("recording not forced", check_recording_not_forced),
    ("search backends agree", check_search_backends_agree),
    ("sheet-qualified refs", check_sheet_qualified_refs),
    ("calc sheet targets (#31-33)", check_calc_sheet_targets),
    ("array formulas (#2631)", check_array_formulas),
    ("doc_close truthful (#36)", check_close_reports_truth),
    ("browser origin refused", check_origin_rejected),
    ("session semantics (#38)", check_session_semantics),
    ("access token", check_auth_token),
    ("heading bookmarks (#2644)", check_heading_bookmarks),
    ("heading content by path", check_heading_content_duplicates),
    ("caches follow the document", check_caches_follow_the_document),
    ("search reports styles", check_search_reports_styles),
    ("style_set (#2647)", check_style_set),
    ("reads are capped (#39)", check_reads_are_capped),
    ("markdown exchange (#2635)", check_markdown_exchange),
    ("close after rewrite (#2651)", check_close_after_rewrite),
    ("report building blocks (#2634)", check_report_building_blocks),
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
    ap.add_argument("--wbox", action="store_true",
                    help="run LibreOffice's GUI in a wbox compositor "
                         "(offscreen unless WBOX_VISIBLE=1)")
    args = ap.parse_args()

    h = Harness(args.port, args.uno_port, args.verbose, args.keep, args.wbox)
    print("Nelson smoke test — profile %s" % h.profile)

    failures = []
    try:
        print("  installing extension ...", flush=True)
        h.install()
        if h.wbox:
            visible = os.environ.get("WBOX_VISIBLE", "").lower() in (
                "1", "true", "yes", "on")
            print("  starting LibreOffice in wbox (%s) ..."
                  % ("visible" if visible else "offscreen"), flush=True)
        else:
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
