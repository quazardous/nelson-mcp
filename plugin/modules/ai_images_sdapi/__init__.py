# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stable Diffusion WebUI (A1111/Forge) image generation sub-module."""

import json
import logging
import os
import subprocess
import sys

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.ai_images.sdapi")

_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform == "win32" else 0

_DEFAULT_ENDPOINT = "http://127.0.0.1:7860"

# Common install locations to probe
_KNOWN_PATHS = []
if sys.platform == "win32":
    _home = os.path.expanduser("~")
    _KNOWN_PATHS = [
        os.path.join(_home, "stable-diffusion-webui"),
        os.path.join(_home, "Desktop", "stable-diffusion-webui"),
        os.path.join(_home, "sd-webui"),
        "C:\\stable-diffusion-webui",
    ]
else:
    _home = os.path.expanduser("~")
    _KNOWN_PATHS = [
        os.path.join(_home, "stable-diffusion-webui"),
        os.path.join(_home, "sd-webui"),
        "/opt/stable-diffusion-webui",
    ]


def _probe_api(endpoint):
    """Check if SD WebUI API is reachable. Returns True if it responds."""
    import urllib.request
    try:
        url = endpoint.rstrip("/") + "/sdapi/v1/sd-models"
        req = urllib.request.urlopen(url, timeout=3)
        req.read()
        return True
    except Exception:
        return False


def _find_installations():
    """Return list of existing A1111/Forge install directories."""
    found = []
    for path in _KNOWN_PATHS:
        # Check for webui.py (the main entry point)
        if os.path.isfile(os.path.join(path, "webui.py")):
            found.append(path)
        elif os.path.isfile(os.path.join(path, "webui-user.bat")):
            found.append(path)
        elif os.path.isfile(os.path.join(path, "webui.sh")):
            found.append(path)
    return found


# starter_model key -> checkpoint filename
_MODEL_FILES = {
    "juggernaut_xl": "juggernautXL_v9Lightning.safetensors",
    "dreamshaper8": "dreamshaper_8.safetensors",
    "dreamshaperxl": "dreamshaperXL_v21.safetensors",
}

# Optimal instance presets per model
_MODEL_PRESETS = {
    "juggernaut_xl": {
        "model": "juggernautXL_v9Lightning.safetensors",
        "resolution": "1024x1024",
        "sampler": "DPM++ SDE Karras",
        "steps": 6,
        "cfg_scale": 2.0,
        "negative_prompt": "ugly, deformed, noisy, blurry, low quality, text, watermark, signature, bad anatomy, bad hands, extra fingers, fewer fingers, cropped",
        "hires_fix": False,
        "hires_scale": 1.5,
        "hires_steps": 10,
        "hires_denoising": 0.4,
    },
    "dreamshaper8": {
        "model": "dreamshaper_8.safetensors",
        "resolution": "512x768",
        "sampler": "DPM++ 2M Karras",
        "steps": 25,
        "cfg_scale": 7.0,
        "negative_prompt": "ugly, deformed, noisy, blurry, low quality, cartoon, anime, illustration, painting, sketch, watermark, text",
        "hires_fix": True,
        "hires_scale": 1.5,
        "hires_steps": 10,
        "hires_denoising": 0.4,
    },
    "dreamshaperxl": {
        "model": "dreamshaperXL_v21.safetensors",
        "resolution": "1024x1024",
        "sampler": "DPM++ 2M Karras",
        "steps": 25,
        "cfg_scale": 7.0,
        "negative_prompt": "ugly, deformed, noisy, blurry, low quality, text, watermark, signature, bad anatomy, bad hands",
        "hires_fix": False,
        "hires_scale": 1.5,
        "hires_steps": 10,
        "hires_denoising": 0.4,
    },
}


def _save_auto_instance(endpoint):
    """Create or update the 'auto' instance with preset settings."""
    from plugin.main import get_services
    services = get_services()
    if not services:
        return False

    cfg = services.config.proxy_for("ai_images.sdapi")
    starter = cfg.get("starter_model") or "juggernaut_xl"
    preset = _MODEL_PRESETS.get(starter, _MODEL_PRESETS["juggernaut_xl"]).copy()
    preset["name"] = "auto"
    preset["endpoint"] = endpoint

    raw = cfg.get("instances") or "[]"
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []

    # Update existing "auto" or append
    updated = False
    for i, item in enumerate(items):
        if item.get("name") == "auto":
            items[i] = preset
            updated = True
            break
    if not updated:
        items.append(preset)

    cfg.set("instances", json.dumps(items))
    log.info("Auto-configured sdapi instance: %s (model=%s)", endpoint, preset.get("model"))
    return True


