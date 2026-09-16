# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""BookmarkService — heading bookmarks (stable IDs) for Writer documents.

Ported from mcp-libre services/writer/tree.py (bookmark methods).

Navigation gives every heading a hidden ``_mcp_<hex>`` bookmark so an agent
can address it by a name that survives edits. Those bookmarks are Nelson's
bookkeeping, not the user's content, so reading a document must not change
it. What happens to them is the ``writer.nav.heading_bookmarks`` option:

- ``strip_on_save`` (default): created in memory, removed just before a save
  writes the file and put back, under the same names, once it has.
- ``keep``: created and saved with the document, as before.
- ``off``: never created; headings are addressed by paragraph index only.

In every mode, creating or restoring them leaves the document's modified
flag and undo stack as they were.
"""

import logging
import uuid

log = logging.getLogger("nelson.writer.nav.bookmarks")

MODES = ("strip_on_save", "keep", "off")
DEFAULT_MODE = "strip_on_save"
PREFIX = "_mcp_"


class BookmarkService:
    """Manage _mcp_ bookmarks on headings for stable addressing."""

    def __init__(self, doc_svc, events, mode_getter=None):
        self._doc_svc = doc_svc
        self._mode_getter = mode_getter
        self._bookmark_cache = {}  # doc_key -> {para_index: bookmark_name}
        # [model, modified before the save, {para_index: name}] while a save
        # is writing the file without the bookmarks. Matched by UNO identity:
        # Save As changes the URL doc_key() is built from.
        self._stripped = []
        events.subscribe("document:cache_invalidated",
                         self._on_cache_invalidated)

    def _on_cache_invalidated(self, doc=None, **_kw):
        if doc is None:
            self._bookmark_cache.clear()
        else:
            self._bookmark_cache.pop(self._doc_svc.doc_key(doc), None)

    @property
    def mode(self):
        mode = None
        if self._mode_getter is not None:
            try:
                mode = self._mode_getter()
            except Exception:
                mode = None
        return mode if mode in MODES else DEFAULT_MODE

    def get_mcp_bookmark_map(self, doc):
        """Return {para_index: bookmark_name} for all _mcp_ bookmarks."""
        key = self._doc_svc.doc_key(doc)
        if key in self._bookmark_cache:
            return self._bookmark_cache[key]

        result = {}
        try:
            if not hasattr(doc, "getBookmarks"):
                return result
            bookmarks = doc.getBookmarks()
            names = bookmarks.getElementNames()
            if not names:
                return result
            para_ranges = self._doc_svc.get_paragraph_ranges(doc)
            text_obj = doc.getText()
            for name in names:
                if not name.startswith("_mcp_"):
                    continue
                bm = bookmarks.getByName(name)
                anchor = bm.getAnchor()
                para_idx = self._doc_svc.find_paragraph_for_range(
                    anchor, para_ranges, text_obj)
                if para_idx >= 0:
                    result[para_idx] = name
        except Exception as e:
            log.error("Failed to get MCP bookmark map: %s", e)

        self._bookmark_cache[key] = result
        return result

    def ensure_heading_bookmarks(self, doc):
        """Ensure every heading has an _mcp_ bookmark. Returns map.

        With the option set to ``off`` nothing is created and the map only
        holds bookmarks the document already carries.
        """
        existing_map = self.get_mcp_bookmark_map(doc)
        if self.mode == "off":
            return existing_map
        text = doc.getText()
        enum = text.createEnumeration()
        para_index = 0
        bookmark_map = {}
        needs_bookmark = []

        while enum.hasMoreElements():
            element = enum.nextElement()
            if element.supportsService("com.sun.star.text.Paragraph"):
                outline_level = 0
                try:
                    outline_level = element.getPropertyValue("OutlineLevel")
                except Exception:
                    pass
                if outline_level > 0:
                    if para_index in existing_map:
                        bookmark_map[para_index] = existing_map[para_index]
                    else:
                        needs_bookmark.append(
                            (para_index, element.getStart()))
            para_index += 1
            self._doc_svc.yield_to_gui()

        if needs_bookmark:
            with _untracked(doc):
                for para_idx, start_range in needs_bookmark:
                    bm_name = "%s%s" % (PREFIX, uuid.uuid4().hex[:8])
                    _insert_bookmark(doc, text, start_range, bm_name)
                    bookmark_map[para_idx] = bm_name

        key = self._doc_svc.doc_key(doc)
        self._bookmark_cache[key] = bookmark_map
        return bookmark_map

    def find_nearest_heading_bookmark(self, para_index, bookmark_map):
        """Find nearest heading bookmark at or before para_index."""
        best_idx = -1
        for idx in bookmark_map:
            if idx <= para_index and idx > best_idx:
                best_idx = idx
        if best_idx >= 0:
            return {"bookmark": bookmark_map[best_idx],
                    "heading_para_index": best_idx}
        return None

    def cleanup_mcp_bookmarks(self, doc):
        """Remove all _mcp_* bookmarks from the document."""
        removed = 0
        try:
            if not hasattr(doc, "getBookmarks"):
                return removed
            bookmarks = doc.getBookmarks()
            names = bookmarks.getElementNames()
            text = doc.getText()
            for name in names:
                if name.startswith("_mcp_"):
                    try:
                        bm = bookmarks.getByName(name)
                        text.removeTextContent(bm)
                        removed += 1
                    except Exception:
                        pass
            if removed:
                key = self._doc_svc.doc_key(doc)
                self._bookmark_cache.pop(key, None)
        except Exception as e:
            log.error("Failed to cleanup bookmarks: %s", e)
        return removed

    # ── Save hook (strip_on_save) ──────────────────────────────────

    def strip_for_save(self, doc):
        """Remove the _mcp_ bookmarks before a save writes *doc*.

        Remembers where they were so restore_after_save() can put them back
        under the same names. No-op unless the mode is strip_on_save.
        """
        if self.mode != "strip_on_save" or not hasattr(doc, "getBookmarks"):
            return 0
        if self._find_stripped(doc) is not None:
            return 0
        key = self._doc_svc.doc_key(doc)
        try:
            names = [n for n in doc.getBookmarks().getElementNames()
                     if n.startswith(PREFIX)]
        except Exception:
            return 0
        if not names:
            return 0
        self._bookmark_cache.pop(key, None)
        positions = self.get_mcp_bookmark_map(doc)
        was_modified = _is_modified(doc)
        bookmarks = doc.getBookmarks()
        text = doc.getText()
        removed = 0
        with _untracked(doc, keep_modified=False):
            for name in names:
                try:
                    text.removeTextContent(bookmarks.getByName(name))
                    removed += 1
                except Exception as e:
                    log.debug("strip %s failed: %s", name, e)
        self._bookmark_cache.pop(key, None)
        self._stripped.append((doc, was_modified, positions))
        return removed

    def _find_stripped(self, doc):
        for i, entry in enumerate(self._stripped):
            try:
                if entry[0] == doc:
                    return i
            except Exception:
                continue
        return None

    def restore_after_save(self, doc, saved):
        """Put back what strip_for_save() removed.

        *saved* is True when the save replaced the document's own file
        (Save, Save As): the document is clean now and must stay clean. For a
        copy (Save a Copy, export) or a failed save, the modified flag goes
        back to what it was before the save started.
        """
        i = self._find_stripped(doc)
        if i is None:
            return 0
        _, was_modified, positions = self._stripped.pop(i)
        target = _is_modified(doc) if saved else was_modified
        restored = 0
        restored_map = {}
        try:
            para_ranges = self._doc_svc.get_paragraph_ranges(doc)
            text = doc.getText()
            with _untracked(doc, keep_modified=False):
                for para_idx, name in sorted(positions.items()):
                    if not 0 <= para_idx < len(para_ranges):
                        continue
                    try:
                        _insert_bookmark(doc, text,
                                         para_ranges[para_idx].getStart(),
                                         name)
                        restored_map[para_idx] = name
                        restored += 1
                    except Exception as e:
                        log.debug("restore %s failed: %s", name, e)
        except Exception as e:
            log.error("Failed to restore heading bookmarks: %s", e)
        finally:
            with _ignoring():
                _set_modified(doc, target)
        self._bookmark_cache[self._doc_svc.doc_key(doc)] = restored_map
        return restored


def _insert_bookmark(doc, text, start_range, name):
    bookmark = doc.createInstance("com.sun.star.text.Bookmark")
    bookmark.Name = name
    cursor = text.createTextCursorByRange(start_range)
    text.insertTextContent(cursor, bookmark, False)


def _is_modified(doc):
    try:
        return bool(doc.isModified())
    except Exception:
        return False


def _set_modified(doc, value):
    try:
        if bool(doc.isModified()) != bool(value):
            doc.setModified(bool(value))
    except Exception:
        pass


class _untracked:
    """Change bookmarks without it showing: no undo step, same modified flag.

    With keep_modified=False the caller restores the flag itself.
    """

    def __init__(self, doc, keep_modified=True):
        self._doc = doc
        self._keep = keep_modified
        self._undo = None
        self._was_modified = False

    def __enter__(self):
        # Bookmarks leave the text and its numbering alone: no cache (and no
        # search index) needs to be thrown away for them.
        self._ignore = _ignoring()
        self._ignore.__enter__()
        self._was_modified = _is_modified(self._doc)
        try:
            self._undo = self._doc.getUndoManager()
            self._undo.lock()
        except Exception:
            self._undo = None
        return self

    def __exit__(self, *exc):
        if self._undo is not None:
            try:
                self._undo.unlock()
            except Exception:
                pass
        if self._keep:
            _set_modified(self._doc, self._was_modified)
        self._ignore.__exit__(*exc)
        return False


def _ignoring():
    try:
        from plugin.modules.core.services.document import DocumentCache
        return DocumentCache.ignoring()
    except Exception:
        import contextlib
        return contextlib.nullcontext()
