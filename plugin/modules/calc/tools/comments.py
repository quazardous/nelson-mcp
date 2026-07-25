# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Calc cell annotation (comment) tools."""

import logging

from plugin.framework.tool_base import ToolBase
from plugin.modules.calc.address_utils import (
    index_to_column,
    parse_range_string,
)

log = logging.getLogger("nelson.calc")


def _resolve_sheet(doc, sheet_name=None):
    """Return the target sheet (by name or active)."""
    if sheet_name:
        sheets = doc.getSheets()
        if not sheets.hasByName(sheet_name):
            raise ValueError("Sheet not found: %s" % sheet_name)
        return sheets.getByName(sheet_name)
    controller = doc.getCurrentController()
    if hasattr(controller, "getActiveSheet"):
        return controller.getActiveSheet()
    return doc.getSheets().getByIndex(0)


def _cell_label(col, row):
    return "%s%d" % (index_to_column(col), row + 1)


def _parse_cell_ref(cell_ref):
    """Parse 'B3' into (col, row) 0-based tuple."""
    (col, row), _ = parse_range_string(cell_ref)
    return col, row


def _annotation_text(sheet, col, row):
    """Read a cell note's text, working around lazy captions on .xlsx.

    A workbook loaded from .xlsx has no caption object for its notes until
    something asks for one, and until then every XSheetAnnotation read path
    returns an empty string — while the text is plainly there in
    xl/comments*.xml. Reported by @braklo on #21.

    ``getAnnotationShape()`` resolves it: LibreOffice implements it as
    ``GetOrCreateCaption()`` (sc/source/ui/unoobj/notesuno.cxx), so the
    caption is materialised on demand and the shape's text is readable.
    Unlike forcing ``setIsVisible(True)``, this does not route through
    ShowNote, so it neither changes what the user sees nor pushes an undo
    action.
    """
    cell_ann = sheet.getCellByPosition(col, row).getAnnotation()
    text = ""
    try:
        text = cell_ann.getString()
    except Exception:
        pass
    if text:
        return cell_ann, text
    try:
        shape = cell_ann.getAnnotationShape()
        if shape is not None:
            text = shape.getString() or ""
    except Exception:
        pass  # optional interface — older builds may not offer it
    return cell_ann, text


class CalcComment(ToolBase):
    """List, add or delete Calc cell comments (annotations)."""

    name = "calc_comment"
    aliases = {
        "calc_comment_list": {"action": "list"},
        "calc_comment_add": {"action": "add"},
        "calc_comment_delete": {"action": "delete"},
        "list_cell_comments": {"action": "list"},
        "add_cell_comment": {"action": "add"},
        "delete_cell_comment": {"action": "delete"},
    }
    intent = "review"
    description = (
        "Work with cell comments (annotations) in a Calc sheet. "
        "action='list' returns every comment with its cell, author, date "
        "and text; action='add' sets the comment on a cell (replacing any "
        "existing one); action='delete' removes it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "delete"],
                "description": "What to do (default: list).",
            },
            "cell": {
                "type": "string",
                "description": "Cell address, e.g. 'B3'. Required to add or delete.",
            },
            "text": {
                "type": "string",
                "description": "Comment text. Required to add.",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": [],
    }
    doc_types = ["calc"]

    def detects_mutation(self, **kwargs):
        # Listing is a read; adding and deleting are not.
        return kwargs.get("action", "list") != "list"

    def execute(self, ctx, **kwargs):
        action = kwargs.get("action", "list")
        try:
            sheet = _resolve_sheet(ctx.doc, kwargs.get("sheet_name"))
        except Exception as e:
            return {"status": "error", "error": str(e)}

        if action == "list":
            return self._list(sheet)

        cell_ref = kwargs.get("cell", "")
        if not cell_ref:
            return {"status": "error",
                    "message": "cell is required to %s a comment." % action}
        try:
            col, row = _parse_cell_ref(cell_ref)
        except Exception as e:
            return {"status": "error", "error": str(e)}

        if action == "add":
            return self._add(sheet, cell_ref, col, row, kwargs.get("text", ""))
        return self._delete(sheet, cell_ref, col, row)

    def _list(self, sheet):
        try:
            annotations = sheet.getAnnotations()
            comments = []
            for i in range(annotations.getCount()):
                ann = annotations.getByIndex(i)
                pos = ann.getPosition()
                # Read text/date through the cell's own CellAnnotation
                # (as the write path does), not the XSheetAnnotations
                # collection item, whose getString()/getDate() come back
                # empty in current LibreOffice (#21).
                cell_ann, text = _annotation_text(
                    sheet, pos.Column, pos.Row)
                comments.append({
                    "cell": _cell_label(pos.Column, pos.Row),
                    "author": ann.getAuthor(),
                    # .xlsx has no date field on a comment at all
                    # (<comment ref=".." authorId=".."/>), so an empty
                    # date there is the format, not a failure.
                    "date": cell_ann.getDate(),
                    "text": text,
                    "is_visible": ann.getIsVisible(),
                })
            return {
                "status": "ok",
                "comments": comments,
                "count": len(comments),
                "sheet": sheet.getName(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _add(self, sheet, cell_ref, col, row, text):
        if not text:
            return {"status": "error", "message": "text is required to add."}
        try:
            from com.sun.star.table import CellAddress
            addr = CellAddress()
            addr.Sheet = sheet.getRangeAddress().Sheet
            addr.Column = col
            addr.Row = row

            cell = sheet.getCellByPosition(col, row)
            ann = cell.getAnnotation()
            if ann and ann.getString():
                ann.setString(text)
            else:
                sheet.getAnnotations().insertNew(addr, text)
            return {
                "status": "ok",
                "cell": cell_ref,
                "text": text,
                "sheet": sheet.getName(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _delete(self, sheet, cell_ref, col, row):
        try:
            annotations = sheet.getAnnotations()
            for i in range(annotations.getCount()):
                pos = annotations.getByIndex(i).getPosition()
                if pos.Column == col and pos.Row == row:
                    annotations.removeByIndex(i)
                    return {"status": "ok", "cell": cell_ref,
                            "message": "Comment deleted."}
            return {"status": "error",
                    "message": "No comment found at %s." % cell_ref}
        except Exception as e:
            return {"status": "error", "error": str(e)}
