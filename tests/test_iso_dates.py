# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ISO date recognition for Calc writes (#2632)."""

import datetime

import pytest

from plugin.modules.calc.iso_dates import literal_text, parse_iso, serial


@pytest.mark.parametrize("text, expected", [
    ("2026-10-01", (datetime.datetime(2026, 10, 1), False)),
    ("2026-10-01T14:30", (datetime.datetime(2026, 10, 1, 14, 30), True)),
    ("2026-10-01 14:30:15", (datetime.datetime(2026, 10, 1, 14, 30, 15),
                             True)),
    (" 2026-10-01 ", (datetime.datetime(2026, 10, 1), False)),
])
def test_iso_forms_are_dates(text, expected):
    assert parse_iso(text) == expected


@pytest.mark.parametrize("text", [
    "2026-02-30", "1-2", "00123", "01/10/2026", "2026-1-1", "2026-10-01x",
    "Q3 2026-10-01", "", None, 20261001,
])
def test_everything_else_stays_as_is(text):
    assert parse_iso(text) is None


def test_serial_numbers():
    assert serial(datetime.datetime(2026, 10, 1)) == 46296
    assert serial(datetime.datetime(1900, 1, 1)) == 2
    assert serial(datetime.datetime(2026, 10, 1, 12)) == 46296.5
    # A document whose NullDate is 1904-01-01 (old Mac files)
    assert serial(datetime.datetime(1904, 1, 2), (1904, 1, 1)) == 1


def test_apostrophe_keeps_text():
    assert literal_text("'2026-10-01") == "2026-10-01"
    assert literal_text("2026-10-01") is None
    assert literal_text("'") is None


def test_column_ranges():
    from plugin.modules.calc.tools.columns import parse_columns
    assert parse_columns("B") == (1, 1)
    assert parse_columns("c:a") == (0, 2)
    assert parse_columns("AA:AB") == (26, 27)
    with pytest.raises(ValueError, match="look like"):
        parse_columns("A1:C3")
