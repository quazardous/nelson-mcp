# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer track-changes tools."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")


class SetTrackChanges(ToolBase):
    """Enable or disable change tracking."""

    name = "change_set"
    aliases = ["set_track_changes"]
    intent = "review"
    description = (
        "Enable or disable change recording (track changes). Works on "
        "Writer and Calc. Disabling can be refused: when the option "
        "'Prevent MCP from disabling change recording' is on, the "
        "recording is treated as an audit trail an agent may not switch "
        "off - turn it off in LibreOffice, or clear that option."
    )
    parameters = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "True to enable track changes, False to disable.",
            },
        },
        "required": ["enabled"],
    }
    # Calc keeps superseded cell values in xl/revisions/, so a spreadsheet
    # needs the off switch just as much as a Writer file (#22).
    doc_types = ["writer", "calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        enabled = kwargs.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() not in ("false", "0", "no")
        enabled = bool(enabled)

        if not enabled and ctx.caller == "mcp" and self._locked(ctx):
            return {
                "status": "error",
                "code": "track_changes_locked",
                "message": ("Change recording is on and MCP calls are not "
                            "allowed to turn it off."),
                "hint": ("This guards the audit trail against the agent "
                         "disabling it. Turn recording off in LibreOffice "
                         "(Edit > Track Changes > Record), or clear "
                         "'Prevent MCP from disabling change recording' in "
                         "Nelson options."),
                "retryable": False,
            }

        ctx.doc.setPropertyValue("RecordChanges", enabled)
        return {"status": "ok", "record_changes": enabled}

    def _locked(self, ctx):
        """True when recording is on and the option forbids turning it off."""
        try:
            if not ctx.doc.getPropertyValue("RecordChanges"):
                return False  # already off - nothing to protect
            cfg = ctx.services.get("config")
            if cfg is None:
                return False
            return bool(cfg.proxy_for("core").get("force_track_changes"))
        except Exception:
            return False


class GetTrackedChanges(ToolBase):
    """List all tracked changes (redlines) in the document."""

    name = "change_list"
    aliases = ["get_tracked_changes"]
    intent = "review"
    description = (
        "List all tracked changes (redlines) in the document, "
        "including type, author, date, and comment. "
        "Writer only: the Calc change track has no UNO API, and the "
        "Calc accept/reject commands open a dialog instead of running "
        "headless, so spreadsheet revisions cannot be listed or "
        "cleared through MCP."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        recording = False
        try:
            recording = doc.getPropertyValue("RecordChanges")
        except Exception:
            pass

        if not hasattr(doc, "getRedlines"):
            return {
                "status": "ok",
                "recording": recording,
                "changes": [],
                "count": 0,
                "message": "Document does not expose redlines API.",
            }

        redlines = doc.getRedlines()
        enum = redlines.createEnumeration()
        changes = []
        while enum.hasMoreElements():
            redline = enum.nextElement()
            entry = {}
            for prop in (
                "RedlineType", "RedlineAuthor",
                "RedlineComment", "RedlineIdentifier",
            ):
                try:
                    entry[prop] = redline.getPropertyValue(prop)
                except Exception:
                    pass
            try:
                dt = redline.getPropertyValue("RedlineDateTime")
                entry["date"] = "%04d-%02d-%02d %02d:%02d" % (
                    dt.Year, dt.Month, dt.Day, dt.Hours, dt.Minutes
                )
            except Exception:
                pass
            changes.append(entry)

        return {
            "status": "ok",
            "recording": recording,
            "changes": changes,
            "count": len(changes),
        }


class AcceptAllChanges(ToolBase):
    """Accept all tracked changes in the document."""

    name = "change_accept_all"
    aliases = ["accept_all_changes"]
    intent = "review"
    description = (
        "Accept all tracked changes in the document. "
        "Writer only: the Calc change track has no UNO API, and the "
        "Calc accept/reject commands open a dialog instead of running "
        "headless, so spreadsheet revisions cannot be listed or "
        "cleared through MCP."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        # UNO dispatcher is the reliable way to accept all redlines.
        smgr = ctx.ctx.ServiceManager
        dispatcher = smgr.createInstanceWithContext(
            "com.sun.star.frame.DispatchHelper", ctx.ctx
        )
        frame = ctx.doc.getCurrentController().getFrame()
        dispatcher.executeDispatch(
            frame, ".uno:AcceptAllTrackedChanges", "", 0, ()
        )
        return {"status": "ok", "message": "All tracked changes accepted."}


class RejectAllChanges(ToolBase):
    """Reject all tracked changes in the document."""

    name = "change_reject_all"
    aliases = ["reject_all_changes"]
    intent = "review"
    description = (
        "Reject all tracked changes in the document. "
        "Writer only: the Calc change track has no UNO API, and the "
        "Calc accept/reject commands open a dialog instead of running "
        "headless, so spreadsheet revisions cannot be listed or "
        "cleared through MCP."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        smgr = ctx.ctx.ServiceManager
        dispatcher = smgr.createInstanceWithContext(
            "com.sun.star.frame.DispatchHelper", ctx.ctx
        )
        frame = ctx.doc.getCurrentController().getFrame()
        dispatcher.executeDispatch(
            frame, ".uno:RejectAllTrackedChanges", "", 0, ()
        )
        return {"status": "ok", "message": "All tracked changes rejected."}
