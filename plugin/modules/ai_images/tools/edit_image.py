# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stub — image editing tool (not yet configured)."""

from plugin.framework.tool_base import ToolBase


class EditImage(ToolBase):
    """Edit the currently selected image using img2img."""

    name = "edit_image"
    intent = "media"
    description = (
        "Edit the selected image using a text prompt (Img2Img). "
        "If no image is selected, it will fail."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The visual description of the desired image version.",
            },
        },
        "required": ["prompt"],
    }
    doc_types = ["writer", "calc", "draw", "impress"]
    is_mutation = True
    long_running = True

    def execute(self, ctx, **kwargs):
        return {
            "status": "error",
            "message": "Image editing is not configured.",
        }
