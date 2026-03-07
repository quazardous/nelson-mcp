# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Image generation tool — submits a background job."""

import logging
import os
import re
import uuid
from datetime import datetime

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.ai_images.generate")


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
        prompt = kwargs["prompt"]
        svc = ctx.services.ai_images
        instance = svc.get_instance()  # raises via get_provider fallback
        provider = svc.get_provider()  # raises RuntimeError if none

        job = ctx.services.jobs.submit(
            _generate_and_save,
            kind="image_generate",
            params={"prompt": prompt},
            provider=provider, prompt=prompt, services=ctx.services,
            provider_name=getattr(provider, "name", ""),
            instance_name=getattr(instance, "name", ""),
        )
        return {
            "status": "ok",
            "job_id": job.job_id,
            "message": "Image generation started. Use get_job to poll.",
        }


def _generate_and_save(provider, prompt, services, provider_name="", instance_name=""):
    endpoint = getattr(provider, "_config", {}).get("endpoint", "")
    if endpoint:
        services.jobs.acquire_endpoint(endpoint)
    try:
        file_paths, error = provider.generate(prompt=prompt)
    finally:
        if endpoint:
            services.jobs.release_endpoint(endpoint)
    gallery_items = []
    if file_paths and not error:
        gallery_items = _auto_save(file_paths, prompt, services, provider_name, instance_name)
    result = (file_paths, error)
    if gallery_items:
        result = (file_paths, error, gallery_items)
    return result


def _slugify(text, max_len=60):
    """Turn a prompt into a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:max_len]


def _format_dest_name(template, prompt, file_path, provider_name="", instance_name=""):
    """Expand a filename template with placeholders."""
    now = datetime.now()
    values = {
        "prompt": _slugify(prompt),
        "provider": _slugify(provider_name or "unknown", max_len=30),
        "instance": _slugify(instance_name or "default", max_len=30),
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
        "timestamp": now.strftime("%Y%m%d_%H%M%S"),
        "uuid": uuid.uuid4().hex[:8],
    }
    name = template.format(**values)
    # Ensure extension from source file
    _, ext = os.path.splitext(file_path)
    if ext and not os.path.splitext(name)[1]:
        name = name + ext
    return name


def _auto_save(file_paths, prompt, services, provider_name="", instance_name=""):
    """Auto-save generated images to a gallery provider.

    Returns list of {"instance_id": ..., "image_id": ...} for saved items.
    """
    cfg = services.config.proxy_for("ai_images")
    target_id = cfg.get("save_to_gallery") or ""
    if not target_id:
        return []
    gallery = services.get("images")
    if not gallery:
        return []
    template = cfg.get("gallery_filename") or ""
    metadata = {"description": prompt, "keywords": ["ai-generated"]}
    saved = []
    for path in file_paths:
        try:
            dest_name = _format_dest_name(template, prompt, path, provider_name, instance_name) if template else None
            item = gallery.add_item(path, metadata=metadata, instance_id=target_id, dest_name=dest_name)
            if item:
                saved.append({
                    "instance_id": target_id,
                    "image_id": item.get("id") or item.get("name", ""),
                })
        except Exception:
            log.exception("Auto-save to gallery failed for %s", path)
    return saved
