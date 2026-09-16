# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Keep Nelson's heading bookmarks out of saved Writer files.

Listens to every document's save events through the global event
broadcaster: just before a save writes the file the _mcp_ bookmarks are
removed, and once it is done (or has failed) they are put back. Whether that
happens is decided per save by BookmarkService.mode, so changing the option
takes effect without a restart.
"""

import logging

log = logging.getLogger("nelson.writer.nav.save_hook")

# Event name -> True for "before", or the value of restore_after_save(saved=).
_BEFORE = ("OnSave", "OnSaveAs", "OnSaveTo")
_AFTER = {
    "OnSaveDone": True,
    "OnSaveAsDone": True,
    "OnSaveToDone": False,
    "OnSaveFailed": False,
    "OnSaveAsFailed": False,
    "OnSaveToFailed": False,
}


def handle_event(bm_svc, event_name, doc):
    """Route one document event. Separate from UNO so it can be tested."""
    if doc is None or not hasattr(doc, "getBookmarks"):
        return None
    if event_name in _BEFORE:
        return bm_svc.strip_for_save(doc)
    if event_name in _AFTER:
        return bm_svc.restore_after_save(doc, saved=_AFTER[event_name])
    return None


class SaveHook:
    """Registers a document event listener on theGlobalEventBroadcaster."""

    def __init__(self, bm_svc):
        self._bm_svc = bm_svc
        self._broadcaster = None
        self._listener = None

    def register(self, ctx):
        import unohelper
        from com.sun.star.document import XDocumentEventListener

        bm_svc = self._bm_svc

        class _Listener(unohelper.Base, XDocumentEventListener):
            def documentEventOccured(self, event):
                try:
                    handle_event(bm_svc, event.EventName, event.Source)
                except Exception as e:
                    log.error("heading bookmarks on %s: %s",
                              event.EventName, e)

            def disposing(self, source):
                pass

        # A singleton: createInstance() on this name returns None.
        broadcaster = ctx.getValueByName(
            "/singletons/com.sun.star.frame.theGlobalEventBroadcaster")
        if broadcaster is None:
            raise RuntimeError("theGlobalEventBroadcaster is unavailable")
        self._broadcaster = broadcaster
        self._listener = _Listener()
        self._broadcaster.addDocumentEventListener(self._listener)

    def unregister(self):
        if self._broadcaster is not None and self._listener is not None:
            try:
                self._broadcaster.removeDocumentEventListener(self._listener)
            except Exception:
                pass
        self._broadcaster = None
        self._listener = None
