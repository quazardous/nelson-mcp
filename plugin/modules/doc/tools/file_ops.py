# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""File operation tools: save, export, lifecycle, metadata."""

import logging
import os

import uno
from com.sun.star.beans import PropertyValue

from plugin.framework.tool_base import ToolBase
from plugin.framework.uno_context import get_ctx

log = logging.getLogger("nelson.common")

_PDF_FILTERS = {
    "writer": "writer_pdf_Export",
    "calc": "calc_pdf_Export",
    "draw": "draw_pdf_Export",
    "impress": "impress_pdf_Export",
}

_EXT_FILTERS = {
    ".odt": "writer8",
    ".docx": "MS Word 2007 XML",
    ".ods": "calc8",
    ".xlsx": "Calc MS Excel 2007 XML",
    ".odp": "impress8",
    ".pptx": "Impress MS PowerPoint 2007 XML",
}


def _save_to_path(doc, path):
    """Save a document to a filesystem path.

    Handles path normalization, directory creation, filter detection,
    and Overwrite flag.  Returns (file_url, error_dict_or_None).
    """
    # Normalize path: resolve ~, make absolute, fix separators
    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    # Ensure parent directory exists
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            return None, {
                "status": "error",
                "code": "invalid_path",
                "message": "Cannot create directory: %s (%s)" % (parent, exc),
                "retryable": False,
            }

    # Detect filter from extension
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    filter_name = _EXT_FILTERS.get(ext)
    if not filter_name:
        return None, {
            "status": "error",
            "code": "unsupported_extension",
            "message": "Unsupported extension: %s. Supported: %s"
                       % (ext, ", ".join(sorted(_EXT_FILTERS))),
            "retryable": False,
        }

    # Convert to file:// URL
    file_url = uno.systemPathToFileUrl(path)

    # Build store properties
    pv_filter = PropertyValue()
    pv_filter.Name = "FilterName"
    pv_filter.Value = filter_name

    pv_overwrite = PropertyValue()
    pv_overwrite.Name = "Overwrite"
    pv_overwrite.Value = True

    try:
        # storeAsURL (NOT storeToURL) performs a real "File > Save As": it
        # writes the file AND rebinds the model to the new location — getURL()
        # is updated, the modified flag cleared, the active filter switched.
        # storeToURL is an export/copy that leaves the model bound to its old
        # URL, so a subsequent save_document overwrote the original file (#19).
        doc.storeAsURL(file_url, (pv_filter, pv_overwrite))
    except Exception as exc:
        log.exception("storeAsURL failed for %s: %s", file_url, exc)
        return None, {
            "status": "error",
            "code": "store_failed",
            "message": "Save failed: %s" % exc,
            "hint": "Check that the path is valid and writable: %s" % path,
            "retryable": False,
        }

    return file_url, None


def _recording_state(doc):
    """Report change recording, so a saved file's audit trail is not a surprise.

    A document saved while recording is on keeps superseded content inside
    the file — `xl/revisions/` for .xlsx, `<w:del>` for .docx — which an
    agent-driven workflow may never see, because nobody opens the file.
    Reported on save and export so it is at least visible (#22).
    """
    try:
        if not doc.getPropertyValue("RecordChanges"):
            return None
    except Exception:
        return None  # document type without the property
    state = {"record_changes": True}
    try:
        state["tracked_changes"] = len(doc.getRedlines())
    except Exception:
        pass  # Calc has no UNO surface for its change track
    state["note"] = (
        "Change recording is on: this file keeps superseded content "
        "(previous cell values or deleted text) alongside the visible "
        "version."
    )
    return state


class SaveDocument(ToolBase):
    """Save the current document to its existing location."""

    name = "doc_save"
    aliases = ["save_document"]
    description = (
        "Saves the current document. If the document has never been saved, "
        "provide a 'path' to save it for the first time (e.g. "
        "C:/Users/me/doc.odt). Supported extensions: "
        + ", ".join(sorted(_EXT_FILTERS))
        + "."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path for first save of an unsaved document "
                    "(absolute path, e.g. C:/Users/me/report.odt). "
                    "Ignored if the document already has a file location."
                ),
            },
        },
        "required": [],
    }
    doc_types = None
    tier = "core"
    is_mutation = True

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        url = doc.getURL()

        if url:
            doc.store()
            result = {"status": "ok", "file_url": url}
            rec = _recording_state(doc)
            if rec:
                result["change_recording"] = rec
            return result

        # Unsaved document — need a path
        path = kwargs.get("path")
        if not path:
            save_dir = "~/Documents"
            try:
                save_dir = ctx.services.document.get_default_save_dir()
            except Exception:
                pass
            return {
                "status": "error",
                "code": "unsaved_document",
                "message": (
                    "Document has never been saved. Provide a 'path' "
                    "parameter to save it."
                ),
                "hint": (
                    "Example: path='%s/report.odt'. "
                    "Supported extensions: %s."
                    % (save_dir.replace("\\", "/"),
                       ", ".join(sorted(_EXT_FILTERS)))
                ),
                "default_save_dir": save_dir.replace("\\", "/"),
                "retryable": False,
            }

        # Save to the given path
        file_url, err = _save_to_path(doc, path)
        if err:
            return err

        result = {"status": "ok", "file_url": file_url, "first_save": True}
        rec = _recording_state(doc)
        if rec:
            result["change_recording"] = rec
        return result


