# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Image editing tool — submits a background job for img2img."""

import logging

from plugin.framework.tool_base import ToolBase
from plugin.framework.image_utils import get_selected_image_base64
from plugin.modules.ai_images.tools.generate_image import _auto_save

log = logging.getLogger("nelson.ai_images.edit")


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
        prompt = kwargs["prompt"]

        # Get selected image as base64 PNG (must happen on main thread)
        source_b64 = get_selected_image_base64(ctx.doc, ctx.ctx)
        if not source_b64:
            return {
                "status": "error",
                "error": "No image selected. Select an image first.",
            }

        svc = ctx.services.ai_images
        instance = svc.get_instance()
        provider = svc.get_provider()  # raises RuntimeError if none

        if not provider.supports_editing():
            return {
                "status": "error",
                "error": "The active image provider does not support editing.",
            }

        job = ctx.services.jobs.submit(
            _edit_and_save,
            kind="image_edit",
            params={"prompt": prompt},
            provider=provider, prompt=prompt, source_image=source_b64,
            services=ctx.services,
            provider_name=getattr(provider, "name", ""),
            instance_name=getattr(instance, "name", ""),
        )
        return {
            "status": "ok",
            "job_id": job.job_id,
            "message": "Image editing started. Use get_job to poll.",
        }


def _edit_and_save(provider, prompt, source_image, services, provider_name="", instance_name=""):
    file_paths, error = provider.generate(prompt=prompt, source_image=source_image)
    gallery_items = []
    if file_paths and not error:
        gallery_items = _auto_save(file_paths, prompt, services, provider_name, instance_name)
    result = (file_paths, error)
    if gallery_items:
        result = (file_paths, error, gallery_items)
    return result
