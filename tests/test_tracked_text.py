# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""text_read with tracked changes (GitHub #48)."""

import pytest

from plugin.modules.writer import tracked_text as tt


class _Portion:
    def __init__(self, text="", **props):
        self.text = text
        self.props = props

    def getString(self):
        return self.text

    def getPropertyValue(self, name):
        if name not in self.props:
            raise KeyError(name)
        return self.props[name]


class _Enum:
    def __init__(self, items):
        self.items = list(items)

    def hasMoreElements(self):
        return bool(self.items)

    def nextElement(self):
        return self.items.pop(0)


class _Para:
    def __init__(self, *portions):
        self.portions = portions

    def createEnumeration(self):
        return _Enum(self.portions)


def text(s):
    return _Portion(s, TextPortionType="Text")


def mark(rid, kind, start):
    return _Portion(TextPortionType="Redline", RedlineType=kind,
                    RedlineIdentifier=rid, IsStart=start)


# "Beta" replaced by "Delta" with recording on: what issue #48 read back as
# "DeltaBeta paragraph."
REPLACED = _Para(mark("1", "Insert", True), text("Delta"),
                 mark("1", "Insert", False), mark("2", "Delete", True),
                 text("Beta"), mark("2", "Delete", False), text(" paragraph."))


@pytest.mark.parametrize("view, expected", [
    ("accepted", "Delta paragraph."),
    ("original", "Beta paragraph."),
    ("marked", "<ins>Delta</ins><del>Beta</del> paragraph."),
])
def test_a_tracked_replace_reads_per_view(view, expected):
    segments = tt.Walker().paragraph_segments(REPLACED)
    assert tt.render(segments, view) == expected
    assert tt.has_changes(segments)


def test_formatting_changes_leave_the_text_alone():
    para = _Para(text("Plain "), mark("3", "Format", True), text("bold"),
                 mark("3", "Format", False))
    segments = tt.Walker().paragraph_segments(para)
    assert tt.render(segments, "accepted") == "Plain bold"
    assert not tt.has_changes(segments)


def test_a_deletion_carries_across_paragraphs():
    walker = tt.Walker()
    first = walker.paragraph_segments(
        _Para(text("Keep "), mark("4", "Delete", True), text("gone")))
    middle = walker.paragraph_segments(_Para(text("all gone")))
    last = walker.paragraph_segments(
        _Para(text("gone too"), mark("4", "Delete", False), text(" kept")))
    assert tt.render(first, "accepted") == "Keep "
    assert tt.render(middle, "accepted") == ""
    assert tt.render(last, "accepted") == " kept"
    assert tt.render(middle, "original") == "all gone"


def test_a_change_begun_before_the_window_is_recognised():
    # The read starts inside a deletion: its start is never seen, its end is.
    walker = tt.Walker()
    first = walker.paragraph_segments(_Para(text("deleted earlier")))
    second = walker.paragraph_segments(
        _Para(text("still deleted"), mark("5", "Delete", False),
              text(" visible")))
    assert tt.render(first, "accepted") == ""
    assert tt.render(second, "accepted") == " visible"
    assert tt.render(second, "marked") == \
        "<del>still deleted</del> visible"


@pytest.mark.parametrize("value, view", [
    ("marked", "marked"), ("original", "original"),
    (None, "accepted"), ("", "accepted"), ("bogus", "accepted"),
])
def test_unknown_settings_fall_back_to_accepted(value, view):
    assert tt.resolve_view(value) == view
