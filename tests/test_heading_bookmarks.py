# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the writer.nav.heading_bookmarks option (#2644).

A small in-memory Writer model stands in for UNO: paragraphs with an outline
level, bookmarks anchored on a paragraph, a modified flag and an undo manager.
"""

import pytest

from plugin.modules.writer_nav.services import save_hook
from plugin.modules.writer_nav.services.bookmarks import BookmarkService


class Para:
    def __init__(self, level):
        self.level = level

    def supportsService(self, name):
        return name == "com.sun.star.text.Paragraph"

    def getPropertyValue(self, name):
        return self.level

    def getStart(self):
        return self


class Bookmark:
    def __init__(self):
        self.Name = None
        self.para = None

    def getAnchor(self):
        return self.para


class Enum:
    def __init__(self, items):
        self._items = list(items)

    def hasMoreElements(self):
        return bool(self._items)

    def nextElement(self):
        return self._items.pop(0)


class Text:
    def __init__(self, doc):
        self._doc = doc

    def createEnumeration(self):
        return Enum(self._doc.paras)

    def createTextCursorByRange(self, rng):
        return rng

    def insertTextContent(self, cursor, bm, absorb):
        bm.para = cursor
        self._doc.marks[bm.Name] = bm
        self._doc.touch()

    def removeTextContent(self, bm):
        del self._doc.marks[bm.Name]
        self._doc.touch()


class Bookmarks:
    def __init__(self, doc):
        self._doc = doc

    def getElementNames(self):
        return tuple(self._doc.marks)

    def getByName(self, name):
        return self._doc.marks[name]


class Undo:
    def __init__(self, doc):
        self._doc = doc

    def lock(self):
        self._doc.undo_locks += 1

    def unlock(self):
        self._doc.undo_locks -= 1


class Doc:
    def __init__(self, levels, url="file:///tmp/a.odt"):
        self.paras = [Para(lv) for lv in levels]
        self.marks = {}
        self.modified = False
        self.undo_steps = 0
        self.undo_locks = 0
        self.url = url
        self.stored = 0

    def touch(self):
        self.modified = True
        if not self.undo_locks:
            self.undo_steps += 1

    def getText(self):
        return Text(self)

    def getBookmarks(self):
        return Bookmarks(self)

    def createInstance(self, name):
        return Bookmark()

    def getUndoManager(self):
        return Undo(self)

    def isModified(self):
        return self.modified

    def setModified(self, value):
        self.modified = value

    def getURL(self):
        return self.url

    def hasLocation(self):
        return True

    def store(self):
        self.stored += 1


class DocSvc:
    def doc_key(self, doc):
        return doc.getURL()

    def yield_to_gui(self):
        pass

    def get_paragraph_ranges(self, doc):
        return list(doc.paras)

    def find_paragraph_for_range(self, anchor, ranges, text):
        return ranges.index(anchor)


class Events:
    def subscribe(self, *_a, **_kw):
        pass


def service(mode):
    return BookmarkService(DocSvc(), Events(), mode_getter=lambda: mode)


def mcp_names(doc):
    return sorted(n for n in doc.marks if n.startswith("_mcp_"))


LEVELS = [1, 0, 2, 0, 0, 1]


class TestCreation:
    @pytest.mark.parametrize("mode", ["strip_on_save", "keep"])
    def test_marks_headings_without_touching_the_document(self, mode):
        doc = Doc(LEVELS)
        bm_map = service(mode).ensure_heading_bookmarks(doc)
        assert sorted(bm_map) == [0, 2, 5]
        assert len(mcp_names(doc)) == 3
        assert doc.modified is False
        assert doc.undo_steps == 0
        assert doc.stored == 0          # navigation never saves the file

    def test_already_modified_stays_modified(self):
        doc = Doc(LEVELS)
        doc.modified = True
        service("keep").ensure_heading_bookmarks(doc)
        assert doc.modified is True

    def test_off_creates_nothing_but_reports_existing(self):
        doc = Doc(LEVELS)
        service("keep").ensure_heading_bookmarks(doc)
        existing = mcp_names(doc)
        fresh = Doc(LEVELS)
        assert service("off").ensure_heading_bookmarks(fresh) == {}
        assert fresh.marks == {}
        doc2 = service("off")
        assert sorted(doc2.ensure_heading_bookmarks(doc).values()) == existing

    def test_unknown_mode_falls_back_to_default(self):
        assert service("bogus").mode == "strip_on_save"
        assert service(None).mode == "strip_on_save"

    def test_cleanup_never_saves(self):
        doc = Doc(LEVELS)
        svc = service("keep")
        svc.ensure_heading_bookmarks(doc)
        assert svc.cleanup_mcp_bookmarks(doc) == 3
        assert doc.stored == 0


class TestSaveHook:
    def _navigated(self, mode, modified=False):
        doc = Doc(LEVELS)
        doc.marks["user_mark"] = Bookmark()
        doc.marks["user_mark"].Name = "user_mark"
        doc.marks["user_mark"].para = doc.paras[1]
        svc = service(mode)
        svc.ensure_heading_bookmarks(doc)
        doc.modified = modified
        return doc, svc

    def test_save_writes_without_bookmarks_and_restores_same_names(self):
        doc, svc = self._navigated("strip_on_save", modified=True)
        before = {n: doc.marks[n].para for n in mcp_names(doc)}
        seen_at_write = []

        save_hook.handle_event(svc, "OnSave", doc)
        seen_at_write = list(doc.marks)
        doc.modified = False                      # the save itself
        save_hook.handle_event(svc, "OnSaveDone", doc)

        assert seen_at_write == ["user_mark"]
        assert {n: doc.marks[n].para for n in mcp_names(doc)} == before
        assert doc.modified is False
        assert doc.undo_steps == 0

    def test_save_as_with_new_url_still_restores(self):
        doc, svc = self._navigated("strip_on_save")
        names = mcp_names(doc)
        save_hook.handle_event(svc, "OnSaveAs", doc)
        doc.url = "file:///tmp/b.odt"
        doc.modified = False
        save_hook.handle_event(svc, "OnSaveAsDone", doc)
        assert mcp_names(doc) == names
        assert svc.get_mcp_bookmark_map(doc)   # cache under the new URL

    @pytest.mark.parametrize("event", ["OnSaveToDone", "OnSaveFailed"])
    @pytest.mark.parametrize("modified", [False, True])
    def test_copy_or_failure_keeps_previous_modified_flag(self, event,
                                                          modified):
        doc, svc = self._navigated("strip_on_save", modified=modified)
        names = mcp_names(doc)
        save_hook.handle_event(svc, "OnSaveTo", doc)
        save_hook.handle_event(svc, event, doc)
        assert mcp_names(doc) == names
        assert doc.modified is modified

    @pytest.mark.parametrize("mode", ["keep", "off"])
    def test_other_modes_leave_saves_alone(self, mode):
        doc, svc = self._navigated("keep")
        svc._mode_getter = lambda: mode
        names = mcp_names(doc)
        save_hook.handle_event(svc, "OnSave", doc)
        assert mcp_names(doc) == names
        save_hook.handle_event(svc, "OnSaveDone", doc)
        assert mcp_names(doc) == names

    def test_ignores_non_writer_and_unrelated_events(self):
        doc, svc = self._navigated("strip_on_save")
        assert save_hook.handle_event(svc, "OnSave", object()) is None
        assert save_hook.handle_event(svc, "OnFocus", doc) is None
        assert save_hook.handle_event(svc, "OnSaveDone", doc) == 0
