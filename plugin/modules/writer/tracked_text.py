# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Paragraph text with tracked changes, as text_read shows it (GitHub #48).

A tracked replace keeps both texts in the paragraph: getString() returned
"DeltaBeta paragraph." for Beta replaced by Delta, with nothing to tell the
deleted part from the inserted one. An agent checking its own edit took
that for duplicated text.

The setting writer.tracked_changes_view chooses what text_read returns:

- accepted: the text as it reads once every change is accepted (default);
- original: the text as it read before the changes;
- marked:   both, insertions in <ins>, deletions in <del>.

Formulas (GitHub #49) are embedded objects anchored as characters: the
paragraph's string leaves them out, so a formula-only paragraph read as
empty. The walk puts each one in the text as [formula: <StarMath source>]
and lists it, with its object name, in the paragraph's formulas.

render() is pure; paragraph_segments() walks UNO text portions.
"""

# CLSID of LibreOffice Math objects.
MATH_CLSID = "078b7aba-54fc-457f-8551-6147e776a997"

VIEWS = ("accepted", "original", "marked")
DEFAULT_VIEW = "accepted"

# Redline types that change the text. Format and ParagraphFormat changes
# leave it as it is.
_TEXT_KINDS = {"Insert": "insert", "Delete": "delete"}


def resolve_view(value):
    """The configured view, or the default for anything unknown."""
    return value if value in VIEWS else DEFAULT_VIEW


def render(segments, view):
    """Join (text, kind) segments for *view*. kind: None, insert, delete."""
    out = []
    for text, kind in segments:
        if kind is None:
            out.append(text)
        elif view == "marked":
            tag = "ins" if kind == "insert" else "del"
            out.append("<%s>%s</%s>" % (tag, text, tag))
        elif (kind == "insert") == (view == "accepted"):
            out.append(text)
    return "".join(out)


def has_changes(segments):
    return any(kind for text, kind in segments if text)


class Walker:
    """Splits consecutive paragraphs into segments.

    A change may span paragraphs, so the open changes carry from one
    paragraph to the next. A change that began before the first paragraph
    read shows up as an end with no start: everything read before that end
    belonged to it, since changes do not overlap. That can relabel
    paragraphs already walked, so render only once the window is walked.
    """

    def __init__(self):
        self.open = {}          # redline id -> kind
        self.read = []          # every segment list returned, in order
        self.formulas = []      # formulas of the last paragraph walked

    def paragraph_segments(self, para):
        segments = []
        self.read.append(segments)
        self.formulas = []
        portions = para.createEnumeration()
        while portions.hasMoreElements():
            portion = portions.nextElement()
            ptype = _prop(portion, "TextPortionType")
            if ptype == "Frame":
                for formula in _formulas_in(portion):
                    self.formulas.append(formula)
                    segments.append(["[formula: %s]" % formula["formula"],
                                     self._kind()])
                continue
            if ptype != "Redline":
                text = portion.getString()
                if text:
                    segments.append([text, self._kind()])
                continue
            kind = _TEXT_KINDS.get(_prop(portion, "RedlineType"))
            if kind is None:
                continue
            rid = _prop(portion, "RedlineIdentifier")
            if _prop(portion, "IsStart"):
                self.open[rid] = kind
            elif rid in self.open:
                del self.open[rid]
            else:
                self._began_before_window(kind)
        return segments

    def _kind(self):
        # Changes do not overlap, so at most one is open.
        return next(iter(self.open.values()), None)

    def _began_before_window(self, kind):
        for segments in self.read:
            for s in segments:
                s[1] = kind


def _formulas_in(portion):
    """The Math objects a Frame portion anchors, in order."""
    found = []
    try:
        contents = portion.createContentEnumeration(
            "com.sun.star.text.TextContent")
    except Exception:
        return found
    while contents.hasMoreElements():
        obj = contents.nextElement()
        if not _is_math(obj):
            continue
        try:
            source = obj.getEmbeddedObject().getPropertyValue("Formula")
        except Exception:
            source = ""
        found.append({"name": obj.getName(), "formula": source})
    return found


def _is_math(obj):
    clsid = _prop(obj, "CLSID")
    return isinstance(clsid, str) and clsid.lower() == MATH_CLSID


def document_has_formulas(doc):
    try:
        objects = doc.getEmbeddedObjects()
        return any(_is_math(objects.getByName(n))
                   for n in objects.getElementNames())
    except Exception:
        return False


def document_has_changes(doc):
    try:
        return doc.getRedlines().createEnumeration().hasMoreElements()
    except Exception:
        return False


def _prop(obj, name):
    try:
        return obj.getPropertyValue(name)
    except Exception:
        return None
