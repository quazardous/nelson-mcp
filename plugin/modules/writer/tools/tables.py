# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer table tools."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")


class ListTables(ToolBase):
    """List all text tables in the document."""

    name = "table_list"
    aliases = ["list_tables"]
    intent = "edit"
    description = (
        "List all text tables in the document with their names "
        "and dimensions (rows x cols)."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        if not hasattr(doc, "getTextTables"):
            return {"status": "error", "message": "Document does not support text tables."}

        tables_sup = doc.getTextTables()
        tables = []
        for name in tables_sup.getElementNames():
            table = tables_sup.getByName(name)
            tables.append({
                "name": name,
                "rows": table.getRows().getCount(),
                "cols": table.getColumns().getCount(),
            })
        return {"status": "ok", "tables": tables, "count": len(tables)}


class ReadTable(ToolBase):
    """Read all cell contents from a named Writer table."""

    name = "table_read"
    aliases = ["read_table"]
    intent = "edit"
    description = "Read all cell contents from a named Writer table as a 2D array."
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name from table_list.",
            },
        },
        "required": ["table_name"],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        if not table_name:
            return {"status": "error", "message": "table_name is required."}

        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            available = list(tables_sup.getElementNames())
            return {
                "status": "error",
                "message": "Table '%s' not found." % table_name,
                "available": available,
            }

        table = tables_sup.getByName(table_name)
        rows = table.getRows().getCount()
        cols = table.getColumns().getCount()
        data = []
        for r in range(rows):
            row_data = []
            for c in range(cols):
                col_letter = _col_letter(c)
                cell_ref = "%s%d" % (col_letter, r + 1)
                try:
                    row_data.append(table.getCellByName(cell_ref).getString())
                except Exception:
                    row_data.append("")
            data.append(row_data)

        return {
            "status": "ok",
            "table_name": table_name,
            "rows": rows,
            "cols": cols,
            "data": data,
        }


