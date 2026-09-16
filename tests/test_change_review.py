# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""change_list review helpers (#2636)."""

import pytest

from plugin.modules.writer.change_review import clip, paragraph_of, review

CHANGES = ([{"type": "Insert", "author": "Agent", "i": i} for i in range(5)]
           + [{"type": "Delete", "author": "Agent", "i": i} for i in range(5)]
           + [{"type": "Insert", "author": "Ana", "i": 99}])


def test_summary_counts_everything_and_page_follows_filter():
    res = review(CHANGES, change_type="insert", limit=4)
    assert res["summary"] == {"total": 11,
                              "by_type": {"Insert": 6, "Delete": 5},
                              "by_author": {"Agent": 10, "Ana": 1}}
    assert res["matched"] == 6 and res["returned"] == 4
    assert res["next_offset"] == 4
    last = review(CHANGES, change_type="insert", offset=4, limit=4)
    assert last["returned"] == 2 and last["next_offset"] is None


def test_author_filter_is_case_insensitive():
    assert review(CHANGES, author="ana")["matched"] == 1


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"limit": 0}])
def test_bad_paging_is_refused(kwargs):
    with pytest.raises(ValueError):
        review(CHANGES, **kwargs)


def test_limit_is_capped():
    assert review(CHANGES * 100, limit=10000)["returned"] == 500


def test_clip_keeps_the_length():
    assert clip("short") == ("short", 5)
    shown, length = clip("x" * 250)
    assert length == 250 and shown.endswith("…") and len(shown) == 201


def test_paragraph_by_binary_search():
    starts = [0, 2, 5, 9]          # paragraph indexes (3, 4, 6... skipped)
    positions = [0, 10, 20, 30]     # where each starts
    for point, expected in [(0, 0), (15, 2), (25, 5), (99, 9)]:
        assert paragraph_of(starts, lambda i: positions[i] <= point) \
            == expected
    assert paragraph_of(starts, lambda i: False) is None
