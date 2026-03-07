# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""OpenAI-compatible image generation provider.

Calls /v1/images/generations — works with OpenAI, Together AI,
OpenRouter, and any compatible endpoint.
"""

import base64
import logging
import re
import tempfile
from typing import Dict, List, Optional, Tuple

from plugin.framework.http_client import http_json
from plugin.modules.ai_images.provider_base import ImageProvider

log = logging.getLogger("nelson.images.openai")


class OpenAIImageProvider(ImageProvider):
    """Image generation via an OpenAI-compatible endpoint."""

    name = "openai"

    def __init__(self, config_dict: Dict) -> None:
        self._config = config_dict

    def generate(self, prompt: str, width: int = 1024, height: int = 1024,
                 model: Optional[str] = None,
                 **kwargs) -> Tuple[List[str], Optional[str]]:
        """Generate an image via /v1/images/generations."""
        endpoint = self._config.get("endpoint") or "https://api.openai.com/v1"
        api_key = self._config.get("api_key") or ""
        model_name = model or self._config.get("model") or ""

        body = {
            "prompt": prompt,
            "n": 1,
            "size": "%dx%d" % (width, height),
            "response_format": "url",
        }
        if model_name:
            body["model"] = model_name

        headers = {}
        if api_key:
            headers["Authorization"] = "Bearer %s" % api_key

        try:
            status, result = http_json(
                endpoint, "POST", "/images/generations",
                body=body, headers=headers, timeout=120,
            )

            if status != 200:
                err_text = result if isinstance(result, str) else str(result)
                return [], "HTTP %d: %s" % (status, err_text[:200])

            if not isinstance(result, dict):
                return [], "Unexpected response format"

            for img in (result.get("data") or []):
                b64 = img.get("b64_json")
                if b64:
                    return _save_b64(b64), None
                url = img.get("url")
                if url:
                    if "data:image" in url:
                        match = re.search(
                            r'base64,([A-Za-z0-9+/=]+)', url)
                        if match:
                            return _save_b64(match.group(1)), None
                    return _save_url(url), None

            return [], "No image data in response"

        except Exception as e:
            log.exception("Image generation failed")
            return [], str(e)

    def check(self) -> Tuple[bool, str]:
        endpoint = self._config.get("endpoint") or ""
        if not endpoint:
            return (False, "No endpoint configured")
        api_key = self._config.get("api_key") or ""
        if not api_key:
            return (False, "No API key configured")
        return (True, "")


def _save_b64(b64_data: str) -> List[str]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(base64.b64decode(b64_data))
        return [tmp.name]


def _save_url(url: str) -> List[str]:
    from plugin.framework.http import sync_request
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webp") as tmp:
        tmp.write(sync_request(url, parse_json=False))
        return [tmp.name]
