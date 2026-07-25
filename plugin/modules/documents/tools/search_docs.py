# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""docgallery_search — search documents in gallery providers."""

from plugin.framework.tool_base import ToolBase


class SearchDocs(ToolBase):
    """Search for documents in gallery providers."""

    name = "docgallery_search"
    aliases = ["docs_gallery_search"]
    requires_service = "documents"
    description = (
        "Search for documents in the document gallery. "
        "Matches against filename, title, description, and keywords. "
        "Returns document metadata including file paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search query (matched against filename, title, "
                    "description, keywords)."
                ),
            },
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID to search in. "
                    "Omit to use the default provider."
                ),
            },
            "doc_type": {
                "type": "string",
                "description": (
                    "Filter by document type: writer, calc, impress, "
                    "draw, other."
                ),
                "enum": ["writer", "calc", "impress", "draw", "other"],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 20).",
            },
        },
        "required": ["query"],
    }
    intent = "media"
    requires_doc = False

    def execute(self, ctx, **kwargs):
        query = kwargs.get("query", "")
        if not query:
            return {"status": "error", "message": "query is required."}

        provider_id = kwargs.get("provider")
        doc_type = kwargs.get("doc_type")
        limit = kwargs.get("limit", 20)

        svc = ctx.services.get("documents")
        if svc is None:
            return {"status": "error",
                    "message": "Documents service is not available."}

        if not svc.list_instances():
            return {"status": "error",
                    "message": "No document gallery providers configured."}

        try:
            results = svc.search(
                query, instance_id=provider_id, limit=limit,
                doc_type=doc_type,
            )
            return {
                "status": "ok",
                "query": query,
                "count": len(results),
                "documents": results,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
