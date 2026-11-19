# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer tables read by cell name, not by column count (GitHub #45)."""

from plugin.modules.writer.tools.tables import group_cell_names


def test_a_regular_table_is_a_grid():
    assert group_cell_names(["A1", "B1", "A2", "B2"]) == [
        ["A1", "B1"], ["A2", "B2"]]


def test_a_merged_first_row_keeps_the_other_columns():
    # The table of issue #45: getColumns() counted 1, B2 and B3 were lost.
    assert group_cell_names(["A1", "A2", "B2", "A3", "B3"]) == [
        ["A1"], ["A2", "B2"], ["A3", "B3"]]


def test_columns_past_z_and_rows_past_9():
    # Writer names column 27 'a', not 'AA'.
    names = ["Y10", "Z10", "a10", "b10", "AA10"]
    assert group_cell_names(names) == [names]
    assert group_cell_names(["A9", "A10", "A11"]) == [
        ["A9"], ["A10"], ["A11"]]


def test_split_cells_stay_in_their_row():
    assert group_cell_names(["A1", "B1.1.1", "B1.1.2", "A2", "B2"]) == [
        ["A1", "B1.1.1", "B1.1.2"], ["A2", "B2"]]
