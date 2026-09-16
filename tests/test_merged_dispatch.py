# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Merged tools refuse another action's parameters; chart legends (#2641)."""

from plugin.framework.tool_base import ToolBase
from plugin.framework.tool_merge import dispatch
from plugin.modules.calc.manipulator import chart_series_count, default_legend


class Create(ToolBase):
    parameters = {"type": "object",
                  "properties": {"data_range": {}, "chart_type": {}}}

    def execute(self, ctx, **kwargs):
        return {"status": "ok", "got": kwargs}


class Edit(ToolBase):
    parameters = {"type": "object",
                  "properties": {"chart_name": {}, "has_legend": {}}}

    def execute(self, ctx, **kwargs):
        return {"status": "ok", "got": kwargs}


IMPL = {"create": Create, "edit": Edit}


def test_own_parameters_pass_through():
    res = dispatch(IMPL, None, "create", {"data_range": "A1:B3",
                                          "chart_type": "bar"})
    assert res["status"] == "ok"


def test_another_actions_parameter_is_refused_and_attributed():
    res = dispatch(IMPL, None, "create", {"data_range": "A1:B3",
                                          "has_legend": True})
    assert res["code"] == "invalid_params" and res["retryable"] is False
    assert "has_legend belongs to edit" in res["message"]
    assert "It accepts: chart_type, data_range" in res["message"]


def test_unknown_parameter_is_refused():
    res = dispatch(IMPL, None, "edit", {"colour": "red"})
    assert "colour is not a parameter of any action" in res["message"]


def test_meta_arguments_are_left_alone():
    assert dispatch(IMPL, None, "edit", {"_trace": 1})["status"] == "ok"


def test_series_and_default_legend():
    assert chart_series_count("line", 6, True) == 5
    assert chart_series_count("bar", 2, True) == 1
    assert chart_series_count("scatter", 3, False) == 2
    assert chart_series_count("bar", 3, False) == 3
    assert default_legend("line", 5) is True
    assert default_legend("bar", 1) is False
    assert default_legend("pie", 1) is True
