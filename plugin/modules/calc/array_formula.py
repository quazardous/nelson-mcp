# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Which formulas return an array, and where their result goes (#2631).

LibreOffice does not spill: =SORT(FILTER(...)) written into one cell with
setFormula shows a single value, the rest of the result silently gone. It
has to be entered as an array formula on a range of the right size. No UNO
here: the tool measures the size and writes.
"""

import re

# Functions whose result is an array when they are what the formula returns.
ARRAY_FUNCTIONS = frozenset({
    "FILTER", "SORT", "SORTBY", "UNIQUE", "SEQUENCE", "RANDARRAY",
    "TRANSPOSE", "MMULT", "MINVERSE", "FREQUENCY", "CHOOSECOLS",
    "CHOOSEROWS", "HSTACK", "VSTACK", "TAKE", "DROP", "EXPAND", "WRAPROWS",
    "WRAPCOLS", "TOCOL", "TOROW",
})

MAX_CELLS = 100000

_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")


def top_level_calls(formula):
    """Names of the functions called at the outermost level of *formula*.

    ``=SUM(FILTER(A1:A9;B1:B9>0))`` -> ``["SUM"]``: FILTER's array is
    consumed by SUM, so the formula as a whole returns one value.
    """
    text = formula[1:] if formula.startswith("=") else formula
    names, depth, i, in_string = [], 0, 0, False
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0:
                match = _CALL.match(text, i)
                if match and (i == 0 or not (text[i - 1].isalnum()
                                             or text[i - 1] in "_.")):
                    names.append(match.group(1).upper())
                    i = match.end() - 1
                    continue
        i += 1
    return names


def returns_array(formula, forced=None):
    """True when *formula* should be entered as an array formula.

    *forced* (the tool's ``array`` argument) wins when given. Otherwise a
    formula is an array formula when a function it calls at the top level
    returns an array. LET, XLOOKUP and plain range arithmetic can go either
    way: callers pass array=true for those.
    """
    if forced is not None:
        return bool(forced)
    if not isinstance(formula, str) or not formula.startswith("="):
        return False
    return any(name in ARRAY_FUNCTIONS for name in top_level_calls(formula))


def result_range(col, row, rows, cols):
    """(first_col, first_row, last_col, last_row) of a result anchored at
    (*col*, *row*), 0-based."""
    return col, row, col + cols - 1, row + rows - 1
