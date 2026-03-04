# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stable Diffusion WebUI image provider.

Calls /sdapi/v1/txt2img and /sdapi/v1/img2img — works with
Automatic1111, Forge, and compatible forks.
"""

import base64
import http.client
import json
import logging
import tempfile
import urllib.parse

from plugin.modules.ai_images.provider_base import ImageProvider

log = logging.getLogger("nelson.ai_images.sdapi")


class SdapiImageProvider(ImageProvider):
    """Image generation via Stable Diffusion WebUI API."""

    name = "sdapi"

    def __init__(self, config_dict):
        self._config = config_dict

    def generate(self, prompt, width=512, height=512,
                 negative_prompt="", **kwargs):
        """Generate an image via /sdapi/v1/txt2img.

        Returns:
            (file_paths: list[str], error: str | None)
        """
        endpoint = self._config.get("endpoint") or "http://127.0.0.1:7860"
        model = self._config.get("model") or ""
        sampler = self._config.get("sampler") or "Euler a"
        steps = int(self._config.get("steps", 20))
        cfg_scale = float(self._config.get("cfg_scale", 7.0))

        body = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler,
            "batch_size": 1,
            "n_iter": 1,
        }
        if model:
            body["override_settings"] = {"sd_model_checkpoint": model}

        return self._post("/sdapi/v1/txt2img", endpoint, body)

    def img2img(self, prompt, init_image_b64, width=512, height=512,
                denoising_strength=0.75, negative_prompt="", **kwargs):
        """Edit an image via /sdapi/v1/img2img.

        Returns:
            (file_paths: list[str], error: str | None)
        """
        endpoint = self._config.get("endpoint") or "http://127.0.0.1:7860"
        sampler = self._config.get("sampler") or "Euler a"
        steps = int(self._config.get("steps", 20))
        cfg_scale = float(self._config.get("cfg_scale", 7.0))

        body = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "init_images": [init_image_b64],
            "denoising_strength": denoising_strength,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler,
        }

        return self._post("/sdapi/v1/img2img", endpoint, body)

    def _post(self, path, endpoint, body):
        try:
            parsed = urllib.parse.urlparse(endpoint)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 7860
            base_path = (parsed.path or "").rstrip("/")

            conn = http.client.HTTPConnection(host, port, timeout=300)

            headers = {"Content-Type": "application/json"}
            data = json.dumps(body).encode("utf-8")

            conn.request("POST", base_path + path, body=data, headers=headers)
            resp = conn.getresponse()

            if resp.status != 200:
                err_body = resp.read().decode("utf-8", errors="replace")
                return [], "HTTP %d: %s" % (resp.status, err_body[:200])

            result = json.loads(resp.read().decode("utf-8"))
            conn.close()

            images = result.get("images") or []
            if not images:
                return [], "No image data in response"

            with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".png") as tmp:
                tmp.write(base64.b64decode(images[0]))
                return [tmp.name], None

        except Exception as e:
            log.exception("SD API call failed")
            return [], str(e)

    def check(self):
        endpoint = self._config.get("endpoint") or ""
        if not endpoint:
            return (False, "No endpoint configured")
        try:
            parsed = urllib.parse.urlparse(endpoint)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 7860
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", "/sdapi/v1/sd-models")
            resp = conn.getresponse()
            conn.close()
            if resp.status == 200:
                return (True, "")
            return (False, "HTTP %d" % resp.status)
        except Exception as e:
            return (False, str(e))

    def supports_editing(self):
        return True
