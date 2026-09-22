# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What to tell an agent when LibreOffice asked a question while loading.

With no interaction handler, a question LibreOffice asks during a load (the
file is locked, it needs a password, it is damaged) opened a modal dialog
nobody could answer: doc_open waited for the 60 s timeout and ended in a
504, and every call after it queued behind the dialog. doc_open now refuses
every such question and reports it with ``describe()``. Nothing here needs
UNO, so it is unit-tested directly.
"""

import os

_PASSWORD = ("DocumentPasswordRequest", "DocumentPasswordRequest2",
             "DocumentMSPasswordRequest", "DocumentMSPasswordRequest2",
             "PasswordRequest")


def lock_owner(path):
    """Who LibreOffice's lock file next to *path* names, or None.

    The file is ``.~lock.<name>#`` and holds one line:
    ``Full Name,host,user,DD.MM.YYYY HH:MM,profile-url;``.
    """
    lock = os.path.join(os.path.dirname(path),
                        ".~lock.%s#" % os.path.basename(path))
    try:
        with open(lock, encoding="utf-8", errors="replace") as f:
            fields = f.read().strip().rstrip(";").split(",")
    except OSError:
        return None
    if len(fields) < 4:
        return {"lock_file": lock}
    name, host, user, since = (f.strip() for f in fields[:4])
    return {"name": name or user, "host": host, "user": user,
            "since": since, "lock_file": lock}


_ZIP_FORMATS = (".odt", ".ods", ".odp", ".odg", ".docx", ".xlsx", ".pptx",
                ".ott", ".ots", ".otp")


def infer_kind(path):
    """What LibreOffice most likely asked about, from the file alone, for
    when the request itself could not be read (pyuno on Python 3.14): a
    lock file next to it, or a zip-based document that is not a zip."""
    if not path:
        return "unknown"
    if lock_owner(path) is not None:
        return "LockedDocumentRequest"
    if path.lower().endswith(_ZIP_FORMATS):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is None:
                    return "unknown"
        except Exception:
            pass
        return "BrokenPackageRequest"
    return "unknown"


def describe(kind, info=None, path=None):
    """The error doc_open returns for a load that stopped on *kind*, the
    UNO name of the request LibreOffice raised (``LockedDocumentRequest``…).
    *info* carries the request's own text (UserInfo, TimeInfo)."""
    if kind in ("LockedDocumentRequest", "OwnLockOnDocumentRequest",
                "LockFileCorruptRequest"):
        owner = lock_owner(path) if path else None
        if kind == "OwnLockOnDocumentRequest":
            who = ("you, in another LibreOffice session or one that "
                   "crashed")
        elif kind == "LockFileCorruptRequest":
            who = "an unreadable lock file"
        elif owner and owner.get("name"):
            who = "%s on %s" % (owner["name"], owner.get("host") or "?")
        else:
            who = info or "someone else"
        result = {
            "status": "error", "code": "document_locked",
            "message": "The document is locked by %s%s." % (
                who, " since %s" % owner["since"]
                if owner and owner.get("since") else ""),
            "hint": ("Close it where it is open, or open it with "
                     "read_only: true to read it without taking the lock. "
                     "If the lock was left by a crash, only the user can "
                     "tell: Nelson never removes a lock file."),
            "retryable": False,
        }
        if owner:
            result["locked_by"] = owner
        return result
    if kind in _PASSWORD:
        return {"status": "error", "code": "password_required",
                "message": "The document is protected by a password.",
                "hint": ("Nelson cannot supply passwords. Ask the user to "
                         "open it in LibreOffice; it can then be addressed "
                         "with doc_list_open."),
                "retryable": False}
    if kind == "BrokenPackageRequest":
        return {"status": "error", "code": "document_damaged",
                "message": "The file is damaged; LibreOffice offered to "
                           "repair it.",
                "hint": ("Ask the user to open it in LibreOffice and "
                         "accept or refuse the repair."),
                "retryable": False}
    return {"status": "error", "code": "interaction_required",
            "message": "LibreOffice asked a question while loading the "
                       "document (%s) and Nelson refused it." % kind,
            "hint": "Ask the user to open the document in LibreOffice.",
            "retryable": False}
