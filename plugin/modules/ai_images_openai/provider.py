# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""OpenAI-compatible image generation provider.

Calls /v1/images/generations — works with OpenAI, Together AI,
OpenRouter, and any compatible endpoint.
"""

import base64
import http.client
import json
import logging
import re
import ssl
import tempfile
import urllib.parse

from plugin.modules.ai_images.provider_base import ImageProvider

log = logging.getLogger("nelson.images.openai")


class OpenAIImageProvider(ImageProvider):
    """Image generation via an OpenAI-compatible endpoint."""

    name = "openai"

    def __init__(self, config_dict):
        self._config = config_dict

    def generate(self, prompt, width=1024, height=1024, model=None, **kwargs):
        """Generate an image via /v1/images/generations.

        Returns:
            (file_paths: list[str], error: str | None)
        """
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

        try:
            parsed = urllib.parse.urlparse(endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port
            scheme = (parsed.scheme or "https").lower()
            base_path = (parsed.path or "").rstrip("/")

            if scheme == "https":
                ctx = ssl.create_default_context()
                port = port or 443
                conn = http.client.HTTPSConnection(host, port, context=ctx,
                                                   timeout=120)
            else:
                port = port or 80
                conn = http.client.HTTPConnection(host, port, timeout=120)

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = "Bearer %s" % api_key

            path = base_path + "/images/generations"
            data = json.dumps(body).encode("utf-8")

            conn.request("POST", path, body=data, headers=headers)
            resp = conn.getresponse()

            if resp.status != 200:
                err_body = resp.read().decode("utf-8", errors="replace")
                return [], "HTTP %d: %s" % (resp.status, err_body[:200])

            result = json.loads(resp.read().decode("utf-8"))
            conn.close()

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

    def check(self):
        endpoint = self._config.get("endpoint") or ""
        if not endpoint:
            return (False, "No endpoint configured")
        api_key = self._config.get("api_key") or ""
        if not api_key:
            return (False, "No API key configured")
        return (True, "")


def _save_b64(b64_data):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(base64.b64decode(b64_data))
        return [tmp.name]


def _save_url(url):
    from plugin.framework.http import sync_request
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webp") as tmp:
        tmp.write(sync_request(url, parse_json=False))
        return [tmp.name]
