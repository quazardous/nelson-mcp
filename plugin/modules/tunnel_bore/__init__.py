# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bore tunnel provider — bore.pub relay."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.tunnel.bore")


class BoreProvider:
    """Bore tunnel: exposes a local port via a bore relay server."""

    name = "bore"
    binary_name = "bore"
    version_args = ["bore", "--version"]
    install_url = "https://github.com/ekzhang/bore/releases"

    def build_command(self, port, scheme, config):
        server = config.get("server", "bore.pub")
        cmd = ["bore", "local", str(port), "--to", server]
        # bore outputs "listening at <host>:<port>"
        url_regex = r"listening at ([\w.\-]+:\d+)"
        return cmd, url_regex

    def parse_line(self, line):
        return None

    def pre_start(self, config):
        pass

    def post_stop(self, config):
        pass


class BoreModule(ModuleBase):

    def initialize(self, services):
        if hasattr(services, "tunnel_manager"):
            services.tunnel_manager.register_provider("bore", BoreProvider())
