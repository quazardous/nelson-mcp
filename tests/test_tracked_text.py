# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""text_read with tracked changes (GitHub #48)."""

import pytest

from plugin.modules.writer import equations as eq
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


class _MathObject:
    def __init__(self, name, formula, clsid=eq.MATH_CLSID.upper()):
        self.name, self.formula, self.clsid = name, formula, clsid

    def getName(self):
        return self.name

    def getPropertyValue(self, name):
        if name != "CLSID":
            raise KeyError(name)
        return self.clsid

    def getEmbeddedObject(self):
        return _Portion(Formula=self.formula)


class _FramePortion(_Portion):
    def __init__(self, *objects):
        super().__init__(TextPortionType="Frame")
        self.objects = objects

    def createContentEnumeration(self, service):
        return _Enum(self.objects)


def test_an_equation_only_paragraph_is_not_empty():
    # GitHub #49: the paragraph string leaves the formula out.
    walker = tt.Walker()
    segments = walker.paragraph_segments(
        _Para(_FramePortion(_MathObject("Object1", "{a} over {b}"))))
    assert tt.render(segments, "accepted") == "[equation: {a} over {b}]"
    assert walker.equations == [{"name": "Object1",
                                "formula": "{a} over {b}"}]
    assert not tt.has_changes(segments)


def test_an_inline_equation_keeps_its_place_and_other_objects_are_skipped():
    walker = tt.Walker()
    chart = _MathObject("Chart1", "", clsid="12dcae26-281f-416f-a234-c3086127382e")
    segments = walker.paragraph_segments(_Para(
        text("where x = "), _FramePortion(_MathObject("Object2", "sqrt{2}")),
        text(" here."), _FramePortion(chart)))
    assert tt.render(segments, "accepted") == \
        "where x = [equation: sqrt{2}] here."
    assert [f["name"] for f in walker.equations] == ["Object2"]


def test_an_equation_inside_a_tracked_insertion_follows_the_view():
    segments = tt.Walker().paragraph_segments(_Para(
        mark("6", "Insert", True),
        _FramePortion(_MathObject("Object3", "x^2")),
        mark("6", "Insert", False)))
    assert tt.render(segments, "accepted") == "[equation: x^2]"
    assert tt.render(segments, "original") == ""


def test_equations_in_a_paragraph_are_named_in_order():
    para = _Para(text("x = "), _FramePortion(_MathObject("Object1", "a")),
                 text(" and "), _FramePortion(_MathObject("Object2", "b")))
    assert eq.in_paragraph(para) == ["Object1", "Object2"]
    assert eq.in_paragraph(_Para(text("plain"))) == []
