# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for Calc sheet targeting and chart naming (#32, #33)."""

import pytest

from plugin.modules.calc.address_utils import same_sheet_name
from plugin.modules.calc.bridge import CalcBridge
from plugin.modules.calc.manipulator import CellManipulator
from plugin.modules.calc.tools.comments import _split_cell_sheet
from plugin.modules.calc.tools.sheets import _error_text


class Names:
    def __init__(self, names):
        self._names = list(names)

    def getElementNames(self):
        return tuple(self._names)


class Sheet:
    def __init__(self, name, charts=()):
        self._name = name
        self._charts = Names(charts)

    def getName(self):
        return self._name

    def getCharts(self):
        return self._charts


class Sheets:
    def __init__(self, sheets):
        self._sheets = sheets

    def getCount(self):
        return len(self._sheets)

    def getByIndex(self, i):
        return self._sheets[i]

    def hasByName(self, name):
        return any(same_sheet_name(s.getName(), name) for s in self._sheets)

    def getByName(self, name):
        return next(s for s in self._sheets
                    if same_sheet_name(s.getName(), name))

    def getElementNames(self):
        return tuple(s.getName() for s in self._sheets)


class Doc:
    def __init__(self, sheets):
        self._sheets = Sheets(sheets)

    def getSheets(self):
        return self._sheets


def test_chart_names_are_unique_across_sheets():
    doc = Doc([Sheet("Capex", ["Chart_0"]), Sheet("Data", [])])
    name = CellManipulator(CalcBridge(doc))._unique_chart_name()
    assert name != "Chart_0"


def test_chart_name_skips_gaps():
    doc = Doc([Sheet("A", ["Chart_1"]), Sheet("B", ["Chart_2"])])
    assert CellManipulator(CalcBridge(doc))._unique_chart_name() == "Chart_3"


def test_sheet_names_compare_like_calc():
    assert same_sheet_name("Summary", "summary")
    assert not same_sheet_name("Summary", "Sources")


def test_prefix_disagreeing_with_sheet_name_is_refused():
    with pytest.raises(ValueError, match="pass one or the other"):
        CalcBridge(Doc([Sheet("Summary"), Sheet("Sources")])).resolve(
            "Summary.B4", "Sources")
    with pytest.raises(ValueError, match="pass one or the other"):
        _split_cell_sheet("Summary.C2", "Sources")


def test_agreeing_prefix_and_case_are_accepted():
    sheet, address = CalcBridge(Doc([Sheet("Summary")])).resolve(
        "summary.B4", "Summary")
    assert (sheet.getName(), address) == ("Summary", "B4")
    assert _split_cell_sheet("C2", "Summary") == ("C2", "Summary")


def test_unknown_sheet_lists_available():
    with pytest.raises(ValueError, match="Available: Summary, Sources"):
        CalcBridge(Doc([Sheet("Summary"), Sheet("Sources")])).resolve("Nope.A1")


class Silent(Exception):
    def __str__(self):
        return ""


def test_error_text_is_never_empty():
    assert _error_text(ValueError("boom")) == "boom"
    e = Silent()
    e.Message = "Chart_0 already exists"
    assert _error_text(e) == "Chart_0 already exists"
    assert "Silent" in _error_text(Silent())
