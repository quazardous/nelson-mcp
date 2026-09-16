# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cell manipulator — writing data and formatting LibreOffice Calc cells.

Ported from core/calc_manipulator.py for the plugin framework.
UNO imports are deferred to method bodies.
"""

import csv
import io
import json
import logging
import re

from plugin.modules.calc.address_utils import parse_address

logger = logging.getLogger("nelson.calc")


# ── Helper ─────────────────────────────────────────────────────────────


def _parse_formula_or_values_string(s: str):
    """Parse *formula_or_values* when it arrives as a JSON string or as a
    raw semicolon-separated string.

    The AI often sends formula_or_values as a JSON-encoded string (e.g.
    ``'["Name"; "Category"; "Value"]'``) or as a raw string like
    ``'Name;Category;Value'``.  Without this, calc_write_formula would
    write the whole string as one value per cell.  We normalise
    LibreOffice-style semicolon separators and return a flat list.

    Returns:
        A flat list of values, or *None* if *s* should be treated as a
        single literal value.
    """
    if not isinstance(s, str):
        return None

    s_strip = s.strip()
    if not s_strip:
        return None

    # Case 1: JSON array e.g. ["a"; "b"] or ["a", "b"]
    if s_strip.startswith("["):
        try:
            # Replace semicolons NOT inside double quotes with commas.
            normalized_list = []
            in_quotes = False
            escaped = False
            for char in s_strip:
                if char == '"' and not escaped:
                    in_quotes = not in_quotes
                if char == ';' and not in_quotes:
                    normalized_list.append(',')
                else:
                    normalized_list.append(char)
                if char == '\\' and not escaped:
                    escaped = True
                else:
                    escaped = False

            normalized = "".join(normalized_list)
            data = json.loads(normalized)
            if isinstance(data, list):
                flat = []
                for item in data:
                    if isinstance(item, list):
                        flat.extend(item)
                    else:
                        flat.append(item)
                return flat
        except (json.JSONDecodeError, TypeError):
            pass

    # Case 2: Raw semicolon-separated string e.g. "Name;Age;Country"
    # Only if it is not a formula (starting with =) and not a single value.
    if ";" in s and not s_strip.startswith("="):
        try:
            reader = csv.reader(
                io.StringIO(s), delimiter=";", skipinitialspace=True,
            )
            rows = list(reader)
            if rows:
                return [val.strip() for val in rows[0]]
        except Exception:
            pass

    return None


class ArrayFormulaError(ValueError):
    """An array formula that cannot be written as asked (#2631)."""

    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details


# XSheetOperation.clearContents flags: VALUE | DATETIME | STRING | FORMULA
_CLEAR_CONTENT = 1 | 2 | 4 | 16


class DateWriter:
    """Writes ISO date strings as real dates in one document (#2632).

    Looks up the document's NullDate and the date number formats once, and
    formats a cell only while it still has the standard number format, so a
    format the agent already set is never overwritten.
    """

    def __init__(self, doc):
        self.doc = doc
        self.count = 0
        self._null = None
        self._keys = {}
        self._standard = None

    def _null_date(self):
        if self._null is None:
            try:
                d = self.doc.getPropertyValue("NullDate")
                self._null = (d.Year, d.Month, d.Day)
            except Exception:
                self._null = (1899, 12, 30)
        return self._null

    def _locale(self):
        import uno
        return uno.createUnoStruct("com.sun.star.lang.Locale")

    def _format_key(self, pattern):
        if pattern not in self._keys:
            formats = self.doc.getNumberFormats()
            locale = self._locale()
            key = formats.queryKey(pattern, locale, False)
            if key == -1:
                key = formats.addNew(pattern, locale)
            self._keys[pattern] = key
        return self._keys[pattern]

    def _is_standard(self, cell):
        try:
            key = cell.getPropertyValue("NumberFormat")
        except Exception:
            return False
        if self._standard is None:
            try:
                self._standard = self.doc.getNumberFormats().getStandardIndex(
                    self._locale())
            except Exception:
                self._standard = 0
        return key in (0, self._standard)

    def write(self, cell, text):
        """Write *text* as a date if it is an ISO date; return True if so."""
        from plugin.modules.calc.iso_dates import (
            DATE_FORMAT, DATETIME_FORMAT, parse_iso, serial)
        parsed = parse_iso(text)
        if parsed is None:
            return False
        value, has_time = parsed
        standard = self._is_standard(cell)
        cell.setValue(serial(value, self._null_date()))
        if standard:
            cell.setPropertyValue("NumberFormat", self._format_key(
                DATETIME_FORMAT if has_time else DATE_FORMAT))
        self.count += 1
        return True


def write_text_or_date(cell, text, dates):
    """setString, unless *text* is an ISO date (-> date) or starts with an
    apostrophe (-> the rest, kept as text, as Calc does)."""
    from plugin.modules.calc.iso_dates import literal_text
    literal = literal_text(text)
    if literal is not None:
        cell.setString(literal)
    elif not dates.write(cell, text):
        cell.setString(text)


# ── Manipulator ────────────────────────────────────────────────────────


class CellManipulator:
    """Manages data writing and style application to cells."""

    def __init__(self, bridge):
        """
        Args:
            bridge: CalcBridge instance.
        """
        self.bridge = bridge

    # ── Internal helpers ───────────────────────────────────────────────

    def _get_cell(self, address: str):
        """Return the cell object for *address*, honouring a sheet prefix."""
        sheet, address = self.bridge.resolve(address)
        col, row = parse_address(address)
        return self.bridge.get_cell(sheet, col, row)

    def _apply_style_properties(
        self, obj, bold, italic, bg_color, font_color, font_size,
        h_align, v_align, wrap_text, border_color,
    ):
        """Apply common style properties to a cell or range object."""
        if bold is not None:
            from com.sun.star.awt.FontWeight import BOLD, NORMAL
            obj.setPropertyValue("CharWeight", BOLD if bold else NORMAL)

        if italic is not None:
            from com.sun.star.awt.FontSlant import ITALIC, NONE
            obj.setPropertyValue("CharPosture", ITALIC if italic else NONE)

        if bg_color is not None:
            obj.setPropertyValue("CellBackColor", bg_color)

        if font_color is not None:
            obj.setPropertyValue("CharColor", font_color)

        if font_size is not None:
            obj.setPropertyValue("CharHeight", font_size)

        if h_align is not None:
            from com.sun.star.table.CellHoriJustify import (
                LEFT, CENTER, RIGHT, BLOCK, STANDARD,
            )
            align_map = {
                "left": LEFT, "center": CENTER, "right": RIGHT,
                "justify": BLOCK, "standard": STANDARD,
            }
            if h_align.lower() in align_map:
                obj.setPropertyValue("HoriJustify", align_map[h_align.lower()])

        if v_align is not None:
            from com.sun.star.table.CellVertJustify import (
                TOP, CENTER, BOTTOM, STANDARD,
            )
            align_map = {
                "top": TOP, "center": CENTER, "bottom": BOTTOM,
                "standard": STANDARD,
            }
            if v_align.lower() in align_map:
                obj.setPropertyValue("VertJustify", align_map[v_align.lower()])

        if wrap_text is not None:
            obj.setPropertyValue("IsTextWrapped", wrap_text)

        if border_color is not None:
            self._apply_borders(obj, border_color)

    def _apply_borders(self, obj, color: int):
        """Apply borders to a cell or range object."""
        from com.sun.star.table import BorderLine

        line = BorderLine()
        line.Color = color
        line.OuterLineWidth = 50  # 1/100 mm; 50 == 0.5 mm

        obj.setPropertyValue("TopBorder", line)
        obj.setPropertyValue("BottomBorder", line)
        obj.setPropertyValue("LeftBorder", line)
        obj.setPropertyValue("RightBorder", line)

    # ── Write operations ───────────────────────────────────────────────

    def write_formula(self, address: str, formula: str) -> str:
        """Write formula, text, or number to a cell.

        If the value starts with ``=`` it is written as a formula.  If it
        can be converted to a number it is written as a numeric value.
        Otherwise it is written as text.

        Args:
            address: Cell address (e.g. "A1").
            formula: Content to write (e.g. "=SUM(A1:A10)", "Header", "42").

        Returns:
            Description of the written value.
        """
        try:
            cell = self._get_cell(address)

            if formula.startswith("="):
                cell.setFormula(formula)
                logger.info("Cell %s <- formula '%s' written.", address.upper(), formula)
                return f"Formula written to cell {address}: {formula}"
            else:
                try:
                    num = float(formula)
                    cell.setValue(num)
                    logger.info("Cell %s <- number %s written.", address.upper(), formula)
                    return f"Number written to cell {address}: {formula}"
                except ValueError:
                    cell.setString(formula)
                    logger.info("Cell %s <- text '%s' written.", address.upper(), formula)
                    return f"Text written to cell {address}: {formula}"
        except Exception as e:
            logger.error("Formula writing error (%s): %s", address, str(e))
            raise

    # ── Style operations ───────────────────────────────────────────────

    def set_cell_style(
        self,
        address_or_range: str,
        bold: bool = None,
        italic: bool = None,
        bg_color: int = None,
        font_color: int = None,
        font_size: float = None,
        h_align: str = None,
        v_align: str = None,
        wrap_text: bool = None,
        border_color: int = None,
        number_format: str = None,
    ):
        """Apply style to a cell or range.

        Delegates to range-specific helpers when the target contains ``:``.

        Args:
            address_or_range: Cell address or range (e.g. "A1" or "A1:D10").
            bold: Bold flag.
            italic: Italic flag.
            bg_color: Background colour (RGB int).
            font_color: Font colour (RGB int).
            font_size: Font size (points).
            h_align: Horizontal alignment ("left", "center", "right", "justify").
            v_align: Vertical alignment ("top", "center", "bottom").
            wrap_text: Wrap text flag.
            border_color: Border colour (RGB int).
            number_format: Number format string (e.g. "#,##0.00").
        """
        try:
            if ":" in address_or_range:
                self._set_range_style(
                    address_or_range,
                    bold=bold, italic=italic, bg_color=bg_color,
                    font_color=font_color, font_size=font_size,
                    h_align=h_align, v_align=v_align,
                    wrap_text=wrap_text, border_color=border_color,
                )
                if number_format:
                    self._set_range_number_format(address_or_range, number_format)
                logger.info("Range %s style updated.", address_or_range.upper())
            else:
                cell = self._get_cell(address_or_range)
                self._apply_style_properties(
                    cell, bold, italic, bg_color, font_color, font_size,
                    h_align, v_align, wrap_text, border_color,
                )
                if number_format:
                    self._set_number_format(address_or_range, number_format)
                logger.info("Cell %s style updated.", address_or_range.upper())
        except Exception as e:
            logger.error("Style application error (%s): %s", address_or_range, str(e))
            raise

    def _set_range_style(
        self, range_str, bold=None, italic=None, bg_color=None,
        font_color=None, font_size=None, h_align=None, v_align=None,
        wrap_text=None, border_color=None,
    ):
        sheet = self.bridge.get_active_sheet()
        cell_range = self.bridge.get_cell_range(sheet, range_str)
        self._apply_style_properties(
            cell_range, bold, italic, bg_color, font_color, font_size,
            h_align, v_align, wrap_text, border_color,
        )

    def _set_range_number_format(self, range_str: str, format_str: str):
        sheet, range_str = self.bridge.resolve(range_str)
        start, end = self.bridge.parse_range_string(range_str)
        doc = self.bridge.get_active_document()
        formats = doc.getNumberFormats()
        locale = doc.getPropertyValue("CharLocale")
        format_id = formats.queryKey(format_str, locale, False)
        if format_id == -1:
            format_id = formats.addNew(format_str, locale)
        for row in range(start[1], end[1] + 1):
            for col in range(start[0], end[0] + 1):
                cell = sheet.getCellByPosition(col, row)
                cell.setPropertyValue("NumberFormat", format_id)

    def _set_number_format(self, address: str, format_str: str):
        cell = self._get_cell(address)
        doc = self.bridge.get_active_document()
        formats = doc.getNumberFormats()
        locale = doc.getPropertyValue("CharLocale")
        format_id = formats.queryKey(format_str, locale, False)
        if format_id == -1:
            format_id = formats.addNew(format_str, locale)
        cell.setPropertyValue("NumberFormat", format_id)

    # ── Range operations ───────────────────────────────────────────────

    def clear_range(self, range_str: str):
        """Clear all content in a cell range.

        Args:
            range_str: Cell range (e.g. "A1:D10").
        """
        try:
            sheet = self.bridge.get_active_sheet()
            cell_range = self.bridge.get_cell_range(sheet, range_str)
            # CellFlags: VALUE=1, DATETIME=2, STRING=4, FORMULA=16 -> 23
            cell_range.clearContents(23)
            logger.info("Range %s cleared.", range_str.upper())
        except Exception as e:
            logger.error("Range clear error (%s): %s", range_str, str(e))
            raise

    def merge_cells(self, range_str: str, center: bool = True):
        """Merge a cell range.

        Args:
            range_str: Cell range to merge (e.g. "A1:D1").
            center: Centre content after merging.
        """
        try:
            sheet = self.bridge.get_active_sheet()
            cell_range = self.bridge.get_cell_range(sheet, range_str)
            cell_range.merge(True)
            logger.info("Range %s merged.", range_str.upper())

            if center:
                from com.sun.star.table.CellHoriJustify import CENTER
                from com.sun.star.table.CellVertJustify import CENTER as V_CENTER
                cell_range.setPropertyValue("HoriJustify", CENTER)
                cell_range.setPropertyValue("VertJustify", V_CENTER)
        except Exception as e:
            logger.error("Cell merge error (%s): %s", range_str, str(e))
            raise

    def sort_range(
        self,
        range_str: str,
        sort_column: int = 0,
        ascending: bool = True,
        has_header: bool = True,
    ):
        """Sort a range.

        Args:
            range_str: Range to sort (e.g. "A1:D10").
            sort_column: 0-based column index within the range.
            ascending: True for ascending, False for descending.
            has_header: Whether the first row is a header.

        Returns:
            Description string.
        """
        try:
            sheet = self.bridge.get_active_sheet()
            cell_range = self.bridge.get_cell_range(sheet, range_str)

            import uno  # noqa: F401 – needed in UNO context
            from com.sun.star.table import TableSortField

            sort_desc = list(cell_range.createSortDescriptor())

            sort_field = TableSortField()
            sort_field.Field = sort_column
            sort_field.IsAscending = ascending
            sort_field.IsCaseSensitive = False

            for p in sort_desc:
                if p.Name == "SortFields":
                    p.Value = (sort_field,)
                elif p.Name == "ContainsHeader":
                    p.Value = has_header

            cell_range.sort(tuple(sort_desc))

            direction = "ascending" if ascending else "descending"
            logger.info(
                "Range %s sorted %s by column %d.",
                range_str.upper(), direction, sort_column,
            )
            return f"Range {range_str} sorted {direction} by column {sort_column}."
        except Exception as e:
            logger.error("Sort error (%s): %s", range_str, str(e))
            raise

    def write_formula_range(self, range_str: str, formula_or_values,
                            array=None):
        """Write formula(s) or value(s) to a cell range.

        Args:
            range_str: Cell range (e.g. "A1:A10", "B2:D2").
            formula_or_values: Single formula/value for all cells, or a
                list/array of values for each cell.

        Returns:
            Summary of the operation.
        """
        try:
            sheet, range_str = self.bridge.resolve(range_str)
            start, end = self.bridge.parse_range_string(range_str)

            num_rows = end[1] - start[1] + 1
            num_cols = end[0] - start[0] + 1
            total_cells = num_rows * num_cols

            # Normalise string-as-array from AI callers.
            if isinstance(formula_or_values, str):
                parsed = _parse_formula_or_values_string(formula_or_values)
                if parsed is not None:
                    formula_or_values = parsed

            if isinstance(formula_or_values, str):
                from plugin.modules.calc.array_formula import returns_array
                if returns_array(formula_or_values, array):
                    return self.write_array_formula(
                        range_str if self.bridge.split_prefix(range_str)[0]
                        else "'%s'.%s" % (sheet.getName(), range_str),
                        formula_or_values)

            if isinstance(formula_or_values, (list, tuple)):
                if len(formula_or_values) != total_cells:
                    raise ValueError(
                        f"Array length {len(formula_or_values)} doesn't match "
                        f"range size {total_cells}"
                    )
                values = formula_or_values
            else:
                values = [formula_or_values] * total_cells

            dates = DateWriter(self.bridge.doc)
            cell_idx = 0
            for row in range(start[1], end[1] + 1):
                for col in range(start[0], end[0] + 1):
                    cell = sheet.getCellByPosition(col, row)
                    value = values[cell_idx]

                    if isinstance(value, str):
                        if value.startswith("="):
                            cell.setFormula(value)
                        else:
                            try:
                                num = float(value)
                                cell.setValue(num)
                            except ValueError:
                                write_text_or_date(cell, value, dates)
                    elif isinstance(value, (int, float)):
                        cell.setValue(value)
                    else:
                        cell.setString(str(value))

                    cell_idx += 1

            logger.info(
                "Range %s filled with %d values.", range_str.upper(), len(values),
            )
            message = f"Range {range_str} filled with {len(values)} values."
            if dates.count:
                message += " %d written as dates." % dates.count
            return message
        except ArrayFormulaError as e:
            # The caller's formula or target, not a fault: keep the log clean.
            logger.debug("Array formula refused (%s): %s", range_str, e)
            raise
        except Exception as e:
            logger.error("Range formula write error (%s): %s", range_str, str(e))
            raise

    # ── Array formulas (#2631) ─────────────────────────────────────────

    def _measure_array(self, sheet, formula):
        """(rows, columns) of *formula*'s result, measured by LibreOffice.

        =ROWS(expr) and =COLUMNS(expr) are entered as array formulas in two
        scratch cells to the right of the sheet's used area, read, then
        cleared. Raises ArrayFormulaError when the formula itself fails.
        """
        cursor = sheet.createCursor()
        cursor.gotoEndOfUsedArea(False)
        used = cursor.getRangeAddress()
        col = min(used.EndColumn + 2, 16383)
        expr = formula[1:] if formula.startswith("=") else formula
        sizes = []
        try:
            for row, fn in ((0, "ROWS"), (1, "COLUMNS")):
                probe = sheet.getCellRangeByPosition(col, row, col, row)
                probe.setArrayFormula("=%s(%s)" % (fn, expr))
                cell = sheet.getCellByPosition(col, row)
                if cell.getError():
                    shown = cell.getString()
                    raise ArrayFormulaError(
                        "formula_error",
                        "The formula returns an error (%s, code %d) — e.g. "
                        "FILTER with no matching row gives #CALC!."
                        % (shown or "error", cell.getError()),
                        error=shown or None, error_code=cell.getError())
                sizes.append(int(round(cell.getValue())))
        finally:
            for row in (0, 1):
                try:
                    probe = sheet.getCellRangeByPosition(col, row, col, row)
                    probe.setArrayFormula("")
                    probe.clearContents(_CLEAR_CONTENT)
                except Exception:
                    pass
        return sizes[0], sizes[1]

    @staticmethod
    def _array_block(sheet, col, row):
        """Range address of the array formula covering (col, row), or None."""
        try:
            cursor = sheet.createCursorByRange(
                sheet.getCellRangeByPosition(col, row, col, row))
            cursor.collapseToCurrentArray()
            a = cursor.getRangeAddress()
            if not sheet.getCellRangeByPosition(
                    a.StartColumn, a.StartRow, a.EndColumn,
                    a.EndRow).getArrayFormula():
                return None
            return a
        except Exception:
            return None

    def write_array_formula(self, range_str: str, formula: str):
        """Enter *formula* as an array formula so its whole result shows.

        From a single cell, the result range is sized from the result and
        must be empty (an array formula already anchored there is replaced).
        On an explicit range, that range is used as given, and the answer
        says if the result is larger (rows cut) or smaller (#N/A padding).
        """
        from plugin.modules.calc.array_formula import MAX_CELLS, result_range
        from plugin.modules.calc.address_utils import index_to_column

        sheet, address = self.bridge.resolve(range_str)
        (c1, r1), (c2, r2) = self.bridge.parse_range_string(address)
        explicit = (c1, r1) != (c2, r2)
        rows, cols = self._measure_array(sheet, formula)

        def name(a, b, c, d):
            return "%s%d:%s%d" % (index_to_column(a), b + 1,
                                  index_to_column(c), d + 1)

        notes = []
        if explicit:
            target = (c1, r1, c2, r2)
            height, width = r2 - r1 + 1, c2 - c1 + 1
            if rows > height or cols > width:
                notes.append("The result is %d x %d but the range is %d x %d: "
                             "the rest is cut." % (rows, cols, height, width))
            elif rows < height or cols < width:
                notes.append("The result is %d x %d, smaller than the range: "
                             "the extra cells show #N/A." % (rows, cols))
        else:
            if rows * cols > MAX_CELLS:
                raise ArrayFormulaError(
                    "result_too_large",
                    "The result is %d x %d cells, over the %d-cell limit."
                    % (rows, cols, MAX_CELLS), rows=rows, columns=cols)
            target = result_range(c1, r1, rows, cols)
            # Rewriting the same array formula in place is an update.
            block = self._array_block(sheet, c1, r1)
            if block is not None and (block.StartColumn, block.StartRow) \
                    == (c1, r1):
                sheet.getCellRangeByPosition(
                    block.StartColumn, block.StartRow,
                    block.EndColumn, block.EndRow).setArrayFormula("")
            formulas = sheet.getCellRangeByPosition(*target).getFormulaArray()
            occupied = [
                (i, j) for i, row in enumerate(formulas)
                for j, value in enumerate(row) if value not in ("", None)]
            if occupied:
                i, j = occupied[0]
                raise ArrayFormulaError(
                    "target_not_empty",
                    "The result needs %s, but %d cell(s) there are not empty "
                    "(first: %s%d). Nothing was written; clear them or start "
                    "elsewhere." % (name(*target), len(occupied),
                                    index_to_column(target[0] + j),
                                    target[1] + i + 1),
                    needed_range=name(*target), rows=rows, columns=cols)

        rng = sheet.getCellRangeByPosition(*target)
        rng.setArrayFormula(formula)
        anchor = sheet.getCellByPosition(target[0], target[1])
        if anchor.getError():
            raise ArrayFormulaError(
                "formula_error",
                "The formula returns an error (%s, code %d)."
                % (anchor.getString(), anchor.getError()),
                error=anchor.getString(), error_code=anchor.getError())
        preview = [list(r) for r in rng.getDataArray()[:5]]
        return {
            "message": "Array formula entered on %s (%d x %d)."
                       % (name(*target), rows, cols),
            "array": True,
            "range": "%s.%s" % (sheet.getName(), name(*target)),
            "rows": rows,
            "columns": cols,
            "preview": preview,
            **({"warning": " ".join(notes)} if notes else {}),
        }

    def import_csv_from_string(self, csv_data: str, target_cell: str = "A1"):
        """Import CSV data into the sheet starting at *target_cell*.

        Automatically detects comma vs semicolon delimiter.

        Args:
            csv_data: CSV content as a string.
            target_cell: Starting cell (e.g. "A1").

        Returns:
            Summary string.
        """
        try:
            delimiter = ","
            first_line = csv_data.split('\n')[0] if csv_data else ""
            if ";" in first_line and "," not in first_line:
                delimiter = ";"

            col_start, row_start = parse_address(target_cell)
            reader = csv.reader(io.StringIO(csv_data), delimiter=delimiter)
            rows = list(reader)
            if not rows:
                return "No data to import."

            sheet = self.bridge.get_active_sheet()
            total_rows = len(rows)
            total_cols = max(len(r) for r in rows) if rows else 0

            for r_idx, row_data in enumerate(rows):
                for c_idx, cell_value in enumerate(row_data):
                    col = col_start + c_idx
                    row = row_start + r_idx
                    cell = sheet.getCellByPosition(col, row)
                    try:
                        num = float(cell_value)
                        cell.setValue(num)
                    except ValueError:
                        cell.setString(cell_value)

            range_imported = (
                f"{target_cell}:"
                f"{self.bridge._index_to_column(col_start + total_cols - 1)}"
                f"{row_start + total_rows}"
            )
            logger.info("CSV imported to range %s.", range_imported)
            return f"Imported {total_rows} rows, {total_cols} cols to {range_imported}."
        except Exception as e:
            logger.error("CSV import error: %s", str(e))
            raise

    # ── Chart ──────────────────────────────────────────────────────────

    def create_chart(
        self,
        data_range: str,
        chart_type: str,
        title: str = None,
        position: str = None,
        has_header: bool = True,
        sheet_name: str = None,
    ):
        """Create a chart from data.

        The chart goes on *sheet_name*, else on the sheet named by
        *position*, else on the active sheet — as Insert > Chart does. The
        data can live anywhere: a sheet-qualified *data_range* reads another
        sheet, an unqualified one reads the chart's sheet (#31).

        Args:
            data_range: Range for chart data (e.g. "A1:B10",
                "Data.A1:B10" for another sheet).
            chart_type: Chart type (bar, line, pie, scatter, column).
            title: Chart title.
            position: Cell where chart is placed (e.g. "E1").
            has_header: Whether first row/column is a label.
            sheet_name: Sheet the chart is placed on.

        Returns:
            dict with message, chart name and the placement and data sheets.
        """
        try:
            from plugin.modules.calc.address_utils import split_sheet_prefix

            # Placement: sheet_name, else position's prefix, else active.
            if position:
                chart_sheet, position = self.bridge.resolve(
                    position, sheet_name)
            elif sheet_name:
                chart_sheet = self.bridge.get_sheet(sheet_name)
            else:
                chart_sheet = self.bridge.get_active_sheet()

            # Data: its own prefix, else the chart's sheet. A prefix that
            # differs from sheet_name is the ordinary layout here — chart on
            # a summary sheet, data elsewhere — not a conflict.
            data_prefix, data_address = split_sheet_prefix(data_range)
            data_sheet = (self.bridge.get_sheet(data_prefix)
                          if data_prefix is not None else chart_sheet)
            cell_range = self.bridge.get_cell_range(data_sheet, data_address)
            range_address = cell_range.getRangeAddress()

            if position:
                # Pixel position from the sheet the chart is drawn on.
                col, row = parse_address(position)
                pos_cell = self.bridge.get_cell(chart_sheet, col, row)
                pos_x = pos_cell.Position.X
                pos_y = pos_cell.Position.Y
            else:
                pos_x = 10000
                pos_y = 1000

            from com.sun.star.awt import Rectangle

            rect = Rectangle()
            rect.X = pos_x
            rect.Y = pos_y
            rect.Width = 12000
            rect.Height = 8000

            charts = chart_sheet.getCharts()
            chart_name = self._unique_chart_name()

            type_map = {
                "bar": "com.sun.star.chart.BarDiagram",
                "column": "com.sun.star.chart.BarDiagram",
                "line": "com.sun.star.chart.LineDiagram",
                "pie": "com.sun.star.chart.PieDiagram",
                "scatter": "com.sun.star.chart.XYDiagram",
            }
            chart_service = type_map.get(chart_type, "com.sun.star.chart.BarDiagram")

            charts.addNewByName(
                chart_name, rect, (range_address,), has_header, has_header,
            )

            chart = charts.getByName(chart_name).getEmbeddedObject()
            diagram = chart.createInstance(chart_service)
            chart.setDiagram(diagram)

            if chart_type == "bar" and hasattr(diagram, "Vertical"):
                diagram.Vertical = True
            elif chart_type == "column" and hasattr(diagram, "Vertical"):
                diagram.Vertical = False

            if title:
                chart.setPropertyValue("HasMainTitle", True)
                chart_title = chart.getTitle()
                chart_title.setPropertyValue("String", title)

            logger.info("Chart created: %s (%s)", chart_name, chart_type)
            return {
                "message": f"{chart_type} type chart created.",
                "chart_name": chart_name,
                "sheet": chart_sheet.getName(),
                "data_sheet": data_sheet.getName(),
            }
        except Exception as e:
            logger.error("Chart creation error: %s", str(e))
            raise

    def _unique_chart_name(self):
        """A chart name no sheet uses yet.

        Chart names are unique per document, not per sheet, so counting the
        target sheet's charts collides as soon as two sheets have one (#32).
        """
        taken = set()
        sheets = self.bridge.doc.getSheets()
        for i in range(sheets.getCount()):
            try:
                taken.update(sheets.getByIndex(i).getCharts().getElementNames())
            except Exception:
                pass
        try:
            taken.update(self.bridge.doc.getEmbeddedObjects().getElementNames())
        except Exception:
            pass
        n = len(taken)
        while "Chart_%d" % n in taken:
            n += 1
        return "Chart_%d" % n

    # ── Structure operations ───────────────────────────────────────────

    def delete_rows(self, row_num: int, count: int = 1):
        """Delete rows starting at *row_num* (1-based)."""
        try:
            sheet = self.bridge.get_active_sheet()
            rows = sheet.getRows()
            rows.removeByIndex(row_num - 1, count)
            logger.info("%d row(s) deleted starting from row %d.", count, row_num)
            return f"{count} row(s) deleted starting from row {row_num}."
        except Exception as e:
            logger.error("Row deletion error: %s", str(e))
            raise

    def delete_columns(self, col_letter: str, count: int = 1):
        """Delete columns starting at *col_letter*."""
        try:
            sheet = self.bridge.get_active_sheet()
            columns = sheet.getColumns()
            col_index = self.bridge._column_to_index(col_letter.upper())
            columns.removeByIndex(col_index, count)
            logger.info(
                "%d column(s) deleted starting from column %s.",
                count, col_letter.upper(),
            )
            return f"{count} column(s) deleted starting from column {col_letter.upper()}."
        except Exception as e:
            logger.error("Column deletion error: %s", str(e))
            raise

    def delete_structure(self, structure_type: str, start, count: int = 1):
        """Delete rows or columns.

        Args:
            structure_type: "rows" or "columns".
            start: For rows, row number (1-based); for columns, column letter.
            count: Number to delete.
        """
        if structure_type == "rows":
            return self.delete_rows(start, count)
        elif structure_type == "columns":
            return self.delete_columns(start, count)
        else:
            raise ValueError(
                f"Invalid structure_type: {structure_type}. "
                f"Must be 'rows' or 'columns'."
            )

    # ── Sheet management ───────────────────────────────────────────────

    def list_sheets(self):
        """List all sheet names in the workbook.

        Returns:
            List of sheet name strings.
        """
        try:
            doc = self.bridge.get_active_document()
            sheets = doc.getSheets()
            sheet_names = []
            for i in range(sheets.getCount()):
                sheet = sheets.getByIndex(i)
                sheet_names.append(sheet.getName())
            logger.info("Sheets listed: %s", sheet_names)
            return sheet_names
        except Exception as e:
            logger.error("Sheet listing error: %s", str(e))
            raise

    def switch_sheet(self, sheet_name: str):
        """Switch to the specified sheet.

        Args:
            sheet_name: Name of the sheet to activate.

        Returns:
            Confirmation string.
        """
        try:
            doc = self.bridge.get_active_document()
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                raise ValueError(f"No sheet found named '{sheet_name}'.")
            sheet = sheets.getByName(sheet_name)
            controller = doc.getCurrentController()
            controller.setActiveSheet(sheet)
            logger.info("Switched to sheet: %s", sheet_name)
            return f"Switched to sheet '{sheet_name}'."
        except Exception as e:
            logger.error("Sheet switch error (%s): %s", sheet_name, str(e))
            raise

    def create_sheet(self, sheet_name: str, position: int = None):
        """Create a new sheet.

        Args:
            sheet_name: New sheet name.
            position: 0-based position (appended to end if None).

        Returns:
            Confirmation string.
        """
        try:
            doc = self.bridge.get_active_document()
            sheets = doc.getSheets()
            if position is None:
                position = sheets.getCount()
            sheets.insertNewByName(sheet_name, position)
            logger.info("New sheet created: %s (position: %d)", sheet_name, position)
            return f"New sheet named '{sheet_name}' created."
        except Exception as e:
            logger.error("Sheet creation error (%s): %s", sheet_name, str(e))
            raise

    def rename_sheet(self, sheet_name: str, new_name: str):
        """Rename a sheet.

        Thin wrapper over ``XNamed::setName()``, so LibreOffice rewrites
        every reference to the sheet (formulas, cross-sheet references,
        named ranges, chart data ranges) automatically.

        Args:
            sheet_name: Current name of the sheet to rename.
            new_name: New name.

        Returns:
            Confirmation string.
        """
        try:
            doc = self.bridge.get_active_document()
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                raise ValueError(f"No sheet found named '{sheet_name}'.")
            if new_name == sheet_name:
                return f"Sheet '{sheet_name}' already has that name."
            if sheets.hasByName(new_name):
                raise ValueError(f"A sheet named '{new_name}' already exists.")
            sheet = sheets.getByName(sheet_name)
            sheet.setName(new_name)
            logger.info("Sheet renamed: %s -> %s", sheet_name, new_name)
            return f"Sheet '{sheet_name}' renamed to '{new_name}'."
        except Exception as e:
            logger.error("Sheet rename error (%s -> %s): %s",
                         sheet_name, new_name, str(e))
            raise

    def delete_sheet(self, sheet_name: str):
        """Delete a sheet from the workbook.

        Args:
            sheet_name: Name of the sheet to delete.

        Returns:
            Confirmation string.
        """
        try:
            doc = self.bridge.get_active_document()
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                raise ValueError(f"No sheet found named '{sheet_name}'.")
            if sheets.getCount() <= 1:
                raise ValueError(
                    "Cannot delete the only sheet; a workbook must keep "
                    "at least one sheet.")
            sheets.removeByName(sheet_name)
            logger.info("Sheet deleted: %s", sheet_name)
            return f"Sheet '{sheet_name}' deleted."
        except Exception as e:
            logger.error("Sheet deletion error (%s): %s", sheet_name, str(e))
            raise
