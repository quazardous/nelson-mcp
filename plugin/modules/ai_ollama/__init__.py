# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Ollama LLM provider module.

Registers LLM provider instances from configured Ollama servers.
User starts/stops Ollama themselves — Nelson just uses the API.
"""

import json
import logging
import os
import subprocess
import sys

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.ai.ollama")

_CREATION_FLAGS = (
    getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    if sys.platform == "win32" else 0
)


def _probe_ollama(endpoint):
    """Check if Ollama API is reachable."""
    import urllib.request
    try:
        url = endpoint.rstrip("/") + "/api/tags"
        req = urllib.request.urlopen(url, timeout=3)
        req.read()
        return True
    except Exception:
        return False


def _launch_ollama():
    """Start Ollama serve in a new console window."""
    import shutil
    ollama = shutil.which("ollama")
    if not ollama:
        return "Ollama not found. Install from https://ollama.com"
    try:
        subprocess.Popen(
            [ollama, "serve"],
            creationflags=_CREATION_FLAGS,
            start_new_session=(sys.platform != "win32"),
        )
        return None
    except Exception as e:
        return "Failed to start Ollama: %s" % e


def _stop_ollama():
    """Stop Ollama process."""
    try:
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(["taskkill", "/f", "/im", "ollama.exe"],
                           capture_output=True, creationflags=flags)
            subprocess.run(["taskkill", "/f", "/im", "ollama_llama_server.exe"],
                           capture_output=True, creationflags=flags)
        else:
            subprocess.run(["pkill", "-f", "ollama serve"],
                           capture_output=True)
    except Exception:
        log.debug("Failed to stop Ollama", exc_info=True)


def on_install():
    """Run install/detect script in a visible terminal."""
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx
    from plugin.main import get_services

    ctx = get_ctx()
    services = get_services()
    model = "llama3.2:latest"
    if services:
        cfg = services.config.proxy_for("ai.ollama")
        try:
            raw = cfg.get("instances") or "[]"
            items = json.loads(raw) if isinstance(raw, str) else raw
            if items and isinstance(items, list):
                model = items[0].get("model") or model
        except Exception:
            pass

    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")

    if sys.platform == "win32":
        script = os.path.join(scripts_dir, "install.ps1")
        cmd = ('cmd /c start "Install Ollama" powershell -ExecutionPolicy Bypass'
               ' -File "%s" -Model "%s"' % (script, model))
    else:
        script = os.path.join(scripts_dir, "install.sh")
        cmd = 'x-terminal-emulator -e bash "%s" "%s" || bash "%s" "%s"' % (
            script, model, script, model)

    if not os.path.isfile(script):
        msgbox(ctx, "Nelson", "Install script not found:\n%s" % script)
        return

    try:
        subprocess.Popen(cmd, shell=True, start_new_session=True,
                         creationflags=_CREATION_FLAGS)
    except Exception:
        log.exception("Failed to launch install script")
        msgbox(ctx, "Nelson", "Failed to launch install script.")


def on_create_preset():
    """Create a default Ollama instance in config."""
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx
    from plugin.main import get_services

    ctx = get_ctx()
    services = get_services()
    if not services:
        return

    cfg = services.config.proxy_for("ai.ollama")
    raw = cfg.get("instances") or "[]"
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        items = []

    # Check if a "Local" instance already exists
    for item in items:
        if item.get("name") == "Local":
            msgbox(ctx, "Nelson",
                   "Instance 'Local' already exists.\n"
                   "Reopen Options to see it.")
            return

    items.append({
        "name": "Local",
        "endpoint": "http://127.0.0.1:11434",
        "model": "llama3.2:latest",
        "temperature": 0.3,
    })
    cfg.set("instances", json.dumps(items))
    msgbox(ctx, "Nelson",
           "Instance 'Local' created.\n"
           "Reopen Options to see it.")


def on_launch_button():
    """Launch Ollama from Options button."""
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx

    if _probe_ollama("http://127.0.0.1:11434"):
        msgbox(get_ctx(), "Nelson", "Ollama is already running.")
        return
    err = _launch_ollama()
    if err:
        msgbox(get_ctx(), "Nelson", err)


class OllamaProvider:
    """LLM provider that talks to a local Ollama instance."""

    name = "ai_ollama"

    def __init__(self, config):
        self._config = config

    def complete(self, messages, **kwargs):
        from plugin.framework.http_client import http_json

        endpoint = self._config.get("endpoint") or "http://127.0.0.1:11434"
        model = kwargs.get("model") or self._config.get("model") or "llama3.2:latest"
        temperature = self._config.get("temperature")
        if temperature is None:
            temperature = 0.3

        body = {
            "model": model,
            "messages": messages,
            "temperature": float(temperature),
            "stream": False,
        }
        if "max_tokens" in kwargs:
            body["options"] = {"num_predict": kwargs["max_tokens"]}

        status, result = http_json(
            endpoint, "POST", "/api/chat",
            body=body, timeout=120, default_port=11434,
        )

        if status != 200:
            err = result if isinstance(result, str) else str(result)
            return {"content": None, "error": "HTTP %d: %s" % (status, err)}

        content = ""
        if isinstance(result, dict):
            msg = result.get("message", {})
            content = msg.get("content", "")

        return {"content": content, "model": model}

    def check(self):
        endpoint = self._config.get("endpoint") or "http://127.0.0.1:11434"
        if _probe_ollama(endpoint):
            return (True, "")
        return (False, "Ollama not reachable at %s" % endpoint)


class OllamaModule(ModuleBase):

    def __init__(self):
        self._services = None

    def initialize(self, services):
        from plugin.modules.ai import AiInstance

        self._services = services
        ai_svc = services.get("ai")
        if not ai_svc:
            return

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
            instance_id = "ollama:%s" % name
            ai_svc.register_instance(instance_id, AiInstance(
                name=name,
                module_name="ai.ollama",
                provider=OllamaProvider(item),
            ))

    def on_action(self, action):
        if action == "ollama_launch":
            cfg = self._services.config.proxy_for(self.name)
            # Try first instance endpoint, fallback to default
            endpoint = "http://127.0.0.1:11434"
            try:
                raw = cfg.get("instances") or "[]"
                items = json.loads(raw) if isinstance(raw, str) else raw
                if items and isinstance(items, list):
                    endpoint = items[0].get("endpoint") or endpoint
            except Exception:
                pass

            if _probe_ollama(endpoint):
                from plugin.framework.dialogs import msgbox
                from plugin.framework.uno_context import get_ctx
                msgbox(get_ctx(), "Nelson", "Ollama is already running.")
                return
            err = _launch_ollama()
            if err:
                from plugin.framework.dialogs import msgbox
                from plugin.framework.uno_context import get_ctx
                msgbox(get_ctx(), "Nelson", err)

        elif action == "ollama_stop":
            _stop_ollama()

        else:
            super().on_action(action)

    def get_menu_text(self, action):
        if action == "ollama_launch":
            return "Start Ollama"
        if action == "ollama_stop":
            return "Stop Ollama"
        return None
