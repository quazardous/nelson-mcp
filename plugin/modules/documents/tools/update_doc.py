# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""docgallery_update — update document metadata in a gallery provider."""

from plugin.framework.tool_base import ToolBase


class UpdateDocMetadata(ToolBase):
    """Update metadata for a document in the gallery.

    Writes title, description, subject, and keywords into the document
    file properties (ODF meta.xml or OOXML docProps/core.xml).
    Requires the provider to have 'Allow Editing Metadata' enabled.
    """

    name = "docgallery_update"
    aliases = ["docs_gallery_update"]
    requires_service = "documents"
    description = (
        "Update document metadata (title, description, subject, keywords) "
        "in the gallery. Writes directly into ODF or OOXML file properties "
        "without opening in LibreOffice. Requires writable provider."
    )
    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": (
                    "Document identifier (relative path within the gallery)."
                ),
            },
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Docs'). "
                    "Omit to use the default provider."
                ),
            },
            "title": {
                "type": "string",
                "description": "New document title.",
            },
            "description": {
                "type": "string",
                "description": (
                    "New document description / summary "
                    "(maps to 'Comments' in LibreOffice File > Properties)."
                ),
            },
            "subject": {
                "type": "string",
                "description": "New document subject.",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New list of keywords (replaces existing).",
            },
        },
        "required": ["doc_id"],
    }
    intent = "media"
    is_mutation = True
    requires_doc = False

    def execute(self, ctx, **kwargs):
        doc_id = kwargs.get("doc_id", "")
        if not doc_id:
            return {"status": "error", "message": "doc_id is required."}

        provider_id = kwargs.get("provider")

        # Build metadata dict from supplied fields
        metadata = {}
        for key in ("title", "description", "subject", "keywords"):
            if key in kwargs:
                metadata[key] = kwargs[key]

        if not metadata:
            return {"status": "error",
                    "message": "No metadata fields to update. "
                    "Provide at least one of: title, description, "
                    "subject, keywords."}

        svc = ctx.services.get("documents")
        if svc is None:
            return {"status": "error",
                    "message": "Documents service is not available."}

        try:
            updated = svc.update_metadata(
                doc_id, metadata, instance_id=provider_id)
            if updated is None:
                return {"status": "error",
                        "message": "Document not found: %s" % doc_id}
            return {"status": "ok", "document": updated}
        except NotImplementedError as e:
            return {"status": "error", "message": str(e)}
        except (ValueError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": str(e)}