class ExportPdf(ToolBase):
    """Export the current document as PDF."""

    name = "doc_export_pdf"
    aliases = ["export_pdf"]
    description = (
        "Exports the current document to a PDF file at the given path."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Output PDF file path (absolute).",
            },
        },
        "required": ["path"],
    }
    doc_types = None
    tier = "core"
    is_mutation = False

    def execute(self, ctx, **kwargs):
        path = kwargs["path"]
        doc_type = ctx.doc_type

        filter_name = _PDF_FILTERS.get(doc_type)
        if not filter_name:
            return {
                "status": "error",
                "error": "Unsupported document type for PDF export: %s"
                         % doc_type,
            }

        # Convert local path to file:// URL.
        if not path.startswith("file://"):
            url = uno.systemPathToFileUrl(path)
        else:
            url = path

        pv = PropertyValue()
        pv.Name = "FilterName"
        pv.Value = filter_name

        try:
            ctx.doc.storeToURL(url, (pv,))
        except Exception as exc:
            log.exception("PDF export failed: %s", exc)
            return {"status": "error", "error": str(exc)}

        result = {"status": "ok", "file_url": url, "filter": filter_name}
        rec = _recording_state(ctx.doc)
        if rec:
            # The PDF itself carries no revisions, but the source document
            # does — worth saying, since an export often precedes sharing.
            result["change_recording"] = rec
        return result


class SaveDocumentAs(ToolBase):
    """Save the current document to a new path (File > Save As)."""

    name = "doc_save_as"
    aliases = ["save_document_as"]
    intent = "media"
    description = (
        "Save the current document to a new path. "
        "The document adopts the new file as its location "
        "(like File > Save As, not an export)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target_path": {
                "type": "string",
                "description": "Absolute file path to save to.",
            },
        },
        "required": ["target_path"],
    }
    doc_types = None
    is_mutation = False

    def execute(self, ctx, **kwargs):
        target_path = kwargs["target_path"]
        file_url, err = _save_to_path(ctx.doc, target_path)
        if err:
            return err
        result = {"status": "ok", "file_url": file_url}
        # Still the same open document, so the same doc_id. The source file,
        # if reopened, is a different document with an id of its own (#20).
        doc_id = ctx.services.document.get_doc_id(ctx.doc)
        if doc_id:
            result["doc_id"] = doc_id
        return result


# ── Factory URLs for new documents ───────────────────────────────────

_FACTORY_URLS = {
    "writer": "private:factory/swriter",
    "calc": "private:factory/scalc",
    "impress": "private:factory/simpress",
    "draw": "private:factory/sdraw",
}


def _get_desktop():
    """Return the com.sun.star.frame.Desktop singleton."""
    ctx = get_ctx()
    smgr = ctx.ServiceManager
    return smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)


def _make_active(desktop, model):
    """Make *model* the desktop's current component before returning (#34).

    loadComponentFromURL returns as soon as the document is loaded, but its
    frame only becomes the active one once the window system gets round to
    it. Until then getCurrentComponent() still answers the previous
    component — the Start Center when this is the first document — so the
    next tool call, which resolves the active document, fails with
    no_document, or silently targets the document that was active before.

    Activating the frame is synchronous and needs no event loop, which
    matters: tools run on the main thread, so waiting or sleeping here would
    block the very loop that performs the activation. It is also what the
    `_document` path already does, which is why that path never raced.

    Returns True when the model is the current component afterwards.
    """
    try:
        frame = model.getCurrentController().getFrame()
        frame.activate()
    except Exception:
        log.debug("Could not activate the new document's frame", exc_info=True)
    try:
        current = desktop.getCurrentComponent()
    except Exception:
        return False
    if current is None:
        return False
    if current == model:
        return True
    # pyuno proxies of the same object do not always compare equal; fall
    # back on the URL, which a freshly loaded file always has.
    try:
        url = model.getURL()
        return bool(url) and current.getURL() == url
    except Exception:
        return False


