# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""gallery_search — full-text search across image gallery providers."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.images")


class SearchImages(ToolBase):
    """Search for images across gallery providers using full-text search."""

    name = "gallery_search"
    description = (
        "Search for images in the image gallery using full-text search. "
        "Matches against image title, description, keywords, and filename. "
        "Returns image metadata including file paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (matched against title, description, keywords, filename).",
            },
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID to search in (e.g. 'folder:My Photos'). "
                    "Omit to search across all providers."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 20).",
            },
        },
        "required": ["query"],
    }
    intent = "media"

    def execute(self, ctx, **kwargs):
        query = kwargs.get("query", "")
        if not query:
            return {"status": "error", "message": "query is required."}

        provider_id = kwargs.get("provider")
        limit = kwargs.get("limit", 20)

        svc = ctx.services.get("images")
        if svc is None:
            return {"status": "error", "message": "Images service is not available."}

        if not svc.list_instances():
            return {
                "status": "error",
                "message": "No image gallery providers configured.",
            }

        try:
            results = svc.search(query, instance_id=provider_id, limit=limit)
            return {
                "status": "ok",
                "query": query,
                "count": len(results),
                "images": results,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
