# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stable Diffusion WebUI image provider.

Calls /sdapi/v1/txt2img and /sdapi/v1/img2img — works with
Automatic1111, Forge, and compatible forks.
"""

import base64
import logging
import tempfile
from typing import Dict, List, Optional, Tuple

from plugin.framework.http_client import http_json
from plugin.modules.ai_images.provider_base import ImageProvider

log = logging.getLogger("nelson.ai_images.sdapi")

_DEFAULT_ENDPOINT = "http://127.0.0.1:7860"


class SdapiImageProvider(ImageProvider):
    """Image generation via Stable Diffusion WebUI API."""

    name = "sdapi"

    def __init__(self, config_dict: Dict) -> None:
        self._config = config_dict

    def _parse_resolution(self) -> Tuple[int, int]:
        """Parse 'WxH' resolution string from config, return (width, height)."""
        res = self._config.get("resolution") or "512x512"
        try:
            w, h = res.lower().split("x")
            return int(w), int(h)
        except (ValueError, AttributeError):
            return 512, 512

    def _get_endpoint(self) -> str:
        return self._config.get("endpoint") or _DEFAULT_ENDPOINT

    def generate(self, prompt: str, width: Optional[int] = None,
                 height: Optional[int] = None,
                 negative_prompt: Optional[str] = None,
                 **kwargs) -> Tuple[List[str], Optional[str]]:
        """Generate an image via /sdapi/v1/txt2img."""
        endpoint = self._get_endpoint()
        model = self._config.get("model") or ""
        sampler = self._config.get("sampler") or "Euler a"
        steps = int(self._config.get("steps", 20))
        cfg_scale = float(self._config.get("cfg_scale", 7.0))
        def_w, def_h = self._parse_resolution()
        width = width or def_w
        height = height or def_h
        if negative_prompt is None:
            negative_prompt = self._config.get("negative_prompt") or ""

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

        # Hires fix
        if self._config.get("hires_fix"):
            body["enable_hr"] = True
            body["hr_scale"] = float(self._config.get("hires_scale", 2.0))
            body["hr_second_pass_steps"] = int(self._config.get("hires_steps", 10))
            body["denoising_strength"] = float(self._config.get("hires_denoising", 0.4))

        return self._post("/sdapi/v1/txt2img", endpoint, body)

    def img2img(self, prompt: str, init_image_b64: str,
                width: Optional[int] = None, height: Optional[int] = None,
                denoising_strength: float = 0.75,
                negative_prompt: Optional[str] = None,
                **kwargs) -> Tuple[List[str], Optional[str]]:
        """Edit an image via /sdapi/v1/img2img."""
        endpoint = self._get_endpoint()
        sampler = self._config.get("sampler") or "Euler a"
        steps = int(self._config.get("steps", 20))
        cfg_scale = float(self._config.get("cfg_scale", 7.0))
        def_w, def_h = self._parse_resolution()
        width = width or def_w
        height = height or def_h
        if negative_prompt is None:
            negative_prompt = self._config.get("negative_prompt") or ""

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

    def _post(self, path: str, endpoint: str,
              body: Dict) -> Tuple[List[str], Optional[str]]:
        try:
            status, result = http_json(
                endpoint, "POST", path, body=body,
                timeout=300, default_port=7860,
            )

            if status != 200:
                err_text = result if isinstance(result, str) else str(result)
                return [], "HTTP %d: %s" % (status, err_text[:200])

            images = result.get("images") or [] if isinstance(result, dict) else []
            if not images:
                return [], "No image data in response"

            with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".png") as tmp:
                tmp.write(base64.b64decode(images[0]))
                return [tmp.name], None

        except Exception as e:
            log.exception("SD API call failed")
            return [], str(e)

    def check(self) -> Tuple[bool, str]:
        endpoint = self._config.get("endpoint") or ""
        if not endpoint:
            return (False, "No endpoint configured")
        try:
            status, _body = http_json(
                endpoint, "GET", "/sdapi/v1/sd-models",
                timeout=5, default_port=7860,
            )
            if status == 200:
                return (True, "")
            return (False, "HTTP %d" % status)
        except Exception as e:
            return (False, str(e))

    def supports_editing(self) -> bool:
        return True

    def supports_interrogate(self) -> bool:
        return True

    def interrogate(self, image_b64: str,
                    model: str = "clip") -> Tuple[str, Optional[str]]:
        """Describe an image via /sdapi/v1/interrogate."""
        endpoint = self._get_endpoint()
        body = {"image": image_b64, "model": model}
        try:
            status, result = http_json(
                endpoint, "POST", "/sdapi/v1/interrogate",
                body=body, timeout=60, default_port=7860,
            )

            if status != 200:
                err_text = result if isinstance(result, str) else str(result)
                return ("", "HTTP %d: %s" % (status, err_text[:200]))

            caption = result.get("caption", "").strip() if isinstance(result, dict) else ""
            return (caption, None)
        except Exception as e:
            log.exception("Interrogate API call failed")
            return ("", str(e))
