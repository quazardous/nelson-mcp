# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI Horde image generation provider.

Wraps the AiHordeClient for free, crowdsourced image generation.
"""

import logging

from plugin.modules.ai_images.provider_base import ImageProvider

log = logging.getLogger("nelson.images.horde")


class _HordeInformer:
    """Minimal informer bridge for AiHordeClient callbacks."""

    def __init__(self):
        self.last_error = ""

    def update_status(self, text, progress):
        log.info("Horde: %s (%s%%)", text, progress)

    def show_error(self, msg, **kwargs):
        log.error("Horde Error: %s", msg)
        self.last_error = msg

    def set_finished(self):
        pass

    def get_generated_image_url_status(self):
        return ["", 0, ""]

    def set_generated_image_url_status(self, *args):
        pass

    def get_toolkit(self):
        return None


class HordeImageProvider(ImageProvider):
    """AI Horde image generation via crowdsourced workers."""

    name = "horde"

    def __init__(self, config_dict):
        self._config = config_dict
        self._client = None
        self._informer = _HordeInformer()

    def _get_client(self):
        if self._client is None:
            from plugin.lib.aihordeclient import AiHordeClient
            self._client = AiHordeClient(
                client_version="1.0.0",
                url_version_update="",
                client_help_url="",
                client_download_url="",
                settings={},
                client_name="Nelson_Horde_Client",
                informer=self._informer,
            )
        return self._client

    def generate(self, prompt, width=512, height=512, model=None, **kwargs):
        """Generate an image via AI Horde.

        Returns:
            (file_paths: list[str], error: str | None)
        """
        api_key = self._config.get("api_key") or "0000000000"
        model_name = model or self._config.get("model") or "stable_diffusion"
        max_wait = kwargs.get("max_wait") or self._config.get("max_wait") or 5
        nsfw = self._config.get("nsfw") or False

        options = {
            "prompt": prompt,
            "image_width": width,
            "image_height": height,
            "model": model_name,
            "api_key": api_key,
            "max_wait_minutes": max_wait,
            "steps": kwargs.get("steps", 30),
            "seed": kwargs.get("seed", ""),
            "prompt_strength": kwargs.get("prompt_strength", 7.5),
            "nsfw": nsfw,
            "censor_nsfw": not nsfw,
        }

        # img2img support
        source_image = kwargs.get("source_image")
        if source_image:
            options["source_image"] = source_image
            options["mode"] = "MODE_IMG2IMG"
            options["init_strength"] = kwargs.get("strength", 0.6)

        client = self._get_client()
        self._informer.last_error = ""

        try:
            paths = client.generate_image(options)
        except Exception:
            log.exception("AI Horde generation failed")
            paths = []

        error = self._informer.last_error if not paths else None
        return paths, error

    def supports_editing(self):
        return True
