# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ISO dates written to Calc become dates, and only ISO dates (#2632).

"2026-10-01" was stored as text: the column neither sorts nor formats as
dates. Calc's own input recognition would fix that but depends on the
locale and also turns "1-2" into a date or strips the zeros of "00123", so
only the unambiguous ISO forms are converted. No UNO here.
"""

import datetime
import re

_ISO = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$")

DATE_FORMAT = "YYYY-MM-DD"
DATETIME_FORMAT = "YYYY-MM-DD HH:MM"


def parse_iso(text):
    """(datetime, has_time) for an ISO date or date-time string, else None.

    The whole string must match and the date must exist: "2026-02-30" is
    left as text.
    """
    if not isinstance(text, str):
        return None
    m = _ISO.match(text.strip())
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()
    try:
        value = datetime.datetime(int(y), int(mo), int(d), int(h or 0),
                                  int(mi or 0), int(s or 0))
    except ValueError:
        return None
    return value, h is not None


def serial(value, null_date=(1899, 12, 30)):
    """Calc serial number of *value*, counted from the document's NullDate."""
    origin = datetime.datetime(*null_date)
    delta = value - origin
    return delta.days + delta.seconds / 86400.0


def literal_text(text):
    """The text to store for a leading-apostrophe string, as Calc does:
    "'2026-10-01" keeps the characters and stays text. None otherwise."""
    if isinstance(text, str) and text.startswith("'") and len(text) > 1:
        return text[1:]
    return None
