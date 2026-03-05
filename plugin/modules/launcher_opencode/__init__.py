# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""OpenCode CLI provider for the launcher module."""

import json
import logging
import os
import shutil

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.launcher.opencode")

_DEFAULT_CWD = os.path.join(
    os.path.expanduser("~"), ".local", "share", "nelson", "cli", "opencode")

# Directory containing prompt templates shipped with this module
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class OpenCodeProvider:
    """OpenCode CLI — AI coding assistant."""

    name = "opencode"
    label = "OpenCode"
    binary_name = "opencode"
    install_url = "https://opencode.ai/docs/cli/"
    default_cwd = _DEFAULT_CWD

    def get_args(self, mcp_url, config):
        return []

    def setup_env(self, mcp_url, env, cwd, config):
        """Write opencode.json and AGENTS.md into the working directory."""
        handle_config = config.get("handle_config", True)

        # 1. opencode.json — always inject MCP, optionally inject Ollama
        config_path = os.path.join(cwd, "opencode.json")
        oc_config = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "nelson": {
                    "type": "remote",
                    "url": mcp_url + "/sse",
                }
            }
        }

        if handle_config:
            ollama_url = config.get("ollama_url") or "http://localhost:11434/v1"
            ollama_model = config.get("ollama_model") or "qwen3:8b"

            oc_config["provider"] = {
                "ollama": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Ollama (local)",
                    "options": {
                        "baseURL": ollama_url,
                    },
                    "models": {
                        ollama_model: {
                            "name": ollama_model,
                        }
                    }
                }
            }
            oc_config["model"] = "ollama/%s" % ollama_model

        try:
            with open(config_path, "w") as f:
                json.dump(oc_config, f, indent=2)
            log.info("Wrote opencode config: %s", config_path)
        except Exception:
            log.exception("Failed to write opencode config")

        # 2. AGENTS.md — Nelson instructions (always)
        self._copy_prompt_file("AGENTS.md", cwd)

    def _copy_prompt_file(self, filename, cwd):
        """Copy a prompt template file into the working directory."""
        src = os.path.join(_PROMPTS_DIR, filename)
        dst = os.path.join(cwd, filename)
        if os.path.isfile(src):
            try:
                shutil.copy2(src, dst)
                log.info("Copied %s to %s", filename, dst)
            except Exception:
                log.exception("Failed to copy %s", filename)


def on_install():
    """Callback for the Install button in Options."""
    from plugin.modules.launcher import run_install_for_provider
    run_install_for_provider("opencode")


class OpenCodeModule(ModuleBase):

    def initialize(self, services):
        if hasattr(services, "launcher_manager"):
            services.launcher_manager.register_provider(
                "opencode", OpenCodeProvider())
