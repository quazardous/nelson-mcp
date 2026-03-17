# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generic document information tool."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.common")


class GetDocumentInfo(ToolBase):
    """Return generic metadata about the current document."""

    name = "get_document_info"
    description = (
        "Returns generic document metadata: title, file path, document type, "
        "modification status, and document properties (author, subject, etc.)."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    doc_types = None  # works with all document types
    tier = "core"

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        url = doc.getURL()
        doc_svc = ctx.services.document

        # Basic info.
        info = {
            "status": "ok",
            "doc_id": doc_svc.get_doc_id(doc),
            "doc_type": ctx.doc_type,
            "file_url": url or None,
            "is_modified": doc.isModified(),
            "is_new": not bool(url),
        }

        # Title: prefer document properties, fall back to URL filename.
        try:
            props = doc.getDocumentProperties()
            title = props.Title
            if not title and url:
                # Extract filename from file:///path/to/doc.odt
                title = url.rsplit("/", 1)[-1]
            info["title"] = title or "(untitled)"
            info["author"] = props.Author or None
            info["subject"] = props.Subject or None
            info["description"] = props.Description or None

            # Keywords
            try:
                kw = props.Keywords
                info["keywords"] = list(kw) if kw else []
            except Exception:
                info["keywords"] = []

            # Dates
            try:
                cdt = props.CreationDate
                info["creation_date"] = "%04d-%02d-%02d %02d:%02d" % (
                    cdt.Year, cdt.Month, cdt.Day, cdt.Hours, cdt.Minutes
                )
            except Exception:
                info["creation_date"] = None
            try:
                mdt = props.ModificationDate
                info["modification_date"] = "%04d-%02d-%02d %02d:%02d" % (
                    mdt.Year, mdt.Month, mdt.Day, mdt.Hours, mdt.Minutes
                )
            except Exception:
                info["modification_date"] = None

        except Exception:
            if url:
                info["title"] = url.rsplit("/", 1)[-1]
            else:
                info["title"] = "(untitled)"

        # Hint: other open documents
        try:
            all_docs = doc_svc.enumerate_open_documents(active_model=doc)
            other_docs = [d for d in all_docs if not d.get("is_active")]
            if other_docs:
                info["_other_open_documents"] = [
                    {"doc_id": d["doc_id"], "title": d["title"],
                     "doc_type": d["doc_type"]}
                    for d in other_docs
                ]
        except Exception:
            pass

        return info