class CreateDocument(ToolBase):
    """Create a new empty document in LibreOffice."""

    name = "doc_create"
    aliases = ["create_document"]
    intent = "media"
    description = (
        "Create a NEW empty document in LibreOffice. "
        "Use this only when the user wants a document that does not exist "
        "yet. To work on one that already exists, do not call this — it "
        "creates an unrelated empty document and leaves theirs untouched; "
        "use doc_list_open (already open), doc_recent (opened before) or "
        "doc_open (a path) instead. "
        "Optionally provide a 'path' to save it immediately "
        "(recommended — avoids ambiguity with multiple unsaved documents)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "doc_type": {
                "type": "string",
                "enum": ["writer", "calc", "impress", "draw"],
                "description": "Type of document to create.",
            },
            "content": {
                "type": "string",
                "description": (
                    "Optional initial text content (only for writer documents)."
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Optional file path to save the document immediately "
                    "(e.g. C:/Users/me/report.odt). "
                    "Supported extensions: "
                    + ", ".join(sorted(_EXT_FILTERS)) + ". "
                    "Tip: use doc_recent to discover valid "
                    "directory paths on this machine."
                ),
            },
        },
        "required": ["doc_type"],
    }
    doc_types = None
    is_mutation = False
    requires_doc = False

    def execute(self, ctx, **kwargs):
        doc_type = kwargs["doc_type"]
        content = kwargs.get("content")
        path = kwargs.get("path")

        factory_url = _FACTORY_URLS.get(doc_type)
        if not factory_url:
            return {
                "status": "error",
                "error": "Unknown doc_type: %s" % doc_type,
            }

        try:
            desktop = _get_desktop()
            new_doc = desktop.loadComponentFromURL(
                factory_url, "_blank", 0, ()
            )
        except Exception as exc:
            log.exception("CreateDocument failed: %s", exc)
            return {"status": "error", "error": str(exc)}

        active = _make_active(desktop, new_doc)

        # Optionally set initial content for writer documents.
        if content and doc_type == "writer":
            try:
                new_doc.getText().setString(content)
            except Exception as exc:
                log.warning("Could not set initial content: %s", exc)

        # Assign and return a stable doc_id
        doc_id = None
        try:
            doc_svc = ctx.services.document
            doc_id = doc_svc.get_doc_id(new_doc)
        except Exception:
            pass

        result = {"status": "ok", "doc_type": doc_type}
        if doc_id:
            result["doc_id"] = doc_id
        if not active:
            result["warning"] = (
                "The new document is not the active one yet. Pass "
                "_document='id:%s' to address it explicitly." % doc_id)

        # Optionally save immediately
        if path:
            file_url, save_err = _save_to_path(new_doc, path)
            if save_err:
                result["save_error"] = save_err.get("message", str(save_err))
            else:
                result["file_url"] = file_url

        return result


class OpenDocument(ToolBase):
    """Open a document file in LibreOffice."""

    name = "doc_open"
    aliases = ["open_document"]
    intent = "media"
    description = (
        "Open an existing document file in LibreOffice, by path. "
        "Check doc_list_open first: if the document is already open, it "
        "does not need opening again. Use doc_recent when the user names a "
        "document but not its path."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the document file.",
            },
        },
        "required": ["file_path"],
    }
    doc_types = None
    is_mutation = False
    requires_doc = False

    def execute(self, ctx, **kwargs):
        file_path = kwargs["file_path"]

        if not file_path.startswith("file://"):
            url = uno.systemPathToFileUrl(file_path)
        else:
            url = file_path

        try:
            desktop = _get_desktop()
            new_doc = desktop.loadComponentFromURL(url, "_blank", 0, ())
        except Exception as exc:
            log.exception("OpenDocument failed: %s", exc)
            return {"status": "error", "error": str(exc)}

        active = _make_active(desktop, new_doc)

        # Return stable doc_id
        doc_id = None
        try:
            doc_svc = ctx.services.document
            doc_id = doc_svc.get_doc_id(new_doc)
        except Exception:
            pass

        result = {"status": "ok", "file_url": url}
        if doc_id:
            result["doc_id"] = doc_id
        if not active:
            result["warning"] = (
                "The document is open but not the active one yet. Pass "
                "_document='id:%s' to address it explicitly." % doc_id)
        return result


