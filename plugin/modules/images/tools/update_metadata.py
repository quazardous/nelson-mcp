# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""gallery_update — update XMP metadata for a gallery image."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.images")


class UpdateMetadata(ToolBase):
    """Update XMP sidecar metadata for an image in the gallery."""

    name = "gallery_update"
    description = (
        "Update metadata (title, description, keywords, rating) for an image "
        "in the gallery. Writes an XMP sidecar file and re-indexes. "
        "The provider must be writable."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_id": {
                "type": "string",
                "description": "Image identifier (relative path within the gallery).",
            },
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Photos'). "
                    "Omit to use the default provider."
                ),
            },
            "title": {
                "type": "string",
                "description": "Image title.",
            },
            "description": {
                "type": "string",
                "description": "Image description.",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keywords/tags.",
            },
            "rating": {
                "type": "integer",
                "description": "Rating (0-5).",
            },
        },
        "required": ["image_id"],
    }
    intent = "media"
    is_mutation = True

    def execute(self, ctx, **kwargs):
        image_id = kwargs.get("image_id", "")
        if not image_id:
            return {"status": "error", "message": "image_id is required."}

        provider_id = kwargs.get("provider")

        # Build metadata dict from provided fields
        meta = {}
        for key in ("title", "description", "keywords", "rating"):
            if key in kwargs:
                meta[key] = kwargs[key]

        if not meta:
            return {
                "status": "error",
                "message": "No metadata fields provided. "
                "Set at least one of: title, description, keywords, rating.",
            }

        svc = ctx.services.get("images")
        if svc is None:
            return {"status": "error", "message": "Images service is not available."}

        try:
            updated = svc.update_metadata(
                image_id, meta, instance_id=provider_id,
            )
            if updated is None:
                return {
                    "status": "error",
                    "message": "Image not found after update: %s" % image_id,
                }
            return {"status": "ok", "image": updated}
        except NotImplementedError as e:
            return {"status": "error", "message": str(e)}
        except FileNotFoundError as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": str(e)}