def on_create_preset():
    """Create an optimized instance for the currently selected starter model."""
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx
    from plugin.main import get_services

    ctx = get_ctx()
    services = get_services()
    if not services:
        return

    cfg = services.config.proxy_for("ai_images.sdapi")
    starter = cfg.get("starter_model") or "juggernaut_xl"
    preset = _MODEL_PRESETS.get(starter)
    if not preset:
        msgbox(ctx, "Nelson", "No preset available for model: %s" % starter)
        return

    instance = preset.copy()
    instance["name"] = starter
    instance["endpoint"] = _DEFAULT_ENDPOINT

    raw = cfg.get("instances") or "[]"
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []

    # Replace existing or append
    replaced = False
    for i, item in enumerate(items):
        if item.get("name") == starter:
            items[i] = instance
            replaced = True
            break
    if not replaced:
        items.append(instance)

    cfg.set("instances", json.dumps(items))
    msgbox(ctx, "Nelson",
           "Instance '%s' created with optimized settings.\n"
           "Reopen Options to see it." % starter)


def _stop_forge():
    """Stop Forge by running the stop script in a visible terminal."""
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx

    ctx = get_ctx()
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")

    if sys.platform == "win32":
        script_path = os.path.join(scripts_dir, "stop.ps1")
        ps_cmd = 'powershell -ExecutionPolicy Bypass -File "%s" -Endpoint "%s"' % (
            script_path, _DEFAULT_ENDPOINT)
        full_cmd = 'cmd /c start "Stop Forge" cmd /c %s' % ps_cmd
    else:
        # Linux/macOS: simple curl POST
        import urllib.request
        if not _probe_api(_DEFAULT_ENDPOINT):
            msgbox(ctx, "Nelson", "Forge is not running.")
            return
        try:
            url = _DEFAULT_ENDPOINT.rstrip("/") + "/sdapi/v1/server-kill"
            req = urllib.request.Request(url, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            log.debug("Forge shutdown request failed", exc_info=True)
        msgbox(ctx, "Nelson", "Forge shutdown signal sent.")
        return

    if not os.path.isfile(script_path):
        msgbox(ctx, "Nelson", "Stop script not found:\n%s" % script_path)
        return

    try:
        subprocess.Popen(
            full_cmd,
            shell=True,
            start_new_session=True,
            creationflags=_CREATION_FLAGS,
        )
    except Exception:
        log.exception("Failed to launch stop script")
        msgbox(ctx, "Nelson",
               "Failed to launch stop script.\n"
               "Check ~/nelson.log for details.")


def _open_browser():
    """Open the Forge WebUI in the default browser."""
    import webbrowser
    webbrowser.open(_DEFAULT_ENDPOINT)


def on_install():
    """Run install/update script — always re-entrant.

    The script itself is idempotent: skips clone if dir exists (does git pull),
    skips venv if already created, skips deps if installed, downloads model
    only if not already present.  Auto-configures the 'auto' instance.
    """
    from plugin.framework.uno_context import get_ctx

    ctx = get_ctx()
    _save_auto_instance(_DEFAULT_ENDPOINT)
    _run_install_script(ctx)


def on_launch():
    """Launch A1111 if not already running."""
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx

    ctx = get_ctx()

    # Already running?
    if _probe_api(_DEFAULT_ENDPOINT):
        msgbox(ctx, "Nelson",
               "SD WebUI API is already running at %s" % _DEFAULT_ENDPOINT)
        return

    # Find installation
    installs = _find_installations()
    if not installs:
        msgbox(ctx, "Nelson",
               "No SD WebUI installation found.\n"
               "Use 'Detect / Install A1111' first.")
        return

    webui_dir = installs[0]
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")

    if sys.platform == "win32":
        script_path = os.path.join(scripts_dir, "launch.ps1")
        # Use cmd /c start to get a visible terminal window
        ps_cmd = 'powershell -ExecutionPolicy Bypass -File "%s" -WebUIDir "%s"' % (
            script_path, webui_dir)
        full_cmd = 'cmd /c start "Forge" cmd /c %s' % ps_cmd
    else:
        script_path = os.path.join(scripts_dir, "launch.sh")
        full_cmd = _build_terminal_cmd([
            "bash", script_path, webui_dir,
        ])

    if not os.path.isfile(script_path):
        msgbox(ctx, "Nelson",
               "Launch script not found:\n%s" % script_path)
        return

    # Ensure auto instance exists
    _save_auto_instance(_DEFAULT_ENDPOINT)

    try:
        log.info("Launching SD WebUI from %s", webui_dir)
        subprocess.Popen(
            full_cmd,
            shell=isinstance(full_cmd, str),
            start_new_session=True,
            creationflags=_CREATION_FLAGS,
        )
    except Exception:
        log.exception("Failed to launch SD WebUI")
        msgbox(ctx, "Nelson",
               "Failed to launch SD WebUI.\n"
               "Check ~/nelson.log for details.")


def _get_starter_model():
    """Read starter_model from saved config."""
    try:
        from plugin.main import get_services
        services = get_services()
        if services:
            cfg = services.config.proxy_for("ai_images.sdapi")
            return cfg.get("starter_model") or "dreamshaper8"
    except Exception:
        log.debug("Could not read starter_model from config", exc_info=True)
    return "dreamshaper8"


def _run_install_script(ctx):
    """Launch the install script in a terminal."""
    from plugin.framework.dialogs import msgbox

    model = _get_starter_model()
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
    if sys.platform == "win32":
        script_path = os.path.join(scripts_dir, "install.ps1")
        ps_cmd = 'powershell -ExecutionPolicy Bypass -File "%s" -StarterModel %s' % (
            script_path, model)
        full_cmd = 'cmd /c start "Forge Install" cmd /c %s' % ps_cmd
    else:
        script_path = os.path.join(scripts_dir, "install.sh")
        full_cmd = _build_terminal_cmd([
            "bash", script_path, model,
        ])

    if not os.path.isfile(script_path):
        msgbox(ctx, "Nelson",
               "Install script not found:\n%s" % script_path)
        return

    # Pre-configure instance for after install
    _save_auto_instance(_DEFAULT_ENDPOINT)

    try:
        subprocess.Popen(
            full_cmd,
            shell=isinstance(full_cmd, str),
            start_new_session=True,
            creationflags=_CREATION_FLAGS,
        )
    except Exception:
        log.exception("Failed to launch install script")
        msgbox(ctx, "Nelson",
               "Failed to launch install script.\n"
               "Check ~/nelson.log for details.")


def _shell_quote(s):
    import shlex
    return shlex.quote(s)


def _build_terminal_cmd(cli_cmd):
    """Wrap cli_cmd in a terminal emulator (Linux/macOS only)."""
    import shutil
    for term in ["gnome-terminal", "konsole", "xfce4-terminal",
                 "mate-terminal", "alacritty", "kitty", "xterm"]:
        if shutil.which(term):
            if term in ("gnome-terminal", "mate-terminal"):
                return [term, "--", *cli_cmd]
            return [term, "-e", *cli_cmd]
    return ["xterm", "-e", *cli_cmd]


class AiImagesSdapiModule(ModuleBase):

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
            instance_id = "sdapi:%s" % name
            svc.register_instance(instance_id, ImageInstance(
                name=name,
                module_name="ai_images.sdapi",
                provider=_LazyProvider(item),
            ))

    def on_action(self, action):
        if action == "sdapi_launch":
            on_launch()
        elif action == "sdapi_stop":
            _stop_forge()
        elif action == "sdapi_browser":
            _open_browser()
        else:
            super().on_action(action)

    def get_menu_text(self, action):
        if action == "sdapi_launch":
            return "Launch Forge"
        if action == "sdapi_stop":
            return "Stop Forge"
        if action == "sdapi_browser":
            return "Open Forge in Browser"
        return super().get_menu_text(action)


class _LazyProvider:
    """Deferred SD WebUI provider — avoids import at startup."""

    def __init__(self, config_dict):
        self._config = config_dict
        self._real = None

    def _ensure(self):
        if self._real is None:
            from plugin.modules.ai_images_sdapi.provider import (
                SdapiImageProvider)
            self._real = SdapiImageProvider(self._config)
        return self._real

    def generate(self, prompt, **kwargs):
        return self._ensure().generate(prompt, **kwargs)

    def check(self):
        return self._ensure().check()

    def supports_editing(self):
        return self._ensure().supports_editing()

    def supports_interrogate(self):
        return self._ensure().supports_interrogate()

    def interrogate(self, image_b64, model="clip"):
        return self._ensure().interrogate(image_b64, model=model)
