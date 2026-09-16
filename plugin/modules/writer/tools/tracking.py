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


class ListTrackedChanges(ToolBase):
    """List tracked changes (redlines) for review."""

    name = "change_list"
    aliases = ["get_tracked_changes"]
    intent = "review"
    description = (
        "List tracked changes (redlines) so they can be reviewed: each with "
        "its type, author, date, comment, the text inserted or deleted "
        "(first 200 characters, plus its length) and the paragraph it is "
        "in. A summary by type and by author covers every change; the list "
        "is paged (offset, limit, default 100) and can be filtered by author "
        "or type. Writer only: the Calc change track has no UNO API, and the "
        "Calc accept/reject commands open a dialog instead of running "
        "headless, so spreadsheet revisions cannot be listed or cleared "
        "through MCP."
    )
    parameters = {
        "type": "object",
        "properties": {
            "author": {"type": "string",
                       "description": "Only changes by this author."},
            "type": {"type": "string",
                     "description": "Only this type, e.g. Insert, Delete, "
                                    "Format."},
            "offset": {"type": "integer",
                       "description": "First change to return (default 0)."},
            "limit": {"type": "integer",
                      "description": "Changes per page (default 100, at most "
                                     "500)."},
        },
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        from plugin.modules.writer import change_review as cr

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

        redlines = []
        enum = doc.getRedlines().createEnumeration()
        while enum.hasMoreElements():
            redlines.append(enum.nextElement())
        changes = []
        for redline in redlines:
            entry = {"type": _prop(redline, "RedlineType"),
                     "author": _prop(redline, "RedlineAuthor"),
                     "comment": _prop(redline, "RedlineComment") or None,
                     "id": _prop(redline, "RedlineIdentifier")}
            dt = _prop(redline, "RedlineDateTime")
            if dt is not None:
                entry["date"] = "%04d-%02d-%02d %02d:%02d" % (
                    dt.Year, dt.Month, dt.Day, dt.Hours, dt.Minutes)
            entry["_redline"] = redline
            changes.append(entry)

        try:
            page = cr.review(changes, author=kwargs.get("author"),
                             change_type=kwargs.get("type"),
                             offset=kwargs.get("offset", 0),
                             limit=kwargs.get("limit", cr.DEFAULT_LIMIT))
        except ValueError as e:
            return {"status": "error", "code": "invalid_params",
                    "message": str(e), "retryable": False}

        # Text and paragraph only for the page returned: both cost UNO calls.
        locate = _paragraph_locator(ctx)
        for entry in page["changes"]:
            redline = entry.pop("_redline")
            start = _prop(redline, "RedlineStart")
            end = _prop(redline, "RedlineEnd")
            text = ""
            try:
                cursor = start.getText().createTextCursorByRange(start)
                cursor.gotoRange(end, True)
                text = cursor.getString()
            except Exception:
                pass
            entry["text"], entry["text_length"] = cr.clip(text)
            entry["paragraph_index"] = locate(start)
        for entry in changes:
            entry.pop("_redline", None)

        return {"status": "ok", "recording": recording,
                "count": page["summary"]["total"], **page}


def _prop(obj, name):
    try:
        return obj.getPropertyValue(name)
    except Exception:
        return None


def _paragraph_locator(ctx):
    """start range -> body paragraph index (binary search), or None for a
    change outside the body text (table cell, frame, note)."""
    from plugin.modules.writer.change_review import paragraph_of

    doc = ctx.doc
    body = doc.getText()
    ranges = ctx.services.document.get_paragraph_ranges(doc)
    starts, points = [], []
    for i, element in enumerate(ranges):
        try:
            if element.supportsService("com.sun.star.text.Paragraph"):
                points.append(element.getStart())
                starts.append(i)
        except Exception:
            continue

    def locate(point):
        if point is None:
            return None
        try:
            # compareRegionStarts(a, b) >= 0: a starts at or before b.
            return paragraph_of(
                starts,
                lambda k: body.compareRegionStarts(points[k], point) >= 0)
        except Exception:
            return None

    return locate


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
