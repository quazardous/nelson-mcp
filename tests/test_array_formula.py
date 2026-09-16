# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Array formula detection for calc_write_formula (#2631)."""

import pytest

from plugin.modules.calc.array_formula import (
    result_range, returns_array, top_level_calls)


@pytest.mark.parametrize("formula, expected", [
    ("=SORT(FILTER(A2:C20;B2:B20=2022);3;-1)", True),
    ("=FILTER(A2:C20;B2:B20>0)", True),
    ("=unique(A1:A9)", True),
    ("=SEQUENCE(5)", True),
    ("=TRANSPOSE(A1:C1)*2", True),
    ("=SUM(FILTER(A2:A9;B2:B9>0))", False),
    ("=COUNT(UNIQUE(A1:A9))", False),
    ("=C2+D2-1", False),
    ('="FILTER("&A1', False),
    ("plain text", False),
    ("=MYFILTER(A1)", False),
])
def test_detection(formula, expected):
    assert returns_array(formula) is expected


def test_forced_value_wins():
    assert returns_array("=A1:A5*2", forced=True) is True
    assert returns_array("=FILTER(A1:A5;B1:B5)", forced=False) is False


def test_top_level_calls():
    assert top_level_calls("=IF(A1;SORT(B1:B9);0)+ROWS(C1:C9)") == ["IF", "ROWS"]


def test_result_range():
    assert result_range(4, 0, 3, 2) == (4, 0, 5, 2)
