# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Thread-safe ring buffer of MCP tool action entries."""

import threading
import time


class ActionEntry:
    """A single MCP tool action record."""

    __slots__ = (
        "timestamp", "tool_name", "caller", "status", "error",
        "duration", "params_snippet", "image_path",
    )

    def __init__(self, tool_name, caller=""):
        self.timestamp = time.time()
        self.tool_name = tool_name
        self.caller = caller or ""
        self.status = "running"
        self.error = None
        self.duration = None
        self.params_snippet = ""
        self.image_path = None


class ActionLog:
    """Thread-safe ring buffer of MCP action entries.

    Registered as the ``action_log`` service so the sidebar panel can
    read entries for display.
    """

    def __init__(self, max_size=200):
        self._entries = []  # newest first
        self._max_size = max_size
        self._lock = threading.Lock()
        self._on_change = None  # optional callback for UI refresh

    def on_executing(self, name="", caller="", **kw):
        """Called when a tool starts executing."""
        entry = ActionEntry(name, caller)
        with self._lock:
            self._entries.insert(0, entry)
            if len(self._entries) > self._max_size:
                self._entries.pop()
        self._notify()

    def on_completed(self, name="", caller="", **kw):
        """Called when a tool completes successfully."""
        with self._lock:
            entry = self._find(name, caller)
            if entry:
                entry.status = "ok"
                entry.duration = time.time() - entry.timestamp
        self._notify()

    def on_failed(self, name="", error="", caller="", **kw):
        """Called when a tool fails."""
        with self._lock:
            entry = self._find(name, caller)
            if entry:
                entry.status = "error"
                entry.error = str(error) if error else "unknown"
                entry.duration = time.time() - entry.timestamp
        self._notify()

    def entries(self, limit=50):
        """Return most recent entries (newest first)."""
        with self._lock:
            return list(self._entries[:limit])

    def count(self):
        """Return total number of entries."""
        with self._lock:
            return len(self._entries)

    def _find(self, name, caller):
        """Find the most recent running entry matching name+caller.

        Caller holds no lock — must be called inside a ``with self._lock``.
        """
        for entry in self._entries:
            if (entry.tool_name == name and entry.caller == caller
                    and entry.status == "running"):
                return entry
        return None

    def _notify(self):
        cb = self._on_change
        if cb:
            try:
                cb()
            except Exception:
                pass
