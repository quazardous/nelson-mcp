# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Filter, sort and aggregate a table without writing to the sheet (#2630).

"Top 10 emitters in 2022" on a 50 000-row sheet used to mean reading
megabytes, sorting the user's table in place, or knowing AGGREGATE. The
calc_query tool reads the needed columns in bulk and hands them here; this
module is plain Python over lists, so it is tested without LibreOffice.
"""

import re

OPS = ("=", "!=", ">", ">=", "<", "<=", "contains", "in", "empty",
       "not_empty")
AGGREGATES = ("sum", "avg", "min", "max", "count")
MAX_LIMIT = 1000
_LETTERS = re.compile(r"^[A-Za-z]{1,3}$")


class QueryError(ValueError):
    """A query that cannot run, with a reason the agent can act on."""


def column_letter_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def resolve_column(headers, ref):
    """Index of *ref* in *headers*: a header name (case-insensitive), else a
    column letter relative to the table's first column."""
    if isinstance(ref, int) and not isinstance(ref, bool):
        if 0 <= ref < len(headers):
            return ref
        raise QueryError("Column index %d out of range." % ref)
    if not isinstance(ref, str) or not ref.strip():
        raise QueryError("A column must be a header name or a letter.")
    wanted = ref.strip().casefold()
    for i, h in enumerate(headers):
        if str(h).strip().casefold() == wanted:
            return i
    if _LETTERS.match(ref.strip()):
        i = column_letter_index(ref.strip())
        if 0 <= i < len(headers):
            return i
    raise QueryError("No column %r. Headers: %s"
                     % (ref, ", ".join(str(h) for h in headers)))


def _is_empty(v):
    return v is None or (isinstance(v, str) and v == "")


def _number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _matches(cell, op, value):
    if op == "empty":
        return _is_empty(cell)
    if op == "not_empty":
        return not _is_empty(cell)
    if _is_empty(cell):
        return False
    if op == "in":
        if not isinstance(value, (list, tuple)):
            raise QueryError("'in' needs a list of values.")
        return any(_matches(cell, "=", v) for v in value)
    if op == "contains":
        return str(value).casefold() in str(cell).casefold()
    a, b = _number(cell), _number(value)
    if a is not None and b is not None:
        left, right = a, b
    else:
        left, right = str(cell).casefold(), str(value).casefold()
    if op == "=":
        return left == right
    if op == "!=":
        return left != right
    try:
        return {">": left > right, ">=": left >= right,
                "<": left < right, "<=": left <= right}[op]
    except TypeError:
        return False


def _sort_key(v):
    n = _number(v)
    if _is_empty(v):
        return (2, 0, "")
    if n is not None:
        return (0, n, "")
    return (1, 0, str(v).casefold())


def run_query(headers, rows, where=None, select=None, order_by=None,
              limit=50, group_by=None, aggregate=None):
    """Apply the query; returns {columns, rows, matched, returned,
    truncated}. *rows* are lists aligned with *headers*."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise QueryError("limit must be a positive integer.")
    limit = min(limit, MAX_LIMIT)

    conditions = []
    for cond in where or []:
        if not isinstance(cond, dict) or "column" not in cond:
            raise QueryError("Each where item needs column and op.")
        op = cond.get("op", "=")
        if op not in OPS:
            raise QueryError("Unknown op %r. Allowed: %s"
                             % (op, ", ".join(OPS)))
        conditions.append((resolve_column(headers, cond["column"]), op,
                           cond.get("value")))
    kept = [r for r in rows
            if all(_matches(r[i] if i < len(r) else None, op, v)
                   for i, op, v in conditions)]

    specs = _order_specs(order_by)
    if group_by or aggregate:
        columns, out = _group(headers, kept, group_by or [], aggregate or [])
        out = _sorted(out, columns, specs)
    else:
        # Sort on the full rows: ordering by a column not selected is fine.
        out = _sorted(kept, headers, specs)
        idx = ([resolve_column(headers, c) for c in select] if select
               else list(range(len(headers))))
        columns = [headers[i] for i in idx]
        out = [[r[i] if i < len(r) else None for i in idx] for r in out]

    matched = len(out)
    return {"columns": columns, "rows": out[:limit], "matched": matched,
            "returned": min(matched, limit), "truncated": matched > limit}


def _sorted(rows, columns, specs):
    out = list(rows)
    for col, desc in reversed(specs):
        pos = resolve_column(columns, col)
        empties = [r for r in out
                   if pos >= len(r) or _is_empty(r[pos])]
        filled = [r for r in out
                  if pos < len(r) and not _is_empty(r[pos])]
        filled.sort(key=lambda r: _sort_key(r[pos]), reverse=desc)
        out = filled + empties              # empties last either way
    return out


def _order_specs(order_by):
    if not order_by:
        return []
    items = order_by if isinstance(order_by, list) else [order_by]
    specs = []
    for item in items:
        if isinstance(item, str):
            parts = item.strip().rsplit(" ", 1)
            if len(parts) == 2 and parts[1].lower() in ("asc", "desc"):
                specs.append((parts[0], parts[1].lower() == "desc"))
            else:
                specs.append((item.strip(), False))
        elif isinstance(item, dict) and "column" in item:
            specs.append((item["column"], bool(item.get("desc"))))
        else:
            raise QueryError("order_by items are 'column [asc|desc]' or "
                             "{column, desc}.")
    return specs


def _group(headers, rows, group_by, aggregate):
    keys = [resolve_column(headers, c) for c in group_by]
    aggs = []
    for a in aggregate:
        if not isinstance(a, dict) or a.get("fn") not in AGGREGATES:
            raise QueryError("aggregate items are {column, fn} with fn in %s"
                             % ", ".join(AGGREGATES))
        col = a.get("column")
        idx = resolve_column(headers, col) if col is not None else None
        if idx is None and a["fn"] != "count":
            raise QueryError("%s needs a column." % a["fn"])
        name = a.get("as") or ("%s(%s)" % (a["fn"], headers[idx])
                               if idx is not None else "count")
        aggs.append((a["fn"], idx, name))
    groups = {}
    for r in rows:
        key = tuple(r[i] if i < len(r) else None for i in keys)
        groups.setdefault(key, []).append(r)
    out = []
    for key, members in groups.items():
        row = list(key)
        for fn, idx, _ in aggs:
            nums = ([] if idx is None else
                    [n for n in (_number(m[idx]) for m in members)
                     if n is not None])
            if fn == "count":
                row.append(len(members) if idx is None else
                           sum(1 for m in members if not _is_empty(m[idx])))
            elif not nums:
                row.append(None)
            elif fn == "sum":
                row.append(sum(nums))
            elif fn == "avg":
                row.append(sum(nums) / len(nums))
            elif fn == "min":
                row.append(min(nums))
            else:
                row.append(max(nums))
        out.append(row)
    return [headers[i] for i in keys] + [a[2] for a in aggs], out
