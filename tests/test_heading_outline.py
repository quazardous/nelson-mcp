# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""nav_outline paths and nav_heading_content lookup (#2626)."""

from plugin.modules.core.services.document import DocumentService
from plugin.modules.writer.tools import outline


class Para:
    def __init__(self, level, text):
        self.level, self.text = level, text

    def getPropertyValue(self, name):
        return self.level

    def getString(self):
        return self.text


class Table:
    """A body element with no OutlineLevel, like a text table."""

    def getPropertyValue(self, name):
        raise AttributeError(name)


class Enum:
    def __init__(self, items):
        self._items = list(items)

    def hasMoreElements(self):
        return bool(self._items)

    def nextElement(self):
        return self._items.pop(0)


class Doc:
    def __init__(self, elements):
        self.elements = elements

    def getText(self):
        return self

    def createEnumeration(self):
        return Enum(self.elements)


BODY = [
    Para(2, "Front matter"),     # 0  orphan level 2 before the first level 1
    Para(1, "Chapter 1"),        # 1
    Para(2, "Notes"),            # 2
    Para(0, "first notes"),      # 3
    Table(),                     # 4  counts as a body element
    Para(1, "Chapter 2"),        # 5
    Para(2, "Notes"),            # 6
    Para(0, "second notes"),     # 7
]


def tree():
    svc = DocumentService.__new__(DocumentService)
    return svc.build_heading_tree(Doc(BODY))


def test_paths_and_indexes():
    flat = {n["path"]: (n["title"], n["para_index"])
            for n in outline._flatten(tree())}
    assert flat == {
        "1": ("Front matter", 0),
        "2": ("Chapter 1", 1),
        "2.1": ("Notes", 2),
        "3": ("Chapter 2", 5),
        "3.1": ("Notes", 6),
    }


def test_path_lookup_reaches_the_right_duplicate():
    node, err = outline._find_heading(tree(), "3.1")
    assert err is None and node["para_index"] == 6


def test_unique_title_is_accepted():
    node, err = outline._find_heading(tree(), "Chapter 2")
    assert err is None and node["path"] == "3"


def test_ambiguous_title_lists_paths():
    node, err = outline._find_heading(tree(), "Notes")
    assert node is None and "2.1, 3.1" in err


def test_unknown_path_and_title():
    assert outline._find_heading(tree(), "9.9")[0] is None
    node, err = outline._find_heading(tree(), "CHAPTER 9. Nope")
    assert node is None and "Invalid heading path" in err
