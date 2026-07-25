# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""docgallery_get — get metadata for a specific document."""

from plugin.framework.tool_base import ToolBase


class GetDocInfo(ToolBase):
    """Get detailed metadata for a specific document in the gallery."""

    name = "docgallery_get"
    aliases = ["docs_gallery_get"]
    requires_service = "documents"
    description = (
        "Get detailed metadata for a specific document in the gallery, "
        "including title, description, keywords, doc_type, and file path."
    )
    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": (
                    "Document identifier (typically relative path "
                    "within the gallery)."
                ),
            },
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Docs'). "
                    "Omit to use the default provider."
                ),
            },
        },
        "required": ["doc_id"],
    }
    intent = "media"
    requires_doc = False

    def execute(self, ctx, **kwargs):
        doc_id = kwargs.get("doc_id", "")
        if not doc_id:
            return {"status": "error", "message": "doc_id is required."}

        provider_id = kwargs.get("provider")

        svc = ctx.services.get("documents")
        if svc is None:
            return {"status": "error",
                    "message": "Documents service is not available."}

        try:
            item = svc.get_item(doc_id, instance_id=provider_id)
            if item is None:
                return {"status": "error",
                        "message": "Document not found: %s" % doc_id}
            return {"status": "ok", "document": item}
        except Exception as e:
            return {"status": "error", "message": str(e)}
