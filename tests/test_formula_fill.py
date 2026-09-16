# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A single formula on a range is filled, not copied (#2633)."""

import sys
import types

import pytest

from plugin.modules.calc.manipulator import CellManipulator


@pytest.fixture(autouse=True)
def fill_direction(monkeypatch):
    mod = types.ModuleType("com.sun.star.sheet.FillDirection")
    mod.TO_BOTTOM, mod.TO_RIGHT = "TO_BOTTOM", "TO_RIGHT"
    for name in ("com", "com.sun", "com.sun.star", "com.sun.star.sheet"):
        monkeypatch.setitem(sys.modules, name,
                            sys.modules.get(name) or types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "com.sun.star.sheet.FillDirection", mod)


class Cell:
    def __init__(self, log, pos):
        self.log, self.pos = log, pos

    def setFormula(self, f):
        self.log.append(("formula", self.pos, f))

    def setValue(self, v):
        self.log.append(("value", self.pos, v))

    def setString(self, v):
        self.log.append(("string", self.pos, v))

    def getFormula(self):
        return "=last"

    def getPropertyValue(self, name):
        return 0


class Range:
    def __init__(self, log, box):
        self.log, self.box = log, box

    def fillAuto(self, direction, count):
        self.log.append(("fill", self.box, direction, count))


class Sheet:
    def __init__(self):
        self.log = []

    def getName(self):
        return "Plan"

    def getCellByPosition(self, c, r):
        return Cell(self.log, (c, r))

    def getCellRangeByPosition(self, *box):
        return Range(self.log, box)


class Bridge:
    def __init__(self):
        self.sheet = Sheet()
        self.doc = None

    def resolve(self, ref, sheet_name=None):
        return self.sheet, ref.split(".")[-1]

    @staticmethod
    def parse_range_string(address):
        from plugin.modules.calc.address_utils import parse_range_string
        return parse_range_string(address)

    @staticmethod
    def split_prefix(ref):
        return (None, ref)


def run(range_str, value):
    bridge = Bridge()
    result = CellManipulator(bridge).write_formula_range(range_str, value)
    return bridge.sheet.log, result


def test_formula_on_a_column_is_written_once_then_filled_down():
    log, result = run("E2:E9", "=C2+D2-1")
    assert log == [("formula", (4, 1), "=C2+D2-1"),
                   ("fill", (4, 1, 4, 8), "TO_BOTTOM", 1)]
    assert "filled from E2 across E2:E9" in result


def test_formula_on_a_block_fills_down_then_right():
    log, _ = run("F2:G3", "=$A$1+B2")
    assert log == [("formula", (5, 1), "=$A$1+B2"),
                   ("fill", (5, 1, 5, 2), "TO_BOTTOM", 1),
                   ("fill", (5, 1, 6, 2), "TO_RIGHT", 1)]


def test_formula_in_one_cell_is_just_written():
    log, _ = run("E2", "=C2+D2-1")
    assert log == [("formula", (4, 1), "=C2+D2-1")]


def test_a_constant_is_still_copied_not_incremented():
    log, _ = run("H2:H4", "7")
    assert [e[0] for e in log] == ["value", "value", "value"]
    assert all(e[2] == 7.0 for e in log)


def test_one_formula_per_cell_is_written_as_given():
    log, _ = run("A1:A2", ["=B1", "=B1"])
    assert log == [("formula", (0, 0), "=B1"), ("formula", (0, 1), "=B1")]
