# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""gallery_get — get metadata for a specific image."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.images")


class GetImageInfo(ToolBase):
    """Get detailed metadata for a specific image in the gallery."""

    name = "gallery_get"
    description = (
        "Get detailed metadata for a specific image in the gallery, "
        "including title, description, keywords, dimensions, and file path."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_id": {
                "type": "string",
                "description": "Image identifier (typically relative path within the gallery).",
            },
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Photos'). "
                    "Omit to use the default provider."
                ),
            },
        },
        "required": ["image_id"],
    }
    intent = "media"

    def execute(self, ctx, **kwargs):
        image_id = kwargs.get("image_id", "")
        if not image_id:
            return {"status": "error", "message": "image_id is required."}

        provider_id = kwargs.get("provider")

        svc = ctx.services.get("images")
        if svc is None:
            return {"status": "error", "message": "Images service is not available."}

        try:
            item = svc.get_item(image_id, instance_id=provider_id)
            if item is None:
                return {
                    "status": "error",
                    "message": "Image not found: %s" % image_id,
                }
            return {"status": "ok", "image": item}
        except Exception as e:
            return {"status": "error", "message": str(e)}
