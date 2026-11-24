# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer equations (GitHub #49): what can be checked without UNO."""

import pytest

from plugin.framework.tool_base import TOOL_GROUPS
from plugin.modules.writer import equations as eq
from plugin.modules.writer.tools import equations as tools


class _Cell:
    def __init__(self, text):
        self.text = text

    def getString(self):
        return self.text


class _Table:
    def __init__(self, cells):
        self.cells = cells

    def getCellNames(self):
        return list(self.cells)

    def getCellByName(self, name):
        return _Cell(self.cells[name])


@pytest.mark.parametrize("cells, cell, number", [
    ({"A1": "", "B1": "(1)"}, "A1", "(1)"),       # Writer's fn AutoText
    ({"A1": "(2.3)", "B1": ""}, "B1", "(2.3)"),   # number on the left
    ({"A1": "", "B1": "see text"}, "A1", None),   # not a number
    ({"A1": "", "B1": "(1)", "A2": ""}, "A1", None),  # not a 1x2 table
])
def test_a_numbered_equation_reads_its_number(cells, cell, number):
    assert eq._equation_number(_Table(cells), cell) == number


@pytest.mark.parametrize("value, mode", [
    ("replace", "replace"), ("in_place", "in_place"),
    (None, "replace"), ("bogus", "replace"),
])
def test_update_mode_defaults_to_the_undoable_one(value, mode):
    class _Config:
        def proxy_for(self, module):
            return {"equation_update": value}
    assert eq.update_mode(_Config()) == mode


def test_equation_tools_belong_to_a_known_group():
    for cls in (tools.ListEquations, tools.SetEquation,
                tools.InsertEquation, tools.DeleteEquation):
        assert cls().tool_group() in TOOL_GROUPS
        assert cls().tool_group() == "text"


def test_only_the_list_is_a_read():
    assert tools.ListEquations.is_mutation is False
    for cls in (tools.SetEquation, tools.InsertEquation,
                tools.DeleteEquation):
        assert cls.is_mutation is True
