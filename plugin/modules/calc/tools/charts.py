# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Calc chart management tools: list, info, edit, delete."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.calc")


def _get_sheet(doc, sheet_name=None):
    """Resolve a sheet by name or active."""
    if sheet_name:
        sheets = doc.getSheets()
        if not sheets.hasByName(sheet_name):
            raise ValueError("Sheet not found: %s" % sheet_name)
        return sheets.getByName(sheet_name)
    return doc.getCurrentController().getActiveSheet()


class ListCharts(ToolBase):
    """List all charts on a Calc sheet."""

    name = "calc_chart_list"
    aliases = ["list_charts"]
    intent = "navigate"
    description = (
        "List all charts on a Calc sheet with name, position, and size."
    )
    parameters = {
        "type": "object",
        "properties": {
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
            sheet = _get_sheet(ctx.doc, kwargs.get("sheet_name"))
            charts = sheet.getCharts()
            result = []
            for name in charts.getElementNames():
                chart_obj = charts.getByName(name)
                entry = {"name": name}
                try:
                    chart_doc = _get_chart_doc(chart_obj)
                    if chart_doc:
                        try:
                            entry["has_legend"] = chart_doc.HasLegend
                        except Exception:
                            entry["has_legend"] = False
                        try:
                            entry["title"] = chart_doc.getTitle().String if chart_doc.HasMainTitle else ""
                        except Exception:
                            entry["title"] = ""
                except Exception:
                    pass
                result.append(entry)

            return {
                "status": "ok",
                "sheet": sheet.getName(),
                "charts": result,
                "count": len(result),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class GetChartInfo(ToolBase):
    """Get detailed info about a chart."""

    name = "calc_chart_info"
    aliases = ["get_chart_info"]
    intent = "navigate"
    description = (
        "Get detailed info about a Calc chart: type, title, "
        "data ranges, legend, and diagram properties."
    )
    parameters = {
        "type": "object",
        "properties": {
            "chart_name": {
                "type": "string",
                "description": "Chart name (from calc_chart_list).",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": ["chart_name"],
    }
    doc_types = ["calc"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        try:
            sheet = _get_sheet(ctx.doc, kwargs.get("sheet_name"))
            charts = sheet.getCharts()
            chart_name = kwargs["chart_name"]

            if not charts.hasByName(chart_name):
                available = list(charts.getElementNames())
                return {
                    "status": "error",
                    "message": "Chart '%s' not found." % chart_name,
                    "available": available,
                }

            chart_obj = charts.getByName(chart_name)
            info = {"name": chart_name, "sheet": sheet.getName()}

            # Data ranges
            try:
                ranges = chart_obj.getRanges()
                info["data_ranges"] = [_range_to_str(r) for r in ranges]
            except Exception:
                info["data_ranges"] = []

            # Chart document properties
            chart_doc = _get_chart_doc(chart_obj)
            if chart_doc:
                try:
                    info["title"] = chart_doc.getTitle().String if chart_doc.HasMainTitle else ""
                except Exception:
                    info["title"] = ""
                try:
                    info["subtitle"] = chart_doc.getSubTitle().String if chart_doc.HasSubTitle else ""
                except Exception:
                    info["subtitle"] = ""
                try:
                    info["has_legend"] = chart_doc.HasLegend
                except Exception:
                    info["has_legend"] = None
                try:
                    diagram = chart_doc.getDiagram()
                    info["diagram_type"] = diagram.getDiagramType()
                except Exception:
                    info["diagram_type"] = ""

            info["status"] = "ok"
            return info
        except Exception as e:
            return {"status": "error", "error": str(e)}


class EditChart(ToolBase):
    """Modify chart properties."""

    name = "calc_chart_edit"
    aliases = ["edit_chart"]
    intent = "edit"
    description = (
        "Edit a Calc chart: update title, subtitle, legend visibility."
    )
    parameters = {
        "type": "object",
        "properties": {
            "chart_name": {
                "type": "string",
                "description": "Chart name (from calc_chart_list).",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
            "title": {
                "type": "string",
                "description": "New chart title.",
            },
            "subtitle": {
                "type": "string",
                "description": "New chart subtitle.",
            },
            "has_legend": {
                "type": "boolean",
                "description": "Show or hide legend.",
            },
        },
        "required": ["chart_name"],
    }
    doc_types = ["calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        try:
            sheet = _get_sheet(ctx.doc, kwargs.get("sheet_name"))
            charts = sheet.getCharts()
            chart_name = kwargs["chart_name"]

            if not charts.hasByName(chart_name):
                return {"status": "error", "message": "Chart '%s' not found." % chart_name}

            chart_obj = charts.getByName(chart_name)
            chart_doc = _get_chart_doc(chart_obj)
            if chart_doc is None:
                return {"status": "error", "message": "Cannot access chart document."}

            updated = []

            title = kwargs.get("title")
            if title is not None:
                chart_doc.HasMainTitle = True
                title_obj = chart_doc.getTitle()
                title_obj.String = title
                updated.append("title")

            subtitle = kwargs.get("subtitle")
            if subtitle is not None:
                chart_doc.HasSubTitle = True
                sub_obj = chart_doc.getSubTitle()
                sub_obj.String = subtitle
                updated.append("subtitle")

            has_legend = kwargs.get("has_legend")
            if has_legend is not None:
                chart_doc.HasLegend = has_legend
                updated.append("has_legend")

            return {"status": "ok", "chart_name": chart_name, "updated": updated}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class DeleteChart(ToolBase):
    """Delete a chart from a Calc sheet."""

    name = "calc_chart_delete"
    aliases = ["delete_chart"]
    intent = "edit"
    description = "Delete a chart from a Calc sheet by name."
    parameters = {
        "type": "object",
        "properties": {
            "chart_name": {
                "type": "string",
                "description": "Chart name (from calc_chart_list).",
            },
            "sheet_name": {
                "type": "string",
                "description": "Sheet name (active sheet if omitted).",
            },
        },
        "required": ["chart_name"],
    }
    doc_types = ["calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        try:
            sheet = _get_sheet(ctx.doc, kwargs.get("sheet_name"))
            charts = sheet.getCharts()
            chart_name = kwargs["chart_name"]

            if not charts.hasByName(chart_name):
                return {"status": "error", "message": "Chart '%s' not found." % chart_name}

            charts.removeByName(chart_name)
            return {"status": "ok", "deleted": chart_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_chart_doc(chart_obj):
    """Get the chart document from a chart object.

    In Python-UNO, queryInterface isn't needed — access the embedded
    object's model directly.
    """
    try:
        embedded = chart_obj.getEmbeddedObject()
        # The embedded object IS the chart document in Python-UNO
        return embedded
    except Exception:
        return None


def _range_to_str(range_addr):
    """Convert a CellRangeAddress to a string."""
    try:
        from plugin.modules.calc.address_utils import index_to_column
        return "%s%d:%s%d" % (
            index_to_column(range_addr.StartColumn), range_addr.StartRow + 1,
            index_to_column(range_addr.EndColumn), range_addr.EndRow + 1,
        )
    except Exception:
        return str(range_addr)
