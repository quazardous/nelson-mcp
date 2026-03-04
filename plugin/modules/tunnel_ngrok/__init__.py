# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Ngrok tunnel provider — JSON log parsing, authtoken support."""

import json
import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.tunnel.ngrok")


class NgrokProvider:
    """Ngrok tunnel: HTTP tunnels with JSON log output.

    Uses --log-format json so we can parse structured output instead of
    relying on regex. Detects ERR_NGROK_105 (missing authtoken).
    """

    name = "ngrok"
    binary_name = "ngrok"
    version_args = ["ngrok", "version"]
    install_url = "https://ngrok.com/download"

    def build_command(self, port, scheme, config):
        cmd = [
            "ngrok", "http",
            "%s://localhost:%s" % (scheme, port),
            "--log", "stdout",
            "--log-format", "json",
        ]
        authtoken = config.get("authtoken", "")
        if authtoken:
            cmd.extend(["--authtoken", authtoken])

        # No regex needed — we use custom JSON parsing
        return cmd, None

    def parse_line(self, line):
        """Parse ngrok JSON log lines for the tunnel URL."""
        from plugin.modules.tunnel import TunnelAuthError

        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None

        # Check for auth error
        err = str(data.get("err", ""))
        if "ERR_NGROK_105" in err:
            raise TunnelAuthError("ngrok requires authtoken — "
                                  "set tunnel.ngrok.authtoken in config")

        # Check for tunnel started message
        if data.get("msg") == "started tunnel" and "url" in data:
            return data["url"]

        return None

    def pre_start(self, config):
        pass

    def post_stop(self, config):
        pass


class NgrokModule(ModuleBase):

    def initialize(self, services):
        if hasattr(services, "tunnel_manager"):
            services.tunnel_manager.register_provider(
                "ngrok", NgrokProvider())
