# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Calc conditional formatting tools.

Uses XSheetConditionalEntries on cell ranges to list, add, and remove
conditional format rules.
"""

import logging

from plugin.framework.tool_base import ToolBase
from plugin.modules.calc.address_utils import parse_range_string, index_to_column

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


# Operator mapping: name -> com.sun.star.sheet.ConditionOperator enum value
_OPERATOR_NAMES = {
    "NONE": 0,
    "EQUAL": 1,
    "NOT_EQUAL": 2,
    "GREATER": 3,
    "GREATER_EQUAL": 4,
    "LESS": 5,
    "LESS_EQUAL": 6,
    "BETWEEN": 7,
    "NOT_BETWEEN": 8,
    "FORMULA": 9,
}

_OPERATOR_REVERSE = {v: k for k, v in _OPERATOR_NAMES.items()}


def _entry_to_dict(entry, idx):
    """Convert a conditional entry to a readable dict.

    XSheetConditionalEntry implements:
    - XSheetCondition: getOperator(), getFormula1(), getFormula2()
    - XPropertySet: StyleName property
    """
    result = {"index": idx}
    # XSheetCondition methods
    try:
        op = entry.getOperator()
        # UNO enum: try .value (string name) then numeric lookup
        op_name = str(op.value) if hasattr(op, "value") else str(op)
        # The .value may be the enum name directly (e.g. "LESS")
        if op_name in _OPERATOR_NAMES:
            result["operator"] = op_name
        else:
            # Try numeric
            try:
                result["operator"] = _OPERATOR_REVERSE.get(int(op_name), op_name)
            except (ValueError, TypeError):
                result["operator"] = op_name
    except Exception:
        pass
    try:
        f1 = entry.getFormula1()
        if f1:
            result["formula1"] = f1
    except Exception:
        pass
    try:
        f2 = entry.getFormula2()
        if f2 and f2 != "0":
            result["formula2"] = f2
    except Exception:
        pass
    # StyleName — try XPropertySet, then direct attribute
    try:
        sn = entry.getPropertyValue("StyleName")
        if sn:
            result["style_name"] = sn
    except Exception:
        try:
            if hasattr(entry, "StyleName") and entry.StyleName:
                result["style_name"] = entry.StyleName
        except Exception:
            log.debug("Could not read StyleName from conditional entry %d", idx)
    return result


class ListConditionalFormats(ToolBase):
    """List conditional formatting rules on a cell range."""

    name = "calc_condformat_list"
    aliases = ["list_conditional_formats"]
    intent = "navigate"
    description = (
        "List conditional formatting rules on a Calc cell range. "
        "Returns operator, formulas, and applied cell style for each rule."
    )
    parameters = {
        "type": "object",
        "properties": {
            "cell_range": {
                "type": "string",
                "description": "Cell range (e.g. 'A1:D10'). If omitted, scans used area.",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": [],
    }
    doc_types = ["calc"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        try:
            doc = ctx.doc
            sheet = _resolve_sheet(doc, kwargs.get("sheet_name"))

            cell_range_str = kwargs.get("cell_range")
            if cell_range_str:
                cell_range = sheet.getCellRangeByName(cell_range_str)
            else:
                cursor = sheet.createCursor()
                cursor.gotoStartOfUsedArea(False)
                cursor.gotoEndOfUsedArea(True)
                cell_range = cursor

            formats = cell_range.getPropertyValue("ConditionalFormat")
            if formats is None or formats.getCount() == 0:
                return {
                    "status": "ok",
                    "sheet": sheet.getName(),
                    "rules": [],
                    "count": 0,
                }

            rules = []
            for i in range(formats.getCount()):
                entry = formats.getByIndex(i)
                rules.append(_entry_to_dict(entry, i))

            return {
                "status": "ok",
                "sheet": sheet.getName(),
                "cell_range": cell_range_str or "(used area)",
                "rules": rules,
                "count": len(rules),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class AddConditionalFormat(ToolBase):
    """Add a conditional formatting rule to a cell range."""

    name = "calc_condformat_add"
    aliases = ["add_conditional_format"]
    intent = "edit"
    description = (
        "Add a conditional formatting rule to a Calc cell range. "
        "Applies a cell style when the condition is met. "
        "Operators: EQUAL, NOT_EQUAL, GREATER, GREATER_EQUAL, LESS, "
        "LESS_EQUAL, BETWEEN, NOT_BETWEEN, FORMULA."
    )
    parameters = {
        "type": "object",
        "properties": {
            "cell_range": {
                "type": "string",
                "description": "Cell range to apply the rule to (e.g. 'A1:D10').",
            },
            "operator": {
                "type": "string",
                "description": (
                    "Condition operator: EQUAL, NOT_EQUAL, GREATER, "
                    "GREATER_EQUAL, LESS, LESS_EQUAL, BETWEEN, NOT_BETWEEN, "
                    "FORMULA."
                ),
            },
            "formula1": {
                "type": "string",
                "description": (
                    "First formula/value. For FORMULA operator, this is the "
                    "condition formula (e.g. 'A1>100'). For value operators, "
                    "the comparison value (e.g. '50')."
                ),
            },
            "formula2": {
                "type": "string",
                "description": "Second formula/value (only for BETWEEN/NOT_BETWEEN).",
            },
            "style_name": {
                "type": "string",
                "description": (
                    "Cell style to apply when condition is true. "
                    "Use style_list with family='CellStyles' to see available styles."
                ),
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": ["cell_range", "operator", "formula1", "style_name"],
    }
    doc_types = ["calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        try:
            doc = ctx.doc
            sheet = _resolve_sheet(doc, kwargs.get("sheet_name"))

            cell_range_str = kwargs["cell_range"]
            cell_range = sheet.getCellRangeByName(cell_range_str)

            operator = kwargs["operator"].upper()
            if operator not in _OPERATOR_NAMES:
                return {
                    "status": "error",
                    "message": "Unknown operator: %s" % operator,
                    "available": list(_OPERATOR_NAMES.keys()),
                }

            from com.sun.star.sheet.ConditionOperator import (
                NONE as CO_NONE,
                EQUAL as CO_EQUAL,
                NOT_EQUAL as CO_NOT_EQUAL,
                GREATER as CO_GREATER,
                GREATER_EQUAL as CO_GREATER_EQUAL,
                LESS as CO_LESS,
                LESS_EQUAL as CO_LESS_EQUAL,
                BETWEEN as CO_BETWEEN,
                NOT_BETWEEN as CO_NOT_BETWEEN,
                FORMULA as CO_FORMULA,
            )

            op_map = {
                "NONE": CO_NONE,
                "EQUAL": CO_EQUAL,
                "NOT_EQUAL": CO_NOT_EQUAL,
                "GREATER": CO_GREATER,
                "GREATER_EQUAL": CO_GREATER_EQUAL,
                "LESS": CO_LESS,
                "LESS_EQUAL": CO_LESS_EQUAL,
                "BETWEEN": CO_BETWEEN,
                "NOT_BETWEEN": CO_NOT_BETWEEN,
                "FORMULA": CO_FORMULA,
            }

            from com.sun.star.beans import PropertyValue

            props = []

            pv = PropertyValue()
            pv.Name = "Operator"
            pv.Value = op_map[operator]
            props.append(pv)

            pv = PropertyValue()
            pv.Name = "Formula1"
            pv.Value = kwargs["formula1"]
            props.append(pv)

            formula2 = kwargs.get("formula2", "")
            if formula2:
                pv = PropertyValue()
                pv.Name = "Formula2"
                pv.Value = formula2
                props.append(pv)

            pv = PropertyValue()
            pv.Name = "StyleName"
            pv.Value = kwargs["style_name"]
            props.append(pv)

            formats = cell_range.getPropertyValue("ConditionalFormat")
            formats.addNew(tuple(props))
            cell_range.setPropertyValue("ConditionalFormat", formats)

            return {
                "status": "ok",
                "cell_range": cell_range_str,
                "operator": operator,
                "formula1": kwargs["formula1"],
                "style_name": kwargs["style_name"],
                "rule_count": formats.getCount(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class RemoveConditionalFormat(ToolBase):
    """Remove a conditional formatting rule from a cell range."""

    name = "calc_condformat_remove"
    aliases = ["remove_conditional_format"]
    intent = "edit"
    description = (
        "Remove a conditional formatting rule from a Calc cell range by index. "
        "Use calc_condformat_list to see current rules and their indices."
    )
    parameters = {
        "type": "object",
        "properties": {
            "cell_range": {
                "type": "string",
                "description": "Cell range (e.g. 'A1:D10').",
            },
            "rule_index": {
                "type": "integer",
                "description": "0-based index of the rule to remove.",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": ["cell_range", "rule_index"],
    }
    doc_types = ["calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        try:
            doc = ctx.doc
            sheet = _resolve_sheet(doc, kwargs.get("sheet_name"))

            cell_range_str = kwargs["cell_range"]
            cell_range = sheet.getCellRangeByName(cell_range_str)
            rule_index = kwargs["rule_index"]

            formats = cell_range.getPropertyValue("ConditionalFormat")
            if formats is None or formats.getCount() == 0:
                return {"status": "error", "message": "No conditional formats on this range."}

            if rule_index < 0 or rule_index >= formats.getCount():
                return {
                    "status": "error",
                    "message": "Rule index %d out of range (0..%d)." % (
                        rule_index, formats.getCount() - 1
                    ),
                }

            formats.removeByIndex(rule_index)
            cell_range.setPropertyValue("ConditionalFormat", formats)

            return {
                "status": "ok",
                "cell_range": cell_range_str,
                "removed_index": rule_index,
                "remaining_rules": formats.getCount(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class ClearConditionalFormats(ToolBase):
    """Clear all conditional formatting from a cell range."""

    name = "calc_condformat_clear"
    aliases = ["clear_conditional_formats"]
    intent = "edit"
    description = "Remove all conditional formatting rules from a Calc cell range."
    parameters = {
        "type": "object",
        "properties": {
            "cell_range": {
                "type": "string",
                "description": "Cell range (e.g. 'A1:D10').",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": ["cell_range"],
    }
    doc_types = ["calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        try:
            doc = ctx.doc
            sheet = _resolve_sheet(doc, kwargs.get("sheet_name"))

            cell_range_str = kwargs["cell_range"]
            cell_range = sheet.getCellRangeByName(cell_range_str)

            formats = cell_range.getPropertyValue("ConditionalFormat")
            formats.clear()
            cell_range.setPropertyValue("ConditionalFormat", formats)

            return {"status": "ok", "cell_range": cell_range_str, "cleared": True}
        except Exception as e:
            return {"status": "error", "error": str(e)}
