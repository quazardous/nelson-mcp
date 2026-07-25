# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""MCP JSON-RPC protocol module.

Registers MCP routes with the shared HTTP server.
No server management — that's the http module's job.
Supports custom filtered endpoints for smaller LLMs.
"""

import json
import logging
import threading

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.mcp")

# Sentinel for "baseline not yet established" in the doc-type poller.
_UNKNOWN = object()

# Tool presets — pre-filled tool lists for common use cases
PRESETS = {
    "writer-edit": [
        "list_open_documents", "get_document_info", "nav_outline",
        "open_document", "create_document", "save_document", "close_document",
        "text_read", "nav_heading_content", "text_find",
        "text_insert", "text_insert_batch", "text_set",
        "text_set_style", "text_delete", "text_duplicate",
        "image_insert", "insert_hyperlink",
        "table_create", "table_write_cell",
        "execute_batch", "undo", "redo",
        "nav_resolve", "get_document_stats",
    ],
    "writer-read": [
        "list_open_documents", "get_document_info", "nav_outline",
        "text_get_range", "text_read", "nav_heading_content",
        "text_find", "text_search", "get_document_stats",
        "image_list", "table_list", "list_comments",
        "nav_resolve", "nav_tree",
    ],
    "calc": [
        "list_open_documents", "get_document_info",
        "open_document", "create_document", "save_document",
        "table_read", "table_write_cell", "table_write_row",
        "create_chart", "table_list",
        "execute_batch", "undo", "redo",
    ],
    "gallery": [
        "gallery_list", "gallery_search", "gallery_get",
        "gallery_providers", "gallery_update",
        "image_insert", "image_list", "image_download",
        "docs_gallery_list", "docs_gallery_search",
    ],
    "minimal": [
        "list_open_documents", "get_document_info",
        "open_document", "create_document", "save_document",
        "text_read", "text_insert",
        "image_insert",
    ],
}


def on_tool_reference():
    """Open the tool reference page in the browser."""
    import webbrowser
    from plugin.main import get_services
    services = get_services()
    if services:
        cfg = services.config.proxy_for("http")
        port = cfg.get("port", 8766)
        webbrowser.open("http://localhost:%s/api/tools" % port)


def on_create_preset():
    """Create a custom endpoint from the selected preset."""
    from plugin.main import get_services
    from plugin.framework.dialogs import msgbox
    from plugin.framework.uno_context import get_ctx

    ctx = get_ctx()
    services = get_services()
    if not services:
        return

    cfg = services.config.proxy_for("mcp")
    preset_name = cfg.get("preset") or "minimal"

    if preset_name not in PRESETS:
        msgbox(ctx, "Nelson", "Unknown preset: %s" % preset_name)
        return

    tools_list = PRESETS[preset_name]
    tools_text = "\n".join(tools_list)

    raw = cfg.get("custom_endpoints") or "[]"
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        items = []

    items.append({
        "name": preset_name,
        "path": "/mcp/%s" % preset_name.replace("-", "/"),
        "tools": tools_text,
    })
    cfg.set("custom_endpoints", json.dumps(items))
    msgbox(ctx, "Nelson",
           "Endpoint '/mcp/%s' created with %d tools.\n"
           "Reopen Options to see it."
           % (preset_name.replace("-", "/"), len(tools_list)))


class MCPModule(ModuleBase):
    """Exposes tools via MCP JSON-RPC routes on the shared HTTP server."""

    def initialize(self, services):
        self._services = services
        self._protocol = None
        self._routes_registered = False
        self._poll_thread = None
        self._poll_stop = None

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

        # Health / readiness probe (raw — custom JSON response)
        routes.add("GET", "/health", p.handle_health, raw=True)

        # Tool reference page (HTML)
        routes.add("GET", "/api/tools", p.handle_tool_reference, raw=True)

        self._routes_registered = True
        self._custom_routes = []
        log.info("MCP routes registered")

        # Register custom filtered endpoints
        self._register_custom_endpoints(services)

        # Watch for active-document-type changes → notify SSE clients so they
        # refetch tools/list (the tool set is filtered by doc type). #24
        self._start_doc_type_poller(services)

    def _register_custom_endpoints(self, services):
        """Register custom filtered MCP endpoints from config."""
        cfg = services.config.proxy_for(self.name)
        raw = cfg.get("custom_endpoints") or "[]"
        try:
            endpoints = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(endpoints, list):
            return

        routes = services.http_routes

        for ep in endpoints:
            name = ep.get("name", "")
            path = ep.get("path", "")
            if not path or not path.startswith("/mcp/"):
                continue
            if not ep.get("enabled", True):
                continue

            # Parse tool filter from textarea (one per line, # comments)
            tools_text = ep.get("tools", "")
            tool_filter = set()
            for line in tools_text.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    tool_filter.add(line)

            if not tool_filter:
                continue  # skip endpoints with no tools defined

            # Create a filtered protocol handler
            from plugin.modules.mcp.protocol import MCPProtocolHandler
            handler = MCPProtocolHandler(services,
                                         tool_filter=tool_filter)

            routes.add("POST", path, handler.handle_mcp_post, raw=True)
            routes.add("GET", path, handler.handle_mcp_sse, raw=True)
            routes.add("DELETE", path, handler.handle_mcp_delete, raw=True)
            self._custom_routes.append(path)
            log.info("Custom MCP endpoint: %s (%s, %d tools)",
                     path, name, len(tool_filter))

    def _start_doc_type_poller(self, services):
        """Poll the active document type and broadcast list_changed on change.

        Only polls while at least one SSE client is connected; re-baselines
        when clients reconnect so a reconnect never spuriously notifies. #24
        """
        from plugin.modules.mcp.protocol import (
            broadcast_notification, _sse_has_clients)

        self._poll_stop = threading.Event()
        stop = self._poll_stop

        def _poll():
            doc_svc = services.document
            last = _UNKNOWN
            while not stop.wait(2.0):
                if not _sse_has_clients():
                    last = _UNKNOWN  # re-baseline on next connect
                    continue
                try:
                    doc = doc_svc.get_active_document()
                    dt = doc_svc.detect_doc_type(doc) if doc else None
                except Exception:
                    continue
                if last is _UNKNOWN:
                    last = dt  # establish baseline, no notification
                    continue
                if dt != last:
                    last = dt
                    n = broadcast_notification(
                        "notifications/tools/list_changed")
                    log.info("Active doc type → %s; notified %d MCP "
                             "client(s)", dt, n)

        self._poll_thread = threading.Thread(
            target=_poll, name="mcp-doctype-poll", daemon=True)
        self._poll_thread.start()

    def _stop_doc_type_poller(self):
        if self._poll_stop is not None:
            self._poll_stop.set()
        self._poll_thread = None
        self._poll_stop = None

    def _unregister_routes(self, services):
        self._stop_doc_type_poller()
        routes = services.http_routes
        for method, path in [
            ("POST", "/mcp"), ("GET", "/mcp"), ("DELETE", "/mcp"),
            ("POST", "/sse"), ("POST", "/messages"), ("GET", "/sse"),
            ("GET", "/health"), ("GET", "/api/tools"),
        ]:
            routes.remove(method, path)
        # Unregister custom endpoints
        for path in getattr(self, "_custom_routes", []):
            for method in ("POST", "GET", "DELETE"):
                routes.remove(method, path)
        self._custom_routes = []
        self._routes_registered = False
        self._protocol = None
        log.info("MCP routes unregistered")

    def shutdown(self):
        if self._routes_registered:
            try:
                self._unregister_routes(self._services)
            except Exception:
                log.exception("Error unregistering MCP routes")
