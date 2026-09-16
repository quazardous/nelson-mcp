# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""calc_query engine (#2630)."""

import pytest

from plugin.modules.calc.query_engine import QueryError, run_query

H = ["country", "year", "iso_code", "co2"]
ROWS = [
    ["China", 2022.0, "CHN", 11711.808],
    ["World", 2022.0, "", 37149.8],
    ["United States", 2022.0, "USA", 5055.403],
    ["India", 2022.0, "IND", 2831.132],
    ["China", 2021.0, "CHN", 11472.0],
    ["Czechia", 2022.0, "CZE", "95.1"],      # a number stored as text
    ["Nowhere", 2022.0, "NWH", ""],
]


def test_top_emitters():
    res = run_query(H, ROWS,
                    where=[{"column": "year", "op": "=", "value": 2022},
                           {"column": "iso_code", "op": "not_empty"}],
                    select=["country", "co2"], order_by="co2 desc", limit=3)
    assert res["rows"] == [["China", 11711.808], ["United States", 5055.403],
                           ["India", 2831.132]]
    assert res["matched"] == 5 and res["truncated"] is True


def test_text_numbers_compare_as_numbers_and_empties_sort_last():
    res = run_query(H, ROWS, where=[{"column": "co2", "op": ">", "value": 90}],
                    select=["country"], order_by={"column": "co2"}, limit=10)
    assert res["rows"][0] == ["Czechia"]
    res = run_query(H, ROWS, select=["country", "co2"],
                    order_by="co2 desc", limit=10)
    assert res["rows"][-1] == ["Nowhere", ""]


def test_group_by_and_aggregates():
    res = run_query(H, ROWS, group_by=["country"],
                    aggregate=[{"column": "co2", "fn": "sum"},
                               {"fn": "count"}],
                    order_by="sum(co2) desc", limit=2)
    assert res["columns"] == ["country", "sum(co2)", "count"]
    assert res["rows"][0] == ["World", 37149.8, 1]
    assert res["rows"][1] == ["China", 23183.808, 2]


def test_columns_by_letter_and_case_insensitive_names():
    res = run_query(H, ROWS, where=[{"column": "A", "op": "contains",
                                     "value": "unit"}],
                    select=["COUNTRY", "d"])
    assert res["rows"] == [["United States", 5055.403]]


def test_in_operator():
    res = run_query(H, ROWS, where=[{"column": "iso_code", "op": "in",
                                     "value": ["CHN", "IND"]}],
                    select=["country"])
    assert len(res["rows"]) == 3


@pytest.mark.parametrize("kwargs, message", [
    ({"where": [{"column": "nope", "op": "="}]}, "Headers: country"),
    ({"where": [{"column": "year", "op": "~"}]}, "Allowed:"),
    ({"limit": 0}, "positive"),
    ({"aggregate": [{"column": "co2", "fn": "median"}]}, "fn in"),
])
def test_errors_say_what_is_allowed(kwargs, message):
    with pytest.raises(QueryError, match=message):
        run_query(H, ROWS, **kwargs)


def test_limit_is_capped():
    res = run_query(H, ROWS * 300, limit=5000)
    assert res["returned"] == 1000
