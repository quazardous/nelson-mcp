# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""calc_columns — column widths, visibility and frozen panes (#2632)."""

import logging
import re

from plugin.framework.tool_base import ToolBase
from plugin.modules.calc.bridge import CalcBridge

log = logging.getLogger("nelson.calc")

_COLUMNS = re.compile(r"^([A-Za-z]{1,3})(?::([A-Za-z]{1,3}))?$")
_ACTIONS = ("width", "autofit", "hide", "show", "freeze", "unfreeze")


def parse_columns(text):
    """(first, last) 0-based column indexes of 'B' or 'A:C'."""
    from plugin.modules.calc.address_utils import column_to_index
    m = _COLUMNS.match((text or "").strip())
    if not m:
        raise ValueError("columns must look like 'B' or 'A:C', got %r"
                         % (text,))
    first = column_to_index(m.group(1))
    last = column_to_index(m.group(2)) if m.group(2) else first
    return min(first, last), max(first, last)


class CalcColumns(ToolBase):
    """Set column widths and visibility, freeze panes."""

    name = "calc_columns"
    intent = "edit"
    description = (
        "Column layout: action 'width' (width_mm), 'autofit' (optimal "
        "width for the content), 'hide' or 'show' on columns such as 'B' "
        "or 'A:C'; 'freeze' keeps the rows above and the columns left of "
        "cell (e.g. 'B2' freezes the header row and first column) in view, "
        "'unfreeze' removes it. Answers with the widths before and after."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(_ACTIONS),
                       "description": "What to do."},
            "columns": {
                "type": "string",
                "description": (
                    "Columns, e.g. 'B' or 'A:C'; may name the sheet "
                    "('Plan'.A:C). Not used by freeze/unfreeze."),
            },
            "width_mm": {"type": "number",
                         "description": "Width for action 'width', in mm."},
            "cell": {
                "type": "string",
                "description": "First cell below/right of the frozen area "
                               "for action 'freeze', e.g. 'B2'.",
            },
            "sheet_name": {"type": "string",
                           "description": "Sheet (default: active sheet)."},
        },
        "required": ["action"],
    }
    doc_types = ["calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from plugin.modules.calc.address_utils import (
            index_to_column, parse_address, split_sheet_prefix)

        action = kwargs.get("action")
        if action not in _ACTIONS:
            return {"status": "error", "code": "invalid_params",
                    "message": "action must be one of %s" % ", ".join(_ACTIONS),
                    "retryable": False}
        bridge = CalcBridge(ctx.doc)
        try:
            if action in ("freeze", "unfreeze"):
                ref = kwargs.get("cell") or "A1"
                if action == "freeze" and not kwargs.get("cell"):
                    raise ValueError("freeze needs cell, e.g. 'B2'.")
                sheet, address = bridge.resolve(ref, kwargs.get("sheet_name"))
                col, row = (0, 0) if action == "unfreeze" \
                    else parse_address(address)
                controller = ctx.doc.getCurrentController()
                controller.setActiveSheet(sheet)
                controller.freezeAtPosition(col, row)
                return {"status": "ok", "sheet": sheet.getName(),
                        "frozen": controller.hasFrozenPanes(),
                        "frozen_columns": col, "frozen_rows": row}

            ref = kwargs.get("columns")
            prefix, bare = split_sheet_prefix(ref or "")
            sheet_name = kwargs.get("sheet_name")
            if prefix and sheet_name and prefix.casefold() != sheet_name.casefold():
                raise ValueError("columns names sheet '%s' but sheet_name "
                                 "says '%s'." % (prefix, sheet_name))
            name = prefix or sheet_name
            sheet = bridge.get_sheet(name) if name else bridge.get_active_sheet()
            first, last = parse_columns(bare)
            if action == "width":
                width = kwargs.get("width_mm")
                if not isinstance(width, (int, float)) or isinstance(
                        width, bool) or not 1 <= width <= 1000:
                    raise ValueError("width needs width_mm between 1 and "
                                     "1000.")
            cols = sheet.getColumns()

            def widths():
                return {index_to_column(i): round(
                            cols.getByIndex(i).getPropertyValue("Width")
                            / 100.0, 1)
                        for i in range(first, last + 1)}

            before = widths()
            for i in range(first, last + 1):
                column = cols.getByIndex(i)
                if action == "width":
                    column.setPropertyValue("Width",
                                            int(round(kwargs["width_mm"] * 100)))
                elif action == "autofit":
                    column.setPropertyValue("OptimalWidth", True)
                elif action == "hide":
                    column.setPropertyValue("IsVisible", False)
                else:
                    column.setPropertyValue("IsVisible", True)
            return {"status": "ok", "sheet": sheet.getName(),
                    "columns": "%s:%s" % (index_to_column(first),
                                          index_to_column(last)),
                    "action": action, "before_mm": before,
                    "after_mm": widths()}
        except ValueError as e:
            return {"status": "error", "code": "invalid_params",
                    "message": str(e), "retryable": False}
