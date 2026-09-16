# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""calc_query — filter, sort and aggregate a sheet without changing it."""

import logging

from plugin.framework.tool_base import ToolBase
from plugin.modules.calc.bridge import CalcBridge

log = logging.getLogger("nelson.calc")


class QuerySheet(ToolBase):
    """Answer a question about a table without reading all of it."""

    name = "calc_query"
    intent = "navigate"
    description = (
        "Filter, sort and aggregate a table without reading it all and "
        "without changing the sheet. The first row of the range holds the "
        "headers; refer to columns by header name (case-insensitive) or "
        "letter. Example — top 10 emitters of 2022: where=[{column: 'year', "
        "op: '=', value: 2022}, {column: 'iso_code', op: 'not_empty'}], "
        "select=['country', 'co2'], order_by='co2 desc', limit=10. Only "
        "the columns used are read, so pass select on wide sheets. Returns "
        "compact rows, the number of matching rows and whether the result "
        "was truncated."
    )
    parameters = {
        "type": "object",
        "properties": {
            "range": {
                "type": "string",
                "description": (
                    "Table range including the header row (e.g. "
                    "'owid-co2'.A1:CA50412). Default: the used area of the "
                    "sheet."),
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet (default: active sheet).",
            },
            "where": {
                "type": "array",
                "description": (
                    "Conditions, all required: {column, op, value}. op: "
                    "=, !=, >, >=, <, <=, contains, in (value is a list), "
                    "empty, not_empty. Numbers stored as text compare as "
                    "numbers."),
                "items": {"type": "object"},
            },
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Columns to return (default: all).",
            },
            "order_by": {
                "type": ["string", "array"],
                "description": (
                    "'column', 'column desc', or a list of those or of "
                    "{column, desc}. Empty cells sort last."),
            },
            "limit": {
                "type": "integer",
                "description": "Rows to return (default 50, at most 1000).",
            },
            "group_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Group rows by these columns.",
            },
            "aggregate": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Per group: {column, fn, as?} with fn sum, avg, min, "
                    "max or count ({fn: 'count'} counts rows). Name the "
                    "result in order_by as 'fn(header)' or its 'as'."),
            },
        },
        "required": [],
    }
    doc_types = ["calc"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        from plugin.modules.calc import query_engine as qe
        from plugin.modules.calc.address_utils import index_to_column

        bridge = CalcBridge(ctx.doc)
        try:
            sheet, top, bottom = _table_bounds(bridge, kwargs.get("range"),
                                               kwargs.get("sheet_name"))
            c1, r1, c2 = top[0], top[1], bottom[0]
            r2 = bottom[1]
            headers = list(sheet.getCellRangeByPosition(
                c1, r1, c2, r1).getDataArray()[0])
            needed = _needed_columns(qe, headers, kwargs)
            count = r2 - r1
            rows = [[None] * len(headers) for _ in range(count)]
            if count > 0:
                for i in needed:
                    column = sheet.getCellRangeByPosition(
                        c1 + i, r1 + 1, c1 + i, r2).getDataArray()
                    for r, (value,) in enumerate(column):
                        rows[r][i] = None if value == "" else value
            result = qe.run_query(
                headers, rows,
                where=kwargs.get("where"), select=kwargs.get("select"),
                order_by=kwargs.get("order_by"),
                limit=kwargs.get("limit", 50),
                group_by=kwargs.get("group_by"),
                aggregate=kwargs.get("aggregate"))
        except (qe.QueryError, ValueError) as e:
            return {"status": "error", "code": "invalid_query",
                    "message": str(e), "retryable": False}
        return {
            "status": "ok",
            "table": "%s.%s%d:%s%d" % (sheet.getName(), index_to_column(c1),
                                       r1 + 1, index_to_column(c2), r2 + 1),
            "data_rows": count,
            "columns_read": len(needed),
            **result,
        }


def _table_bounds(bridge, range_ref, sheet_name):
    """(sheet, (col, row) of the header row start, (col, row) of the end)."""
    if range_ref:
        sheet, address = bridge.resolve(range_ref, sheet_name)
        (c1, r1), (c2, r2) = bridge.parse_range_string(address)
        return sheet, (min(c1, c2), min(r1, r2)), (max(c1, c2), max(r1, r2))
    sheet = (bridge.get_sheet(sheet_name) if sheet_name
             else bridge.get_active_sheet())
    cursor = sheet.createCursor()
    cursor.gotoStartOfUsedArea(False)
    cursor.gotoEndOfUsedArea(True)
    a = cursor.getRangeAddress()
    return sheet, (a.StartColumn, a.StartRow), (a.EndColumn, a.EndRow)


def _needed_columns(qe, headers, kwargs):
    """Indexes of the columns the query reads; all when none is named."""
    refs = [c.get("column") for c in kwargs.get("where") or []
            if isinstance(c, dict)]
    grouping = kwargs.get("group_by") or kwargs.get("aggregate")
    refs += list(kwargs.get("group_by") or [])
    refs += [a.get("column") for a in kwargs.get("aggregate") or []
             if isinstance(a, dict) and a.get("column") is not None]
    if not grouping:
        if not kwargs.get("select"):
            return list(range(len(headers)))
        refs += list(kwargs["select"])
        refs += [col for col, _ in qe._order_specs(kwargs.get("order_by"))]
    return sorted({qe.resolve_column(headers, r) for r in refs})