class CloseDocument(ToolBase):
    """Close the current document."""

    name = "doc_close"
    aliases = ["close_document"]
    intent = "media"
    description = (
        "Close the current document. Use doc_save first if needed."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = None
    is_mutation = True
    # Closing destroys the document: never inside an undo context (#2651).
    opens_undo_context = False

    def execute(self, ctx, **kwargs):
        desktop = _get_desktop()
        closing_doc = ctx.doc

        # Collect other document frames before closing
        next_frame = None
        try:
            frames = desktop.getFrames()
            frame_count = frames.getCount()
            log.debug(
                "doc_close: %d frames before close", frame_count
            )
            for i in range(frame_count):
                frame = frames.getByIndex(i)
                try:
                    controller = frame.getController()
                    if controller is None:
                        log.debug("  frame %d: no controller", i)
                        continue
                    model = controller.getModel()
                    if model is None:
                        log.debug("  frame %d: no model", i)
                        continue
                    frame_title = frame.getTitle()
                    # Skip the document we're about to close. Two proxies of
                    # the same UNO object are never `is`, but always `==`.
                    try:
                        is_closing = (model == closing_doc)
                    except Exception:
                        is_closing = False
                    if is_closing:
                        log.debug("  frame %d: closing doc (%s)", i, frame_title)
                        continue
                    # Skip non-document components (Start Center, Basic IDE)
                    if not hasattr(model, "supportsService"):
                        log.debug("  frame %d: not a document (%s)", i, frame_title)
                        continue
                    is_doc = (
                        model.supportsService("com.sun.star.text.TextDocument")
                        or model.supportsService("com.sun.star.sheet.SpreadsheetDocument")
                        or model.supportsService("com.sun.star.drawing.DrawingDocument")
                        or model.supportsService("com.sun.star.presentation.PresentationDocument")
                    )
                    if is_doc:
                        log.debug("  frame %d: next doc candidate (%s)", i, frame_title)
                        next_frame = frame
                        break
                    else:
                        log.debug("  frame %d: not a supported doc (%s)", i, frame_title)
                except Exception:
                    log.debug("  frame %d: exception during inspection", i, exc_info=True)
                    continue
        except Exception:
            log.info("Could not enumerate frames for next-doc activation", exc_info=True)

        closed = _describe_document(closing_doc)
        _release_undo(closing_doc)

        # Close the document
        try:
            closing_doc.close(False)
        except Exception as exc:
            # A CloseVetoException stringifies to "": say what happened.
            reason = str(exc) or getattr(exc, "Message", "") or type(exc).__name__
            log.warning("doc_close: %s refused to close: %s",
                        closed.get("title"), reason)
            return {"status": "error", "code": "document_not_closed",
                    "message": "The document was not closed: %s" % reason,
                    "document": closed, "retryable": False}

        # close() can return without closing anything; an "ok" must mean the
        # document is gone (#36).
        if _is_still_open(desktop, closing_doc):
            log.warning("doc_close: %s is still open after close()",
                        closed.get("title"))
            return {"status": "error", "code": "document_not_closed",
                    "message": "LibreOffice did not close the document.",
                    "document": closed, "retryable": False}
        log.info("doc_close: closed %s", closed.get("title"))

        result = {"status": "ok", "message": "Document closed.",
                  "closed": closed}

        # Activate the next document so getCurrentComponent() returns it
        if next_frame is not None:
            try:
                next_frame.activate()
                next_title = next_frame.getTitle()
                log.info("doc_close: activated next doc: %s", next_title)
                # The document now active, not the one closed.
                result["active_document"] = next_title
            except Exception:
                log.warning("doc_close: failed to activate next frame", exc_info=True)
        else:
            log.info("doc_close: no next frame found")

        return result


def _release_undo(model):
    """Leave any open undo context and empty the undo stack before closing.

    LibreOffice aborts in ~SfxUndoArray when a document is destroyed while
    its undo manager still has a list action open, and the nested undo
    arrays of a large rewrite (tables, notes, comments) are what it trips
    on (#2651). The stack is destroyed a moment later anyway.
    """
    try:
        undo = model.getUndoManager()
    except Exception:
        return
    try:
        # reset() leaves every open Undo context, clears both stacks and
        # removes any lock (XUndoManager.idl).
        undo.reset()
    except Exception:
        log.debug("doc_close: could not reset undo stack", exc_info=True)


def _describe_document(model):
    """Title and URL of *model*, read before it is closed."""
    info = {}
    try:
        info["title"] = model.getCurrentController().getFrame().getTitle()
    except Exception:
        pass
    try:
        info["url"] = model.getURL() or None
    except Exception:
        pass
    return info


def _is_still_open(desktop, model):
    """True if *model* is still one of the desktop's components."""
    try:
        components = desktop.getComponents().createEnumeration()
        while components.hasMoreElements():
            try:
                if components.nextElement() == model:
                    return True
            except Exception:
                continue
    except Exception:
        log.debug("doc_close: could not enumerate components", exc_info=True)
    return False


class ListOpenDocuments(ToolBase):
    """List all currently open documents in LibreOffice."""

    name = "doc_list_open"
    aliases = ["list_open_documents"]
    intent = "media"
    description = (
        "List the documents currently open in LibreOffice. Start here "
        "when the user refers to a document: it is usually already open, "
        "and this gives you the doc_id to address it with. "
        "Each document has a unique doc_id for identification. "
        "The active document (is_active=true) is the one MCP tools operate on."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = None
    is_mutation = False
    requires_doc = False

    def execute(self, ctx, **kwargs):
        try:
            doc_svc = ctx.services.document
            documents = doc_svc.enumerate_open_documents(
                active_model=ctx.doc)
            return {
                "status": "ok",
                "documents": documents,
                "count": len(documents),
            }
        except Exception as exc:
            log.exception("ListOpenDocuments failed: %s", exc)
            return {"status": "error", "error": str(exc)}


class GetRecentDocuments(ToolBase):
    """Get list of recently opened documents from LibreOffice history."""

    name = "doc_recent"
    aliases = ["get_recent_documents"]
    intent = "media"
    description = (
        "List recently opened documents from LibreOffice history. Use "
        "this when the user names a document that is not currently open "
        "and you do not know its path — it is how you find the path to "
        "give doc_open."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_count": {
                "type": "integer",
                "description": "Maximum number of recent documents to return (default 20).",
            },
        },
        "required": [],
    }
    doc_types = None
    is_mutation = False
    requires_doc = False

    def execute(self, ctx, **kwargs):
        max_count = kwargs.get("max_count", 20)
        try:
            uno_ctx = get_ctx()
            smgr = uno_ctx.ServiceManager
            cfg_provider = smgr.createInstanceWithContext(
                "com.sun.star.configuration.ConfigurationProvider", uno_ctx)
            arg = PropertyValue()
            arg.Name = "nodepath"
            arg.Value = (
                "/org.openoffice.Office.Histories/Histories"
                "/org.openoffice.Office.Histories:HistoryInfo['PickList']"
            )
            cfg = cfg_provider.createInstanceWithArguments(
                "com.sun.star.configuration.ConfigurationAccess", (arg,))

            order_list = cfg.getByName("OrderList")
            item_list = cfg.getByName("ItemList")

            docs = []
            names = order_list.getElementNames()
            # Names are string indices — sort numerically
            sorted_names = sorted(names, key=lambda n: int(n))
            for name in sorted_names[:max_count]:
                entry = order_list.getByName(name)
                url = entry.getPropertyValue("HistoryItemRef")
                title = ""
                try:
                    item = item_list.getByName(url)
                    title = item.getPropertyValue("Title")
                except Exception:
                    pass
                try:
                    path = uno.fileUrlToSystemPath(url)
                except Exception:
                    path = url
                doc = {"url": url, "path": path}
                if title:
                    doc["title"] = title
                docs.append(doc)

            return {
                "status": "ok",
                "documents": docs,
                "count": len(docs),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": "Failed to read recent documents: %s" % e,
            }


