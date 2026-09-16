# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""How much exported content text_get_range may return (#2628, #39).

Reading Moby Dick returned 1.36 MB of HTML in one result: max_chars had no
default and writer.max_content_chars was never read. No UNO here.
"""

# The setting's own upper bound (module.yaml): an explicit max_chars above it
# is lowered to it, so no call can return an unbounded result.
HARD_MAX = 500000
MARKER = "\n\n[... truncated ...]"


def effective_limit(requested, configured):
    """The character limit for a call: *requested* if given, else the
    setting; never above HARD_MAX."""
    for value in (requested, configured):
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return min(value, HARD_MAX)
    return 50000


def cut(content, limit):
    """Return (content, truncated), cut at or before *limit* on a clean
    boundary: never inside a tag, preferably at a line end."""
    if len(content) <= limit:
        return content, False
    head = content[:limit]
    # Never leave an unclosed tag at the end.
    lt, gt = head.rfind("<"), head.rfind(">")
    if lt > gt:
        head = head[:lt]
    newline = head.rfind("\n")
    if newline >= len(head) // 2:
        head = head[:newline]
    return head.rstrip() + MARKER, True
