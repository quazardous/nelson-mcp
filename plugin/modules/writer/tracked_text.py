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

Equations (GitHub #49) are embedded Math objects anchored as characters:
the paragraph's string leaves them out, so a paragraph holding only an
equation read as empty. The walk puts each one in the text as
[equation: <StarMath source>] and lists it, with its object name, in the
paragraph's equations.

render() is pure; paragraph_segments() walks UNO text portions.
"""

from plugin.modules.writer import equations as eq

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
        self.equations = []     # equations of the last paragraph walked

    def paragraph_segments(self, para):
        segments = []
        self.read.append(segments)
        self.equations = []
        portions = para.createEnumeration()
        while portions.hasMoreElements():
            portion = portions.nextElement()
            ptype = _prop(portion, "TextPortionType")
            if ptype == "Frame":
                for found in eq.in_portion(portion):
                    self.equations.append(found)
                    segments.append(["[equation: %s]" % found["formula"],
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


class Reader:
    """Paragraph text as text_read shows it, for any tool that reads text.

    The outline, nav_tree, heading content and the other readers used
    getString(), which runs tracked deletions into the text and leaves
    equations out (GitHub #48, #49). One Reader per pass over a document:
    read in document order, it follows changes across paragraphs. When the
    document has neither changes nor equations it is getString() and
    costs nothing more.
    """

    def __init__(self, doc, config=None):
        self.walker = None
        self.view = DEFAULT_VIEW
        if document_has_changes(doc) or document_has_equations(doc):
            self.walker = Walker()
            try:
                self.view = resolve_view(config.proxy_for("writer").get(
                    "tracked_changes_view"))
            except Exception:
                pass

    def text(self, para):
        if self.walker is None or not hasattr(para, "createEnumeration"):
            return para.getString()
        try:
            return render(self.walker.paragraph_segments(para), self.view)
        except Exception:
            return para.getString()


def reader(doc, services=None):
    config = None
    try:
        config = services.get("config") if services else None
    except Exception:
        pass
    return Reader(doc, config)


def deletions(doc):
    """(start, end) text ranges of the tracked deletions in *doc*."""
    found = []
    try:
        enum = doc.getRedlines().createEnumeration()
    except Exception:
        return found
    while enum.hasMoreElements():
        redline = enum.nextElement()
        if _prop(redline, "RedlineType") == "Delete":
            start, end = (_prop(redline, "RedlineStart"),
                          _prop(redline, "RedlineEnd"))
            if start is not None and end is not None:
                found.append((start, end))
    return found


def in_deletion(found, deleted):
    """True when the text range *found* lies inside a tracked deletion."""
    text = found.getText()
    for start, end in deleted:
        try:
            if text.compareRegionStarts(start, found.getStart()) >= 0 \
                    and text.compareRegionEnds(found.getEnd(), end) >= 0:
                return True
        except Exception:
            continue                # another text (table, frame): skip
    return False


def document_has_equations(doc):
    return bool(eq.math_objects(doc))


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
