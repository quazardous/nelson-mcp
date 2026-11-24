# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer helper operations used by tools.

Low-level UNO helpers for paragraph navigation, selection ranges,
and text cursor manipulation. Tools delegate here rather than
duplicating UNO details.
"""

import logging

log = logging.getLogger("nelson.writer")


def find_paragraph_for_range(anchor, para_ranges, text_obj):
    """Return the 0-based paragraph index that contains *anchor*.

    Iterates *para_ranges* and uses ``compareRegionStarts`` on
    *text_obj* to locate the paragraph whose start/end brackets
    the anchor's start position.

    Returns 0 if no match is found.
    """
    try:
        match_start = anchor.getStart()
        for i, para in enumerate(para_ranges):
            try:
                cmp_start = text_obj.compareRegionStarts(
                    match_start, para.getStart()
                )
                cmp_end = text_obj.compareRegionStarts(
                    match_start, para.getEnd()
                )
                if cmp_start <= 0 and cmp_end >= 0:
                    return i
            except Exception:
                continue
    except Exception:
        log.debug("find_paragraph_for_range: failed", exc_info=True)
    return 0


def get_selection_range(model):
    """Return ``(start_offset, end_offset)`` character positions of the
    current selection (or cursor insertion point).

    Returns ``(0, 0)`` on error or when no text range is available.
    """
    try:
        sel = model.getCurrentController().getSelection()
        if not sel or sel.getCount() == 0:
            rng = model.getCurrentController().getViewCursor()
        else:
            rng = sel.getByIndex(0)

        if not rng or not hasattr(rng, "getStart") or not hasattr(rng, "getEnd"):
            return (0, 0)

        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoRange(rng.getStart(), True)
        start_offset = len(cursor.getString())

        cursor.gotoStart(False)
        cursor.gotoRange(rng.getEnd(), True)
        end_offset = len(cursor.getString())

        return (start_offset, end_offset)
    except Exception:
        log.debug("get_selection_range: failed", exc_info=True)
        return (0, 0)


# goRight(nCount, bExpand) takes a short; max 32767 per call.
_GO_RIGHT_CHUNK = 8192


def get_text_cursor_at_range(model, start, end):
    """Create a text cursor that selects the character range ``[start, end)``.

    Offsets are the ones text_find and the selection report: the length of
    the body text before a point, as getString() counts it. That count
    includes table cells and tracked deletions but not equations and other
    objects anchored as characters, while goRight() steps over those too:
    moving goRight(start) from the top drifted one character per object,
    which is the "range coordinate mismatch" of docs/known-issues.md.
    The positions are found by measuring instead; see position_at.

    Returns ``None`` on error or invalid range.
    """
    try:
        doc_len = _doc_length(model)
        start = max(0, min(start, doc_len))
        end = max(0, min(end, doc_len))
        if start > end:
            start, end = end, start
        text = model.getText()
        layout = body_offsets(text)
        first = position_at(text, layout, start)
        last = position_at(text, layout, end, at_end=True)
        cursor = text.createTextCursorByRange(first)
        cursor.gotoRange(last, True)
        return cursor
    except Exception:
        log.debug("get_text_cursor_at_range: failed", exc_info=True)
        return None


def body_offsets(text):
    """[(element, is_table, start, end)] for the body, in text_find offsets.

    A paragraph spans its getString() and is followed by one break. A
    table's span is measured: the offset of the paragraph after it.
    """
    layout = []
    enum = text.createEnumeration()
    offset = 0
    after_table = False
    while enum.hasMoreElements():
        el = enum.nextElement()
        if el.supportsService("com.sun.star.text.TextTable"):
            layout.append([el, True, offset, None])
            after_table = True
            continue
        if after_table:
            offset = _measure(text, el.getStart())
            layout[-1][3] = max(layout[-1][2], offset - 1)
            after_table = False
        end = offset + len(el.getString())
        layout.append([el, False, offset, end])
        offset = end + 1
    if after_table:
        layout[-1][3] = layout[-1][2]
    return layout


def position_at(text, layout, offset, at_end=False):
    """A text range at *offset* (see body_offsets).

    An offset inside a table snaps outside it, so the table is kept whole:
    a start to the end of the paragraph before it, an end to the start of
    the paragraph after it. With *at_end*, objects sitting right at the
    offset are taken in (the end of a range includes them).
    """
    paras = [e for e in layout if not e[1]]
    if not paras:
        return text.getStart()
    for i, (el, is_table, s, e) in enumerate(layout):
        if is_table and s <= offset <= (e or s):
            if at_end:
                nxt = next((x for x in layout[i + 1:] if not x[1]), None)
                return nxt[0].getStart() if nxt else text.getEnd()
            prev = next((x for x in reversed(layout[:i]) if not x[1]), None)
            return prev[0].getEnd() if prev else text.getStart()
        if not is_table and s <= offset <= e:
            return _inside(text, el, offset - s, at_end)
    return text.getEnd()


def _inside(text, para, k, at_end):
    """The point *k* characters (getString count) into *para*."""
    cursor = text.createTextCursorByRange(para.getStart())
    # Objects add steps but no characters, so stepping the characters still
    # missing never overshoots: repeat until the count is reached.
    got = 0
    for _ in range(10000):              # a pass short only by objects
        if got >= k or not cursor.goRight(
                min(k - got, _GO_RIGHT_CHUNK), True):
            break
        got = len(cursor.getString())
    if at_end:
        while True:
            probe = text.createTextCursorByRange(cursor)
            if not probe.goRight(1, True) or len(probe.getString()) != k \
                    or text.compareRegionEnds(probe, para.getEnd()) < 0:
                break
            cursor = probe
    end = cursor.getEnd()
    return text.createTextCursorByRange(end)


def _measure(text, point):
    cursor = text.createTextCursor()
    cursor.gotoStart(False)
    cursor.gotoRange(point, True)
    return len(cursor.getString())


def _doc_length(model):
    """Return total character length of the document body text."""
    try:
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        return len(cursor.getString())
    except Exception:
        return 0
