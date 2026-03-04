# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""OpenAI-compatible AI image generation sub-module."""

import json
import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.ai_images.openai")


class AiImagesOpenaiModule(ModuleBase):

    def initialize(self, services):
        from plugin.modules.ai_images.service import ImageInstance

        svc = services.ai_images
        cfg = services.config.proxy_for(self.name)
        raw = cfg.get("instances") or "[]"
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(items, list):
            return

        for item in items:
            name = item.get("name") or "default"
            instance_id = "openai:%s" % name
            svc.register_instance(instance_id, ImageInstance(
                name=name,
                module_name="ai_images.openai",
                provider=_LazyProvider(item),
            ))


class _LazyProvider:
    """Deferred OpenAI image provider — avoids import at startup."""

    def __init__(self, config_dict):
        self._config = config_dict
        self._real = None

    def _ensure(self):
        if self._real is None:
            from plugin.modules.ai_images_openai.provider import (
                OpenAIImageProvider)
            self._real = OpenAIImageProvider(self._config)
        return self._real

    def generate(self, prompt, **kwargs):
        return self._ensure().generate(prompt, **kwargs)

    def check(self):
        return self._ensure().check()

    def supports_editing(self):
        return False
