# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""In-process UNO bridge for Calc.

Wraps a Calc document and provides convenience methods for accessing
sheets, cells, and ranges. Ported from core/calc_bridge.py for the
plugin framework.
"""

import logging

from plugin.modules.calc.address_utils import (
    index_to_column,
    column_to_index,
    parse_range_string,
    split_sheet_prefix,
)

logger = logging.getLogger("nelson.calc")


class CalcBridge:
    """Bridge between the plugin layer and the UNO Calc document."""

    def __init__(self, doc):
        self.doc = doc

    def get_active_document(self):
        """Return the wrapped document."""
        return self.doc

    def get_active_sheet(self):
        """Return the currently active sheet.

        Falls back to the first sheet when the controller does not expose
        *getActiveSheet* (e.g. headless mode).

        Raises:
            RuntimeError: Document is not a spreadsheet or no sheet found.
        """
        if not hasattr(self.doc, "getSheets"):
            raise RuntimeError("Active document is not a spreadsheet.")

        controller = self.doc.getCurrentController()
        if hasattr(controller, "getActiveSheet"):
            sheet = controller.getActiveSheet()
        else:
            sheets = self.doc.getSheets()
            sheet = sheets.getByIndex(0)

        if sheet is None:
            raise RuntimeError("No active sheet found.")
        return sheet

    def get_sheet(self, name):
        """Return a sheet by name.

        Raises:
            ValueError: no such sheet, listing the ones that exist.
        """
        sheets = self.doc.getSheets()
        if not sheets.hasByName(name):
            raise ValueError(
                "No sheet named '%s'. Available: %s"
                % (name, ", ".join(sheets.getElementNames())))
        return sheets.getByName(name)

    def resolve(self, ref: str, sheet_name: str = None):
        """Resolve a possibly sheet-qualified reference.

        Returns ``(sheet, address)`` where *address* has no prefix. A
        prefix on the reference wins over *sheet_name*; disagreeing is an
        error rather than a silent choice (#30).
        """
        prefix, address = split_sheet_prefix(ref)
        if prefix is not None and sheet_name and prefix != sheet_name:
            raise ValueError(
                "Reference names sheet '%s' but sheet_name says '%s' — "
                "pass one or the other." % (prefix, sheet_name))
        name = prefix or sheet_name
        sheet = self.get_sheet(name) if name else self.get_active_sheet()
        return sheet, address

    def get_cell(self, sheet, col: int, row: int):
        """Return the cell object at *col*, *row* on *sheet*."""
        return sheet.getCellByPosition(col, row)

    def get_cell_range(self, sheet, range_str: str):
        """Return a cell range object from a range string like ``A1:D10``.

        A sheet prefix on *range_str* wins over the *sheet* argument, so a
        caller that has already resolved the active sheet still honours an
        explicit ``Sheet1.A1:C5`` (#30).
        """
        prefix, range_str = split_sheet_prefix(range_str)
        if prefix is not None:
            sheet = self.get_sheet(prefix)
        start, end = parse_range_string(range_str)
        return sheet.getCellRangeByPosition(start[0], start[1], end[0], end[1])

    @staticmethod
    def _index_to_column(index: int) -> str:
        return index_to_column(index)

    @staticmethod
    def _column_to_index(col_str: str) -> int:
        return column_to_index(col_str)

    @staticmethod
    def parse_range_string(range_str: str):
        return parse_range_string(range_str)
