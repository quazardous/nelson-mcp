# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cell inspector — reads detailed information from LibreOffice Calc cells.

Ported from core/calc_inspector.py for the plugin framework.
"""

import logging
import re

from plugin.modules.calc.address_utils import parse_address, split_sheet_prefix

try:
    from com.sun.star.table.CellContentType import EMPTY, VALUE, TEXT, FORMULA
    UNO_AVAILABLE = True
except ImportError:
    EMPTY, VALUE, TEXT, FORMULA = 0, 1, 2, 3
    UNO_AVAILABLE = False

logger = logging.getLogger("nelson.calc")


class CellInspector:
    """Examines cell contents and properties."""

    def __init__(self, bridge):
        """
        Args:
            bridge: CalcBridge instance.
        """
        self.bridge = bridge

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _cell_type_name(cell_type) -> str:
        """Return a human-readable name for a UNO cell content type."""
        if cell_type == EMPTY:
            return "empty"
        if cell_type == VALUE:
            return "value"
        if cell_type == TEXT:
            return "text"
        if cell_type == FORMULA:
            return "formula"
        return "unknown"

    @staticmethod
    def _safe_prop(cell, name, default=None):
        try:
            return cell.getPropertyValue(name)
        except Exception:
            return default

    def _get_cell(self, address: str):
        """Return the cell object for *address*."""
        sheet, address = self.bridge.resolve(address)
        col, row = parse_address(address)
        return self.bridge.get_cell(sheet, col, row)

    # ── Public API ─────────────────────────────────────────────────────

    def read_cell(self, address: str) -> dict:
        """Read basic cell information.

        Args:
            address: Cell address (e.g. "A1").

        Returns:
            dict with keys: address, value, formula, type.
        """
        try:
            cell = self._get_cell(address)
            cell_type = cell.getType()

            if cell_type == EMPTY:
                value = None
            elif cell_type == VALUE:
                value = cell.getValue()
            elif cell_type == TEXT:
                value = cell.getString()
            elif cell_type == FORMULA:
                value = cell.getValue() if cell.getValue() != 0 else cell.getString()
            else:
                value = cell.getString()

            formula = cell.getFormula() if cell_type == FORMULA else None

            result = {
                # The resolved address: no sheet prefix, like read_range (#33).
                "address": split_sheet_prefix(address)[1].upper(),
                "value": value,
                "formula": formula,
                "type": self._cell_type_name(cell_type),
            }
            if cell_type == FORMULA:
                sheet, bare = self.bridge.resolve(address)
                col, row = parse_address(bare)
                block = _array_block(sheet, col, row)
                if block:
                    result["array_range"] = block
            return result
        except Exception as e:
            # A bad address or sheet name is the caller's mistake, not a
            # fault: log it quietly so real errors stay visible (#30).
            level = logger.debug if isinstance(e, ValueError) else logger.error
            level("Cell reading error (%s): %s", address, str(e))
            raise

    def get_cell_details(self, address: str) -> dict:
        """Return all detailed cell information.

        Args:
            address: Cell address (e.g. "A1").

        Returns:
            dict with keys: address, value, formula, formula_local, type,
            background_color, number_format, font_color, font_size, bold,
            italic, h_align, v_align, wrap_text.
        """
        try:
            cell = self._get_cell(address)
            cell_type = cell.getType()

            if cell_type == EMPTY:
                value = None
            elif cell_type == VALUE:
                value = cell.getValue()
            elif cell_type == TEXT:
                value = cell.getString()
            elif cell_type == FORMULA:
                value = cell.getValue() if cell.getValue() != 0 else cell.getString()
            else:
                value = cell.getString()

            return {
                # The resolved address: no sheet prefix, like read_range (#33).
                "address": split_sheet_prefix(address)[1].upper(),
                "value": value,
                "formula": cell.getFormula(),
                "formula_local": self._safe_prop(cell, "FormulaLocal"),
                "type": self._cell_type_name(cell_type),
                "background_color": self._safe_prop(cell, "CellBackColor"),
                "number_format": self._safe_prop(cell, "NumberFormat"),
                "font_color": self._safe_prop(cell, "CharColor"),
                "font_size": self._safe_prop(cell, "CharHeight"),
                "bold": self._safe_prop(cell, "CharWeight"),
                "italic": self._safe_prop(cell, "CharPosture"),
                "h_align": self._safe_prop(cell, "HoriJustify"),
                "v_align": self._safe_prop(cell, "VertJustify"),
                "wrap_text": self._safe_prop(cell, "IsTextWrapped"),
            }
        except Exception as e:
            logger.error("Cell detailed reading error (%s): %s", address, str(e))
            raise

    def read_range(self, range_name: str) -> list[list[dict]]:
        """Read values and formulas in a cell range.

        Args:
            range_name: Cell range (e.g. "A1:D10", "B2").

        Returns:
            2D list of dicts, each with keys: address, value, formula, type.
        """
        try:
            # Single cell shortcut — pass the reference through untouched
            # so read_cell resolves the sheet itself. Handing it the
            # stripped address would silently read the active sheet (#30).
            if ":" not in range_name:
                return [[self.read_cell(range_name)]]

            sheet, addr, data, formulas = self._read_block(range_name)
            covered = _array_cover(sheet, addr, formulas)
            result = []
            for r, (data_row, formula_row) in enumerate(zip(data, formulas)):
                row_data = []
                for c, (value, formula) in enumerate(zip(data_row,
                                                         formula_row)):
                    col, row = addr.StartColumn + c, addr.StartRow + r
                    kind = _kind(value, formula)
                    in_array = covered.get((col, row))
                    if in_array:
                        # Only an array formula's top-left cell carries the
                        # formula in getFormulaArray; the rest are its cells.
                        kind, formula = "formula", in_array[1]
                    entry = {
                        "address": "%s%d" % (self.bridge._index_to_column(col),
                                             row + 1),
                        "value": None if kind == "empty" else value,
                        "formula": formula if kind == "formula" else None,
                        "type": kind,
                    }
                    if in_array:
                        entry["array_range"] = in_array[0]
                    row_data.append(entry)
                result.append(row_data)
            return result
        except Exception as e:
            level = logger.debug if isinstance(e, ValueError) else logger.error
            level("Range reading error (%s): %s", range_name, str(e))
            raise

    def read_range_rows(self, range_name: str) -> dict:
        """Compact read: values as rows, formulas listed apart (#2630).

        Returns {"range", "rows": [[value or None]], "formulas": {addr: f},
        "array_ranges": {addr: "E1:G4"}} — no per-cell address or type, so a
        cell costs a few bytes instead of ~86.
        """
        try:
            sheet, addr, data, formulas = self._read_block(range_name)
            covered = _array_cover(sheet, addr, formulas)
            rows, found, arrays = [], {}, {}
            for r, (data_row, formula_row) in enumerate(zip(data, formulas)):
                out = []
                for c, (value, formula) in enumerate(zip(data_row,
                                                         formula_row)):
                    kind = _kind(value, formula)
                    out.append(None if kind == "empty" else value)
                    if kind == "formula":
                        col, row = addr.StartColumn + c, addr.StartRow + r
                        name = "%s%d" % (self.bridge._index_to_column(col),
                                         row + 1)
                        found[name] = formula
                        if (col, row) in covered:
                            arrays[name] = covered[(col, row)][0]
                rows.append(out)
            result = {"range": _address_name(self.bridge, addr), "rows": rows}
            if found:
                result["formulas"] = found
            if arrays:
                result["array_ranges"] = arrays
            return result
        except Exception as e:
            level = logger.debug if isinstance(e, ValueError) else logger.error
            level("Range reading error (%s): %s", range_name, str(e))
            raise

    def _read_block(self, range_name):
        """(sheet, RangeAddress, values, formulas), read in two UNO calls.

        getDataArray / getFormulaArray return the whole range at once;
        reading cell by cell cost four UNO calls per cell (5.4 s for
        A1:CA2000 on the main thread).
        """
        sheet, address = self.bridge.resolve(range_name)
        cell_range = self.bridge.get_cell_range(sheet, address)
        return (sheet, cell_range.getRangeAddress(),
                cell_range.getDataArray(), cell_range.getFormulaArray())

    def get_all_formulas(self, sheet_name: str = None) -> list[dict]:
        """List all formulas in a sheet.

        Args:
            sheet_name: Sheet name (active sheet if None).

        Returns:
            List of dicts with keys: address, formula, value, precedents.
        """
        try:
            if sheet_name:
                doc = self.bridge.get_active_document()
                sheets = doc.getSheets()
                sheet = sheets.getByName(sheet_name)
            else:
                sheet = self.bridge.get_active_sheet()

            cursor = sheet.createCursor()
            cursor.gotoStartOfUsedArea(False)
            cursor.gotoEndOfUsedArea(True)

            addr = cursor.getRangeAddress()
            formulas = []

            for row in range(addr.StartRow, addr.EndRow + 1):
                for col in range(addr.StartColumn, addr.EndColumn + 1):
                    cell = sheet.getCellByPosition(col, row)
                    if cell.getType() == FORMULA:
                        col_letter = self.bridge._index_to_column(col)
                        cell_address = f"{col_letter}{row + 1}"
                        formula = cell.getFormula()
                        value = cell.getValue() if cell.getValue() != 0 else cell.getString()

                        refs = re.findall(r'\$?([A-Z]+)\$?(\d+)', formula.upper())
                        precedents = list(set([f"{c}{r}" for c, r in refs]))

                        formulas.append({
                            "address": cell_address,
                            "formula": formula,
                            "value": value,
                            "precedents": precedents,
                        })

            return formulas
        except Exception as e:
            logger.error("Formula listing error: %s", str(e))
            raise


def _array_block(sheet, col, row):
    """'A1:C5' when (col, row) is part of an array formula, else None."""
    try:
        cursor = sheet.createCursorByRange(
            sheet.getCellRangeByPosition(col, row, col, row))
        cursor.collapseToCurrentArray()
        a = cursor.getRangeAddress()
        # A plain formula cell collapses to itself without failing: only an
        # actual array formula has one to report.
        if not sheet.getCellRangeByPosition(
                a.StartColumn, a.StartRow, a.EndColumn,
                a.EndRow).getArrayFormula():
            return None
    except Exception:
        return None
    from plugin.modules.calc.address_utils import index_to_column
    return "%s%d:%s%d" % (index_to_column(a.StartColumn), a.StartRow + 1,
                          index_to_column(a.EndColumn), a.EndRow + 1)


def _array_cover(sheet, addr, formulas):
    """{(col, row): (block name, formula)} for cells inside array formulas.

    Array blocks are found from the formula cells of the range (the anchor,
    or any cell of a block that starts above or left of it) — one cursor per
    formula cell, none for plain values.
    """
    from plugin.modules.calc.address_utils import index_to_column

    cover, seen = {}, set()
    for r, row in enumerate(formulas):
        for c, formula in enumerate(row):
            col, rw = addr.StartColumn + c, addr.StartRow + r
            # Only array formula cells carry braces; plain formulas need no
            # cursor at all.
            if not (isinstance(formula, str) and formula.startswith("{=")):
                continue
            if (col, rw) in cover:
                continue
            try:
                cursor = sheet.createCursorByRange(
                    sheet.getCellRangeByPosition(col, rw, col, rw))
                cursor.collapseToCurrentArray()
                a = cursor.getRangeAddress()
                block = sheet.getCellRangeByPosition(
                    a.StartColumn, a.StartRow, a.EndColumn, a.EndRow)
                array_formula = block.getArrayFormula()
            except Exception:
                continue
            if not array_formula:
                continue
            key = (a.StartColumn, a.StartRow, a.EndColumn, a.EndRow)
            if key in seen:
                continue
            seen.add(key)
            name = "%s%d:%s%d" % (index_to_column(a.StartColumn),
                                  a.StartRow + 1, index_to_column(a.EndColumn),
                                  a.EndRow + 1)
            for cc in range(a.StartColumn, a.EndColumn + 1):
                for rr in range(a.StartRow, a.EndRow + 1):
                    cover[(cc, rr)] = (name, array_formula)
    return cover


def _kind(value, formula):
    """Cell type from a data-array value and a formula-array entry.

    Every cell of an array formula reports it in braces, "{=SORT(...)}".
    """
    if isinstance(formula, str) and (formula.startswith("=")
                                     or formula.startswith("{=")):
        return "formula"
    if value == "" and formula in ("", None):
        return "empty"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "value"
    return "text"


def _address_name(bridge, a):
    return "%s%d:%s%d" % (bridge._index_to_column(a.StartColumn),
                          a.StartRow + 1,
                          bridge._index_to_column(a.EndColumn), a.EndRow + 1)
