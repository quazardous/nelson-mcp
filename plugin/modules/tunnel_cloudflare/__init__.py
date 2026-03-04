# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cloudflare tunnel provider — quick or named tunnels via cloudflared."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.tunnel.cloudflare")


class CloudflareProvider:
    """Cloudflare Tunnel: quick (random URL) or named (stable domain).

    Quick mode: cloudflared creates a temporary trycloudflare.com URL.
    Named mode: uses a pre-configured tunnel name with a known public URL.
    """

    name = "cloudflare"
    binary_name = "cloudflared"
    version_args = ["cloudflared", "--version"]
    install_url = "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"

    def build_command(self, port, scheme, config):
        tunnel_name = config.get("tunnel_name", "")

        if tunnel_name:
            # Named tunnel — stable domain, pre-configured via cloudflared
            cmd = [
                "cloudflared", "tunnel",
                "--no-autoupdate",
                "run", tunnel_name,
            ]
            # Named tunnels log the URL differently; may need custom regex
            url_regex = r"(https://[\w.-]+)"
        else:
            # Quick tunnel — random trycloudflare.com URL
            cmd = [
                "cloudflared", "tunnel",
                "--no-autoupdate",
                "--url", "%s://localhost:%s" % (scheme, port),
                "--no-tls-verify",
            ]
            url_regex = r"(https://[\w-]+\.trycloudflare\.com)"

        return cmd, url_regex

    def get_known_url(self, config):
        """For named tunnels, the public URL may be known in advance."""
        tunnel_name = config.get("tunnel_name", "")
        public_url = config.get("public_url", "")
        if tunnel_name and public_url:
            return public_url
        return None

    def parse_line(self, line):
        return None

    def pre_start(self, config):
        pass

    def post_stop(self, config):
        pass


class CloudflareModule(ModuleBase):

    def initialize(self, services):
        if hasattr(services, "tunnel_manager"):
            services.tunnel_manager.register_provider(
                "cloudflare", CloudflareProvider())
