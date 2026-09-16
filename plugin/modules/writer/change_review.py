# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Page, filter and summarise tracked changes for review (#2636).

change_list returned 664 changes in 114 KB, with type, author and date but
not what changed: an agent could count revisions, not read them. No UNO
here: the tool collects the changes and hands them over.
"""

TEXT_LIMIT = 200
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def clip(text, limit=TEXT_LIMIT):
    """(text shown, full length) — long insertions are cut, with the length
    kept so the agent knows."""
    text = text or ""
    return (text if len(text) <= limit else text[:limit] + "…"), len(text)


def review(changes, author=None, change_type=None, offset=0,
           limit=DEFAULT_LIMIT):
    """Filter *changes* (dicts with type and author), summarise all of them
    and return one page.

    Returns {summary: {total, by_type, by_author}, matched, offset,
    returned, next_offset, changes}. The summary counts every change, so
    an agent can see the whole review before paging through a filter.
    """
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be 0 or more.")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be 1 or more.")
    limit = min(limit, MAX_LIMIT)

    by_type, by_author = {}, {}
    for c in changes:
        by_type[c.get("type")] = by_type.get(c.get("type"), 0) + 1
        by_author[c.get("author")] = by_author.get(c.get("author"), 0) + 1

    def keep(c):
        if author is not None and (c.get("author") or "").casefold() \
                != author.casefold():
            return False
        if change_type is not None and (c.get("type") or "").casefold() \
                != change_type.casefold():
            return False
        return True

    matched = [c for c in changes if keep(c)]
    page = matched[offset:offset + limit]
    end = offset + len(page)
    return {
        "summary": {"total": len(changes), "by_type": by_type,
                    "by_author": by_author},
        "matched": len(matched),
        "offset": offset,
        "returned": len(page),
        "next_offset": end if end < len(matched) else None,
        "changes": page,
    }


def paragraph_of(starts, position_before):
    """Index into *starts* of the last paragraph starting at or before a
    point, by binary search. *position_before(i)* is True when paragraph i
    starts at or before the point."""
    lo, hi, found = 0, len(starts) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if position_before(mid):
            found = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return None if found is None else starts[found]
