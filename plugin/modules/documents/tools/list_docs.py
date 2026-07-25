# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""docgallery_list — browse documents in a gallery provider."""

from plugin.framework.tool_base import ToolBase


class ListDocs(ToolBase):
    """List documents from a gallery provider with pagination."""

    name = "docgallery_list"
    aliases = ["docs_gallery_list"]
    requires_service = "documents"
    description = (
        "List documents from the document gallery with optional path and "
        "type filtering and pagination. Returns document metadata including "
        "file paths, doc_type, and document properties."
    )
    parameters = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Docs'). "
                    "Omit to use the default provider."
                ),
            },
            "path": {
                "type": "string",
                "description": "Sub-path within the gallery to list (default: root).",
            },
            "doc_type": {
                "type": "string",
                "description": (
                    "Filter by document type: writer, calc, impress, draw, other."
                ),
                "enum": ["writer", "calc", "impress", "draw", "other"],
            },
            "offset": {
                "type": "integer",
                "description": "Number of items to skip (default: 0).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to return (default: 50).",
            },
        },
    }
    intent = "media"
    requires_doc = False

    def execute(self, ctx, **kwargs):
        provider_id = kwargs.get("provider")
        path = kwargs.get("path", "")
        doc_type = kwargs.get("doc_type")
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 50)

        svc = ctx.services.get("documents")
        if svc is None:
            return {"status": "error",
                    "message": "Documents service is not available."}

        if not svc.list_instances():
            return {"status": "error",
                    "message": "No document gallery providers configured."}

        try:
            results = svc.list_items(
                instance_id=provider_id, path=path,
                offset=offset, limit=limit, doc_type=doc_type,
            )
            return {
                "status": "ok",
                "path": path,
                "offset": offset,
                "count": len(results),
                "documents": results,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
