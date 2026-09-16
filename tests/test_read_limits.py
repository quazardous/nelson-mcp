# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Capped reads: text_get_range and calc_read_range (#2628, GH #39)."""

from plugin.modules.calc.read_limit import plan_reads
from plugin.modules.writer import content_limit as cl


def test_limit_prefers_the_call_then_the_setting_and_is_capped():
    assert cl.effective_limit(None, 50000) == 50000
    assert cl.effective_limit(70000, 50000) == 70000
    assert cl.effective_limit(10**9, 50000) == cl.HARD_MAX
    assert cl.effective_limit(None, None) == 50000
    assert cl.effective_limit(0, "bad") == 50000


def test_short_content_is_untouched():
    assert cl.cut("<p>hi</p>", 100) == ("<p>hi</p>", False)


def test_cut_never_leaves_a_broken_tag_and_prefers_line_ends():
    content = "<p>one</p>\n<p>two</p>\n<p class=\"x\">three</p>"
    head, truncated = cl.cut(content, len(content) - 12)
    assert truncated and head.endswith(cl.MARKER)
    body = head[:-len(cl.MARKER)]
    assert body == "<p>one</p>\n<p>two</p>"
    assert body.count("<") == body.count(">")


def test_cut_inside_an_opening_tag_backs_off():
    content = "x" * 50 + "<span class=\"long attribute\">y</span>"
    head, _ = cl.cut(content, 60)
    assert "<span" not in head


def test_single_range_within_limits_is_read_whole():
    plan = plan_reads(["A1:D10"], max_rows=1000)
    assert plan["reads"] == [("A1:D10", "A1:D10")]
    assert not plan["truncated"] and plan["rows_returned"] == 10


def test_rows_limit_gives_the_exact_next_range():
    plan = plan_reads(["'Data Sheet'.B1:C1500"], max_rows=1000)
    assert plan["reads"][0][0] == "'Data Sheet'.B1:C1000"
    assert plan["next_range"] == "'Data Sheet'.B1001:C1500"
    assert (plan["rows_total"], plan["rows_returned"]) == (1500, 1000)


def test_cell_budget_caps_wide_ranges():
    plan = plan_reads(["A1:CA2000"], max_rows=1000, max_cells=20000)
    # CA is 79 columns: 20000 // 79 = 253 rows
    assert plan["reads"][0][0] == "A1:CA253"
    assert plan["next_range"] == "A254:CA2000"


def test_budget_spans_several_ranges():
    plan = plan_reads(["A1:A600", "B1:B600", "C1:C10"], max_rows=1000)
    assert [r for r, _ in plan["reads"]] == ["A1:A600", "B1:B400"]
    assert plan["next_range"] == "B401:B600"
    assert plan["unread"] == ["C1:C10"]
    assert plan["rows_total"] == 1210


def test_single_cell_reads_as_itself():
    plan = plan_reads(["Summary.B2"], max_rows=1000)
    assert plan["reads"] == [("Summary.B2", "Summary.B2")]
