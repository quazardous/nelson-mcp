# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""How much of a set of ranges calc_read_range may return (#2628, #39).

A read of A1:CA2000 came back as 13 MB, and the whole sheet would have been
hundreds: nothing capped it, and calc.max_rows_display was never read.
plan_reads() splits the requested ranges within a row limit and a cell
budget, and says exactly which range to read next. No UNO here.
"""

from plugin.modules.calc.address_utils import (
    index_to_column,
    parse_range_string,
    split_sheet_prefix,
)

# The row limit alone is not enough: 1000 rows of a 79-column sheet is still
# ~7 MB in calc_read_range's per-cell format.
MAX_CELLS = 20000


def _address(prefix, c1, r1, c2, r2):
    ref = "%s%d" % (index_to_column(c1), r1 + 1)
    if (c1, r1) != (c2, r2):
        ref += ":%s%d" % (index_to_column(c2), r2 + 1)
    return ("'%s'.%s" % (prefix, ref)) if prefix is not None else ref


def plan_reads(ranges, max_rows, max_cells=MAX_CELLS):
    """Decide what to read from *ranges* (list of references).

    Returns a dict:
        reads:       [(reference to read, original reference)] in order
        truncated:   True if anything was left out
        rows_total, rows_returned
        next_range:  the reference to read next, or None
        unread:      references not started at all

    Invalid references raise ValueError, as reading them would.
    """
    rows_left, cells_left = max_rows, max_cells
    plan = {"reads": [], "truncated": False, "rows_total": 0,
            "rows_returned": 0, "next_range": None, "unread": []}
    for ref in ranges:
        prefix, address = split_sheet_prefix(ref)
        (c1, r1), (c2, r2) = parse_range_string(address)
        c1, c2 = min(c1, c2), max(c1, c2)
        r1, r2 = min(r1, r2), max(r1, r2)
        rows, cols = r2 - r1 + 1, c2 - c1 + 1
        plan["rows_total"] += rows
        if plan["truncated"]:
            plan["unread"].append(ref)
            continue
        fit = min(rows, rows_left, cells_left // cols)
        if fit <= 0:
            plan["truncated"] = True
            plan["next_range"] = ref
            continue
        if fit == rows:
            plan["reads"].append((ref, ref))
        else:
            plan["reads"].append((_address(prefix, c1, r1, c2, r1 + fit - 1),
                                  ref))
            plan["truncated"] = True
            plan["next_range"] = _address(prefix, c1, r1 + fit, c2, r2)
        plan["rows_returned"] += fit
        rows_left -= fit
        cells_left -= fit * cols
    return plan