class SetDocumentProperties(ToolBase):
    """Set document metadata properties."""

    name = "doc_set_properties"
    aliases = ["set_document_properties"]
    intent = "media"
    description = (
        "Set document metadata properties "
        "(title, subject, author, description, keywords)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Document title.",
            },
            "subject": {
                "type": "string",
                "description": "Document subject.",
            },
            "author": {
                "type": "string",
                "description": "Document author.",
            },
            "description": {
                "type": "string",
                "description": "Document description.",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keywords.",
            },
        },
        "required": [],
    }
    doc_types = None
    is_mutation = True

    def execute(self, ctx, **kwargs):
        try:
            props = ctx.doc.getDocumentProperties()
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        updated = []

        if "title" in kwargs:
            props.Title = kwargs["title"]
            updated.append("title")

        if "subject" in kwargs:
            props.Subject = kwargs["subject"]
            updated.append("subject")

        if "author" in kwargs:
            props.Author = kwargs["author"]
            updated.append("author")

        if "description" in kwargs:
            props.Description = kwargs["description"]
            updated.append("description")

        if "keywords" in kwargs:
            props.Keywords = tuple(kwargs["keywords"])
            updated.append("keywords")

        if not updated:
            return {
                "status": "error",
                "error": "No properties provided to update.",
            }

        return {
            "status": "ok",
            "message": "Properties updated.",
            "updated": updated,
        }
