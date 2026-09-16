# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""No UNO off the main thread: the active-document watcher and the guard
(#2625, GitHub #35/#37)."""

import logging
import threading

from plugin.framework.main_thread import warn_if_off_main_thread
from plugin.modules.mcp.active_doc import ActiveDocumentWatcher


class DocSvc:
    def __init__(self):
        self.doc = None
        self.calls = []

    def get_active_document(self):
        self.calls.append(threading.current_thread().name)
        return self.doc

    def detect_doc_type(self, doc):
        return doc["type"]

    def get_doc_id(self, doc):
        return doc["id"]

    def get_default_save_dir(self):
        return "/home/u/Documents"


def test_snapshot_needs_no_uno_and_reports_pending_first():
    svc = DocSvc()
    w = ActiveDocumentWatcher(svc)
    assert w.snapshot()["known"] is False
    assert svc.calls == []
    svc.doc = {"type": "writer", "id": "abc"}
    w.on_event("OnFocus")
    snap = w.snapshot()
    assert (snap["known"], snap["doc_type"], snap["doc_id"]) == (
        True, "writer", "abc")
    calls = len(svc.calls)
    for _ in range(5):
        w.snapshot()
    assert len(svc.calls) == calls          # reading never touches UNO


def test_type_change_notifies_only_on_change():
    svc, seen = DocSvc(), []
    w = ActiveDocumentWatcher(svc, on_type_change=seen.append)
    svc.doc = {"type": "writer", "id": "a"}
    w.refresh()                              # baseline, no notification
    w.refresh()
    svc.doc = {"type": "calc", "id": "b"}
    w.refresh()
    svc.doc = None
    w.refresh()
    assert seen == ["calc", None]


def test_unrelated_events_are_ignored():
    svc = DocSvc()
    w = ActiveDocumentWatcher(svc)
    w.on_event("OnSaveDone")
    assert svc.calls == []


def test_guard_warns_once_per_call_site_off_the_main_thread(caplog):
    caplog.set_level(logging.WARNING, "nelson.framework.main_thread")
    assert warn_if_off_main_thread("x") is False     # pytest's main thread
    results = []

    def worker():
        for _ in range(3):
            results.append(warn_if_off_main_thread("get_active_document"))

    t = threading.Thread(target=worker, name="nelson-test")
    t.start()
    t.join()
    assert results == [True, True, True]
    lines = [r for r in caplog.records
             if "UNO off the main thread" in r.getMessage()]
    assert len(lines) == 1 and "nelson-test" in lines[0].getMessage()
