# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""MCP JSON-RPC protocol module.

Registers MCP routes with the shared HTTP server.
No server management — that's the http module's job.
"""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.mcp")


class MCPModule(ModuleBase):
    """Exposes tools via MCP JSON-RPC routes on the shared HTTP server."""

    def initialize(self, services):
        self._services = services
        self._protocol = None
        self._routes_registered = False

        if services.config.proxy_for(self.name).get("enabled"):
            self._register_routes(services)

        if hasattr(services, "events"):
            services.events.subscribe("config:changed", self._on_config_changed)

    def _on_config_changed(self, **data):
        key = data.get("key", "")
        if not key.startswith("mcp."):
            return
        cfg = self._services.config.proxy_for(self.name)
        enabled = cfg.get("enabled")
        if enabled and not self._routes_registered:
            self._register_routes(self._services)
        elif not enabled and self._routes_registered:
            self._unregister_routes(self._services)

    def _register_routes(self, services):
        from plugin.modules.mcp.protocol import MCPProtocolHandler

        self._protocol = MCPProtocolHandler(services)
        routes = services.http_routes
        p = self._protocol

        # MCP streamable-http (raw — JSON-RPC + custom headers + SSE)
        routes.add("POST", "/mcp", p.handle_mcp_post, raw=True)
        routes.add("GET", "/mcp", p.handle_mcp_sse, raw=True)
        routes.add("DELETE", "/mcp", p.handle_mcp_delete, raw=True)

        # Legacy SSE transport (raw — streaming)
        routes.add("POST", "/sse", p.handle_sse_post, raw=True)
        routes.add("POST", "/messages", p.handle_sse_post, raw=True)
        routes.add("GET", "/sse", p.handle_sse_stream, raw=True)

        self._routes_registered = True
        log.info("MCP routes registered")

    def _unregister_routes(self, services):
        routes = services.http_routes
        for method, path in [
            ("POST", "/mcp"), ("GET", "/mcp"), ("DELETE", "/mcp"),
            ("POST", "/sse"), ("POST", "/messages"), ("GET", "/sse"),
        ]:
            routes.remove(method, path)
        self._routes_registered = False
        self._protocol = None
        log.info("MCP routes unregistered")

    def shutdown(self):
        if self._routes_registered:
            try:
                self._unregister_routes(self._services)
            except Exception:
                log.exception("Error unregistering MCP routes")
