# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stub — image generation tool (not yet configured)."""

from plugin.framework.tool_base import ToolBase


class GenerateImage(ToolBase):
    """Generate an image from a text prompt and insert it."""

    name = "generate_image"
    intent = "media"
    description = (
        "Generate an image from a text prompt and insert it "
        "into the document."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The visual description of the image to generate.",
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
            "message": "Image generation is not configured.",
        }
