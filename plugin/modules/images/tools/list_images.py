# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""gallery_list — browse images in a gallery provider."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.images")


class ListImages(ToolBase):
    """List images from a gallery provider with pagination."""

    name = "gallery_list"
    description = (
        "List images from the image gallery with optional path filtering "
        "and pagination. Returns image metadata including file paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Photos'). "
                    "Omit to use the default provider."
                ),
            },
            "path": {
                "type": "string",
                "description": "Sub-path within the gallery to list (default: root).",
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

    def execute(self, ctx, **kwargs):
        provider_id = kwargs.get("provider")
        path = kwargs.get("path", "")
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 50)

        svc = ctx.services.get("images")
        if svc is None:
            return {"status": "error", "message": "Images service is not available."}

        if not svc.list_instances():
            return {
                "status": "error",
                "message": "No image gallery providers configured.",
            }

        try:
            results = svc.list_items(
                instance_id=provider_id, path=path, offset=offset, limit=limit,
            )
            return {
                "status": "ok",
                "path": path,
                "offset": offset,
                "count": len(results),
                "images": results,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
