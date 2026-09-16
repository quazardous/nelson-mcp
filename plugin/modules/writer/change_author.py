# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sign the agent's tracked changes with a name of its own (#2636).

Writer signs a tracked change with the user's full name
(SwModule::GetRedlineAuthor, from Tools > Options > User Data), so an
agent's edits look like the user's. No UNO property sets the author per
document. What does work: Writer drops its cached author whenever the user
profile changes, so Nelson puts ``writer.change_author`` in the profile
for the length of a mutating call and puts the user's name back after.
The call runs on the main thread, so nothing the user types can land in
between.

The original values are written to ``writer.change_author_restore``
before the swap, so a crash in the middle of a call is repaired at the
next start instead of leaving the agent's name as the user's.
"""

import contextlib
import json
import logging

log = logging.getLogger("nelson.writer")

PROFILE_PATH = "/org.openoffice.UserProfile/Data"
# Every key SvtUserOptions builds the full name from, whatever the UI
# language's name order.
NAME_KEYS = ("givenname", "sn", "fathersname")
UNKNOWN_AUTHOR = "Unknown Author"


def plan_swap(current, name):
    """Return (changes, original): the profile keys to write so the full
    name reads *name*, and their values to restore afterwards. Keys that
    already hold the right value are left alone, so nothing is written
    that does not need to be."""
    target = {key: "" for key in NAME_KEYS}
    target["givenname"] = name
    changes = {k: v for k, v in target.items() if current.get(k, "") != v}
    original = {k: current.get(k, "") for k in changes}
    return changes, original


def full_name(values):
    """The name Writer signs with, from the profile values (the common
    given-name-first order; enough to tell the user an empty profile)."""
    parts = [str(values.get(k) or "").strip() for k in ("givenname", "sn")]
    return " ".join(p for p in parts if p)


class ChangeAuthor:
    """The ``change_author`` service."""

    def __init__(self, config, uno_ctx=None):
        self._config = config
        self._uno_ctx = uno_ctx

    # -- profile access ----------------------------------------------

    def _profile(self):
        import uno
        from com.sun.star.beans import PropertyValue
        ctx = self._uno_ctx or uno.getComponentContext()
        provider = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.configuration.ConfigurationProvider", ctx)
        arg = PropertyValue()
        arg.Name, arg.Value = "nodepath", PROFILE_PATH
        return provider.createInstanceWithArguments(
            "com.sun.star.configuration.ConfigurationUpdateAccess", (arg,))

    @staticmethod
    def _write(data, values):
        for key, value in values.items():
            data.setPropertyValue(key, value)
        data.commitChanges()

    def _setting(self):
        try:
            value = self._config.get("writer.change_author",
                                     caller_module="writer")
            return str(value or "").strip()
        except Exception:
            return ""

    # -- API ---------------------------------------------------------

    def signing_name(self):
        """Who signs the agent's tracked changes: the configured name,
        else the user's, else LibreOffice's "Unknown Author"."""
        name = self._setting()
        if name:
            return name
        try:
            data = self._profile()
            name = full_name({k: data.getPropertyValue(k) for k in NAME_KEYS})
        except Exception:
            name = ""
        return name or UNKNOWN_AUTHOR

    @contextlib.contextmanager
    def signing(self, doc):
        """Around a mutating call: sign tracked changes with the configured
        name when one is set and *doc* records changes."""
        name = self._setting()
        if not name or not _records_changes(doc):
            yield None
            return
        try:
            data = self._profile()
            current = {k: data.getPropertyValue(k) for k in NAME_KEYS}
            changes, original = plan_swap(current, name)
            if changes:
                self._config.set("writer.change_author_restore",
                                 json.dumps(original), caller_module="writer")
                self._write(data, changes)
        except Exception:
            log.warning("Could not sign changes as %r", name, exc_info=True)
            yield None
            return
        try:
            yield name
        finally:
            if changes:
                try:
                    self._write(data, original)
                    self._config.set("writer.change_author_restore", "",
                                     caller_module="writer")
                except Exception:
                    log.exception("Could not restore the user's name after "
                                  "signing changes as %r", name)

    def recover(self):
        """Put the user's name back if a call died with the agent's in the
        profile. Main thread, at start."""
        try:
            pending = self._config.get("writer.change_author_restore",
                                       caller_module="writer")
        except Exception:
            return False
        if not pending:
            return False
        try:
            original = json.loads(pending)
            self._write(self._profile(), {k: v for k, v in original.items()
                                          if k in NAME_KEYS})
            self._config.set("writer.change_author_restore", "",
                             caller_module="writer")
            log.warning("Restored the user's name in the LibreOffice profile "
                        "after an interrupted call (writer.change_author)")
            return True
        except Exception:
            log.exception("Could not restore the user's name from "
                          "writer.change_author_restore")
            return False


def _records_changes(doc):
    try:
        return (doc is not None
                and doc.supportsService("com.sun.star.text.TextDocument")
                and bool(doc.getPropertyValue("RecordChanges")))
    except Exception:
        return False
