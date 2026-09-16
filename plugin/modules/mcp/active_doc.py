# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The active document, as the main thread last saw it (#2625).

/health and the tools/list_changed notification (#24) used to ask UNO for
the current component from Nelson's own threads — the HTTP thread and a
poller every 2 s. Calling UNO off the main thread during startup is the
Nelson side of the GitHub #35/#37 deadlock. This watcher listens to document
events on the main thread, keeps a snapshot, and lets any thread read it
without touching UNO.
"""

import logging
import threading

log = logging.getLogger("nelson.mcp.active_doc")

_REFRESH_NOW = ("OnFocus", "OnLoadFinished", "OnNew", "OnViewCreated",
                "OnSaveAsDone")
_REFRESH_LATER = ("OnUnload", "OnViewClosed", "OnUnfocus")


class ActiveDocumentWatcher:
    """Snapshot of the active document, refreshed on document events."""

    def __init__(self, doc_svc, on_type_change=None):
        self._doc_svc = doc_svc
        self._on_type_change = on_type_change
        self._lock = threading.Lock()
        self._state = {"known": False, "available": None, "doc_type": None,
                       "doc_id": None, "title": None,
                       "default_save_dir": None}
        self._broadcaster = None
        self._listener = None

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def refresh(self):
        """Re-read the active document. Main thread only."""
        doc = doc_type = doc_id = title = None
        try:
            doc = self._doc_svc.get_active_document()
            if doc is not None:
                doc_type = self._doc_svc.detect_doc_type(doc)
                doc_id = self._doc_svc.get_doc_id(doc)
                try:
                    title = doc.getCurrentController().getFrame().getTitle()
                except Exception:
                    title = None
        except Exception:
            log.debug("active document refresh failed", exc_info=True)
        save_dir = None
        try:
            save_dir = self._doc_svc.get_default_save_dir().replace("\\", "/")
        except Exception:
            pass
        with self._lock:
            previous = self._state["doc_type"] if self._state["known"] \
                else _UNSET
            self._state = {"known": True, "available": doc is not None,
                           "doc_type": doc_type, "doc_id": doc_id,
                           "title": title, "default_save_dir": save_dir}
        if previous is not _UNSET and previous != doc_type \
                and self._on_type_change is not None:
            try:
                self._on_type_change(doc_type)
            except Exception:
                log.debug("doc type change callback failed", exc_info=True)

    def on_event(self, name):
        """Route a document event.

        LibreOffice fires events on whatever thread caused them — a UNO
        bridge thread when a client loads a document over the socket — so
        refresh inline only on the main thread, and post otherwise.
        """
        if name not in _REFRESH_NOW and name not in _REFRESH_LATER:
            return
        if name in _REFRESH_NOW and \
                threading.current_thread() is threading.main_thread():
            self.refresh()
            return
        # _REFRESH_LATER: the closing document is still current while the
        # event fires.
        from plugin.framework.main_thread import post_to_main_thread
        post_to_main_thread(self.refresh)

    def register(self, ctx):
        """Listen to document events. Main thread only."""
        import unohelper
        from com.sun.star.document import XDocumentEventListener

        watcher = self

        class _Listener(unohelper.Base, XDocumentEventListener):
            def documentEventOccured(self, event):
                try:
                    watcher.on_event(event.EventName)
                except Exception:
                    log.debug("document event %s failed", event.EventName,
                              exc_info=True)

            def disposing(self, source):
                pass

        self._broadcaster = ctx.getValueByName(
            "/singletons/com.sun.star.frame.theGlobalEventBroadcaster")
        self._listener = _Listener()
        self._broadcaster.addDocumentEventListener(self._listener)
        self.refresh()

    def unregister(self):
        if self._broadcaster is not None and self._listener is not None:
            try:
                self._broadcaster.removeDocumentEventListener(self._listener)
            except Exception:
                pass
        self._broadcaster = self._listener = None


_UNSET = object()
