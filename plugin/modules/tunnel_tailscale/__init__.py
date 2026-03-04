# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tailscale Funnel tunnel provider — pre/post reset, HTTPS support."""

import logging
import subprocess

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.tunnel.tailscale")

# Windows: hide subprocess console window
_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_RESET_COMMANDS = [
    ["tailscale", "funnel", "reset"],
    ["tailscale", "serve", "reset"],
]


class TailscaleProvider:
    """Tailscale Funnel: expose a local port via Tailscale network.

    HTTPS mode uses https+insecure:// to tell tailscale the backend is
    self-signed HTTPS. HTTP mode just uses the port number directly.
    Pre-start and post-stop run funnel/serve reset to ensure clean state.
    """

    name = "tailscale"
    binary_name = "tailscale"
    version_args = ["tailscale", "version"]
    install_url = "https://tailscale.com/download"

    def build_command(self, port, scheme, config):
        if scheme == "https":
            target = "https+insecure://127.0.0.1:%s" % port
        else:
            target = str(port)

        cmd = ["tailscale", "funnel", target]
        url_regex = r"(https://[\w.-]+\.ts\.net)"
        return cmd, url_regex

    def parse_line(self, line):
        return None

    def pre_start(self, config):
        """Reset funnel/serve state before starting."""
        self._run_reset_commands()

    def post_stop(self, config):
        """Reset funnel/serve state after stopping."""
        self._run_reset_commands()

    def _run_reset_commands(self):
        for cmd in _RESET_COMMANDS:
            try:
                subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=5,
                    creationflags=_CREATION_FLAGS,
                )
                log.debug("Reset: %s", " ".join(cmd))
            except Exception:
                log.debug("Reset command failed: %s", " ".join(cmd))


class TailscaleModule(ModuleBase):

    def initialize(self, services):
        if hasattr(services, "tunnel_manager"):
            services.tunnel_manager.register_provider(
                "tailscale", TailscaleProvider())