class WriteTableCell(ToolBase):
    """Write a value to a specific cell in a Writer table."""

    name = "table_write_cell"
    aliases = ["write_table_cell"]
    intent = "edit"
    description = (
        "Write a value to a specific cell in a named Writer table. "
        "Use Excel-style cell references (e.g. 'A1', 'B2'). "
        "Numeric strings are stored as numbers automatically."
    )
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name from table_list.",
            },
            "cell": {
                "type": "string",
                "description": "Cell reference, e.g. 'A1', 'B3'.",
            },
            "value": {
                "type": "string",
                "description": "The value to write.",
            },
        },
        "required": ["table_name", "cell", "value"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        cell_ref = kwargs.get("cell", "")
        value = kwargs.get("value", "")

        if not table_name or not cell_ref:
            return {"status": "error", "message": "table_name and cell are required."}

        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        cell_obj = table.getCellByName(cell_ref)
        if cell_obj is None:
            return {
                "status": "error",
                "message": "Cell '%s' not found in table '%s'." % (cell_ref, table_name),
            }

        try:
            cell_obj.setValue(float(value))
        except (ValueError, TypeError):
            cell_obj.setString(str(value))

        return {
            "status": "ok",
            "table": table_name,
            "cell": cell_ref,
            "value": value,
        }


class CreateTable(ToolBase):
    """Create a new table at a paragraph position."""

    name = "table_create"
    aliases = ["create_table"]
    intent = "edit"
    description = (
        "Create a new table at a paragraph position. "
        "The table is inserted relative to the target paragraph. "
        "Provide either a locator string or a paragraph_index."
    )
    parameters = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "integer",
                "description": "Number of rows.",
            },
            "cols": {
                "type": "integer",
                "description": "Number of columns.",
            },
            "paragraph_index": {
                "type": "integer",
                "description": "Paragraph index for insertion point.",
            },
            "locator": {
                "type": "string",
                "description": (
                    "Unified locator for insertion point "
                    "(e.g. 'bookmark:NAME', 'heading_text:Title')."
                ),
            },
            "position": {
                "type": "string",
                "enum": ["before", "after"],
                "description": (
                    "Insert before or after the target paragraph "
                    "(default: after)."
                ),
            },
        },
        "required": ["rows", "cols"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        rows = kwargs.get("rows")
        cols = kwargs.get("cols")
        if not rows or not cols:
            return {"status": "error", "message": "rows and cols are required."}
        if rows < 1 or cols < 1:
            return {"status": "error", "message": "rows and cols must be >= 1."}

        paragraph_index = kwargs.get("paragraph_index")
        locator = kwargs.get("locator")
        position = kwargs.get("position", "after")

        doc = ctx.doc
        doc_svc = ctx.services.document

        try:
            # Resolve locator to paragraph index
            if locator is not None and paragraph_index is None:
                resolved = doc_svc.resolve_locator(doc, locator)
                paragraph_index = resolved.get("para_index")

            if paragraph_index is None:
                return {
                    "status": "error",
                    "message": "Provide locator or paragraph_index.",
                }

            # Find the target paragraph element
            target, _ = doc_svc.find_paragraph_element(doc, paragraph_index)
            if target is None:
                return {
                    "status": "error",
                    "message": "Paragraph %d not found." % paragraph_index,
                }

            # Create and insert the table
            table = doc.createInstance("com.sun.star.text.TextTable")
            table.initialize(rows, cols)

            doc_text = doc.getText()
            if position == "before":
                cursor = doc_text.createTextCursorByRange(target.getStart())
            else:
                cursor = doc_text.createTextCursorByRange(target.getEnd())

            doc_text.insertTextContent(cursor, table, False)

            table_name = table.getName()

            return {
                "status": "ok",
                "table_name": table_name,
                "rows": rows,
                "cols": cols,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ------------------------------------------------------------------
# DeleteTable
# ------------------------------------------------------------------

class DeleteTable(ToolBase):
    """Delete a table from the document."""

    name = "table_delete"
    aliases = ["delete_table"]
    intent = "edit"
    description = "Delete a named table from the Writer document."
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name from table_list.",
            },
        },
        "required": ["table_name"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        try:
            anchor = table.getAnchor()
            text = anchor.getText()
            text.removeTextContent(table)
            return {"status": "ok", "deleted": table_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ------------------------------------------------------------------
# SetTableProperties
# ------------------------------------------------------------------

class SetTableProperties(ToolBase):
    """Set table layout properties: width, alignment, equal columns."""

    name = "table_set"
    aliases = ["set_table_properties"]
    intent = "edit"
    description = (
        "Set layout properties on a Writer table: width, alignment, "
        "equal-width columns, repeat header row, background color. "
        "Use equal_columns=true to make all columns the same width."
    )
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name from table_list.",
            },
            "width_mm": {
                "type": "number",
                "description": "Table width in millimetres.",
            },
            "equal_columns": {
                "type": "boolean",
                "description": "Set all columns to equal width (default: false).",
            },
            "column_widths": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Relative column widths (e.g. [1, 2, 1] = 25%/50%/25%). "
                    "Number of values must match number of columns."
                ),
            },
            "alignment": {
                "type": "string",
                "enum": ["left", "center", "right", "full"],
                "description": "Horizontal alignment (default: full = stretch to margins).",
            },
            "repeat_header": {
                "type": "boolean",
                "description": "Repeat first row as header on each page.",
            },
            "header_rows": {
                "type": "integer",
                "description": "Number of header rows to repeat (default: 1).",
            },
            "bg_color": {
                "type": "string",
                "description": "Background color as hex (#RRGGBB) or name.",
            },
        },
        "required": ["table_name"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        updated = []

        # Width
        width_mm = kwargs.get("width_mm")
        if width_mm is not None:
            table.setPropertyValue("Width", int(width_mm * 100))
            updated.append("width")

        # Alignment
        alignment = kwargs.get("alignment")
        if alignment is not None:
            # HoriOrientation: 0=NONE, 1=RIGHT, 2=CENTER, 3=LEFT, 4=FULL
            align_map = {"left": 3, "center": 2, "right": 1, "full": 4, "none": 0}
            if alignment in align_map:
                table.setPropertyValue("HoriOrient", align_map[alignment])
                updated.append("alignment")

        # Column widths (equal or custom ratios)
        equal = kwargs.get("equal_columns", False)
        custom_widths = kwargs.get("column_widths")

        if equal or custom_widths:
            try:
                cols = table.getColumns().getCount()
                rel_sum = table.getPropertyValue("TableColumnRelativeSum")
                seps = list(table.getPropertyValue("TableColumnSeparators"))

                if cols < 2:
                    pass  # single column, nothing to adjust
                elif equal:
                    # Equal-width: place separators at even intervals
                    for i in range(len(seps)):
                        seps[i].Position = int(rel_sum * (i + 1) / cols)
                    table.setPropertyValue("TableColumnSeparators", tuple(seps))
                    updated.append("equal_columns")
                elif custom_widths and len(custom_widths) == cols:
                    # Custom ratios
                    total = sum(custom_widths)
                    cumulative = 0
                    for i in range(len(seps)):
                        cumulative += custom_widths[i]
                        seps[i].Position = int(rel_sum * cumulative / total)
                    table.setPropertyValue("TableColumnSeparators", tuple(seps))
                    updated.append("column_widths")
                elif custom_widths:
                    return {
                        "status": "error",
                        "message": "column_widths length (%d) != column count (%d)" % (
                            len(custom_widths), cols),
                    }
            except Exception as e:
                log.debug("table_set: column adjust failed: %s", e)

        # Repeat header
        repeat = kwargs.get("repeat_header")
        if repeat is not None:
            table.setPropertyValue("RepeatHeadline", bool(repeat))
            updated.append("repeat_header")

        header_rows = kwargs.get("header_rows")
        if header_rows is not None:
            try:
                table.setPropertyValue("HeaderRowCount", int(header_rows))
                updated.append("header_rows")
            except Exception:
                pass

        # Background color
        bg_color = kwargs.get("bg_color")
        if bg_color is not None:
            color_val = _parse_color(bg_color)
            if color_val is not None:
                table.setPropertyValue("BackTransparent", False)
                table.setPropertyValue("BackColor", color_val)
                updated.append("bg_color")

        return {"status": "ok", "table_name": table_name, "updated": updated}


# ------------------------------------------------------------------
# AddTableRows / AddTableColumns
# ------------------------------------------------------------------

class AddTableRows(ToolBase):
    """Add rows to a Writer table."""

    name = "table_add_rows"
    aliases = ["add_table_rows"]
    intent = "edit"
    description = "Insert one or more rows into a Writer table at a given position."
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name.",
            },
            "count": {
                "type": "integer",
                "description": "Number of rows to add (default: 1).",
            },
            "at_index": {
                "type": "integer",
                "description": "Row index to insert before (appends at end if omitted).",
            },
        },
        "required": ["table_name"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        rows = table.getRows()
        count = kwargs.get("count", 1)
        at_index = kwargs.get("at_index")
        if at_index is None:
            at_index = rows.getCount()

        try:
            rows.insertByIndex(at_index, count)
            return {
                "status": "ok",
                "table_name": table_name,
                "rows_added": count,
                "at_index": at_index,
                "total_rows": rows.getCount(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class AddTableColumns(ToolBase):
    """Add columns to a Writer table."""

    name = "table_add_columns"
    aliases = ["add_table_columns"]
    intent = "edit"
    description = "Insert one or more columns into a Writer table at a given position."
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name.",
            },
            "count": {
                "type": "integer",
                "description": "Number of columns to add (default: 1).",
            },
            "at_index": {
                "type": "integer",
                "description": "Column index to insert before (appends at end if omitted).",
            },
        },
        "required": ["table_name"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        cols = table.getColumns()
        count = kwargs.get("count", 1)
        at_index = kwargs.get("at_index")
        if at_index is None:
            at_index = cols.getCount()

        try:
            cols.insertByIndex(at_index, count)
            return {
                "status": "ok",
                "table_name": table_name,
                "columns_added": count,
                "at_index": at_index,
                "total_columns": cols.getCount(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ------------------------------------------------------------------
# DeleteTableRows / DeleteTableColumns
# ------------------------------------------------------------------

class DeleteTableRows(ToolBase):
    """Delete rows from a Writer table."""

    name = "table_delete_rows"
    aliases = ["delete_table_rows"]
    intent = "edit"
    description = "Delete one or more rows from a Writer table."
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name.",
            },
            "at_index": {
                "type": "integer",
                "description": "First row index to delete.",
            },
            "count": {
                "type": "integer",
                "description": "Number of rows to delete (default: 1).",
            },
        },
        "required": ["table_name", "at_index"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        rows = table.getRows()
        at_index = kwargs["at_index"]
        count = kwargs.get("count", 1)

        try:
            rows.removeByIndex(at_index, count)
            return {
                "status": "ok",
                "table_name": table_name,
                "rows_deleted": count,
                "total_rows": rows.getCount(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class DeleteTableColumns(ToolBase):
    """Delete columns from a Writer table."""

    name = "table_delete_columns"
    aliases = ["delete_table_columns"]
    intent = "edit"
    description = "Delete one or more columns from a Writer table."
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name.",
            },
            "at_index": {
                "type": "integer",
                "description": "First column index to delete.",
            },
            "count": {
                "type": "integer",
                "description": "Number of columns to delete (default: 1).",
            },
        },
        "required": ["table_name", "at_index"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        cols = table.getColumns()
        at_index = kwargs["at_index"]
        count = kwargs.get("count", 1)

        try:
            cols.removeByIndex(at_index, count)
            return {
                "status": "ok",
                "table_name": table_name,
                "columns_deleted": count,
                "total_columns": cols.getCount(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ------------------------------------------------------------------
# WriteTableRow (batch write)
# ------------------------------------------------------------------

class WriteTableRow(ToolBase):
    """Write a full row of values to a Writer table."""

    name = "table_write_row"
    aliases = ["write_table_row"]
    intent = "edit"
    description = (
        "Write a full row of values to a Writer table in one call. "
        "More efficient than calling table_write_cell for each cell."
    )
    parameters = {
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "The table name.",
            },
            "row": {
                "type": "integer",
                "description": "0-based row index.",
            },
            "values": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Values for each column (left to right).",
            },
        },
        "required": ["table_name", "row", "values"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        table_name = kwargs.get("table_name", "")
        row_idx = kwargs.get("row", 0)
        values = kwargs.get("values", [])

        doc = ctx.doc
        tables_sup = doc.getTextTables()
        if not tables_sup.hasByName(table_name):
            return {"status": "error", "message": "Table '%s' not found." % table_name}

        table = tables_sup.getByName(table_name)
        cols = table.getColumns().getCount()

        written = 0
        for c in range(min(len(values), cols)):
            col_letter = _col_letter(c)
            cell_ref = "%s%d" % (col_letter, row_idx + 1)
            cell_obj = table.getCellByName(cell_ref)
            if cell_obj is None:
                continue
            val = values[c]
            try:
                cell_obj.setValue(float(val))
            except (ValueError, TypeError):
                cell_obj.setString(str(val))
            written += 1

        return {
            "status": "ok",
            "table_name": table_name,
            "row": row_idx,
            "cells_written": written,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _col_letter(c):
    """Convert 0-based column index to Excel-style letter(s)."""
    if c < 26:
        return chr(ord("A") + c)
    return "A" + chr(ord("A") + c - 26)


def _parse_color(color_str):
    """Parse a color string (hex or name) to integer."""
    if not color_str:
        return None
    color_str = color_str.strip().lower()
    names = {
        "red": 0xFF0000, "green": 0x00FF00, "blue": 0x0000FF,
        "yellow": 0xFFFF00, "white": 0xFFFFFF, "black": 0x000000,
        "orange": 0xFF8C00, "gray": 0x808080,
    }
    if color_str in names:
        return names[color_str]
    if color_str.startswith("#"):
        try:
            return int(color_str[1:], 16)
        except ValueError:
            return None
    return None
