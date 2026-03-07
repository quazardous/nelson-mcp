# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Debug tools module — conditional diagnostics menu and HTTP API.

The /debug HTTP endpoint is gated by debug.enable_api (disabled by
default).  It exposes eval, exec, call_tool, trigger, services, and
config actions for testing and development.
"""

import logging
import time

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.debug")


class DebugModule(ModuleBase):
    """Provides debug actions when debug.enabled is true,
    and an HTTP debug API when debug.enable_api is true."""

    def initialize(self, services):
        self._services = services
        self._routes_registered = False

        cfg = services.config.proxy_for(self.name)
        if cfg.get("enable_api"):
            self._register_routes(services)

        if hasattr(services, "events"):
            services.events.subscribe("config:changed", self._on_config_changed)

    def _on_config_changed(self, **data):
        key = data.get("key", "")
        if key == "debug.enable_api":
            cfg = self._services.config.proxy_for(self.name)
            if cfg.get("enable_api") and not self._routes_registered:
                self._register_routes(self._services)
            elif not cfg.get("enable_api") and self._routes_registered:
                self._unregister_routes(self._services)

    # ── HTTP route management ────────────────────────────────────────

    def _register_routes(self, services):
        routes = services.http_routes
        routes.add("GET", "/api/debug", self._handle_debug_get)
        routes.add("POST", "/api/debug", self._handle_debug_post, raw=True)
        self._routes_registered = True
        log.info("Debug API routes enabled")

    def _unregister_routes(self, services):
        routes = services.http_routes
        routes.remove("GET", "/api/debug")
        routes.remove("POST", "/api/debug")
        self._routes_registered = False
        log.info("Debug API routes disabled")

    # ── Menu actions ─────────────────────────────────────────────────

    def on_action(self, action):
        cfg = self._services.config.proxy_for(self.name)
        if not cfg.get("enabled"):
            from plugin.framework.uno_context import get_ctx
            from plugin.framework.dialogs import msgbox
            msgbox(get_ctx(), "Debug",
                   "Enable debug in Options > Nelson MCP > Debug")
            return

        if action == "debug_info":
            self._show_debug_info()
        else:
            super().on_action(action)

    def _show_debug_info(self):
        """Show system info in a message box."""
        from plugin.framework.uno_context import get_ctx
        from plugin.framework.dialogs import msgbox
        from plugin.version import EXTENSION_VERSION

        ctx = get_ctx()
        lines = ["Nelson MCP v%s" % EXTENSION_VERSION, ""]

        # Registered services
        svc_names = sorted(self._services.service_names)
        lines.append("Services: %s" % ", ".join(svc_names))

        # Document info
        doc_svc = self._services.get("document")
        if doc_svc:
            doc = doc_svc.get_active_document()
            if doc:
                doc_type = doc_svc.detect_doc_type(doc) or "unknown"
                doc_len = doc_svc.get_document_length(doc)
                lines.append("")
                lines.append("Document: %s (%d chars)" % (doc_type, doc_len))

        # HTTP routes
        routes = self._services.get("http_routes")
        if routes:
            lines.append("")
            lines.append("HTTP routes: %d" % routes.route_count)
            for method, path in sorted(routes.list_routes()):
                lines.append("  %s %s" % (method, path))

        # Tools
        tools = self._services.get("tools")
        if tools:
            tool_names = sorted(tools.list_tool_names())
            lines.append("")
            lines.append("Tools (%d): %s" % (
                len(tool_names), ", ".join(tool_names[:20])))
            if len(tool_names) > 20:
                lines.append("  ... and %d more" % (len(tool_names) - 20))

        msgbox(ctx, "Nelson MCP Debug Info", "\n".join(lines))

    # ── HTTP handlers ────────────────────────────────────────────────

    def _handle_debug_get(self, body, headers, query):
        """GET /debug — show available debug actions and tools."""
        tools_svc = self._services.get("tools")
        tools = sorted(tools_svc.list_tool_names()) if tools_svc else []
        return (200, {
            "debug": True,
            "usage": "POST /debug with JSON body",
            "actions": {
                "eval": {
                    "description": "Evaluate a Python expression",
                    "body": {"action": "eval", "code": "1 + 1"},
                },
                "exec": {
                    "description": "Execute Python code (result in _result var)",
                    "body": {"action": "exec", "code": "_result = 'hello'"},
                },
                "call_tool": {
                    "description": "Call a registered tool",
                    "body": {"action": "call_tool", "tool": "get_document_info", "args": {}},
                },
                "trigger": {
                    "description": "Simulate a menu trigger command",
                    "body": {"action": "trigger", "command": "settings"},
                },
                "services": {
                    "description": "List registered services",
                    "body": {"action": "services"},
                },
                "config": {
                    "description": "Get/set config values",
                    "body": {"action": "config", "key": "mcp.port", "value": None},
                },
            },
            "tools": tools,
        })

    def _handle_debug_post(self, handler):
        """POST /debug — execute debug actions."""
        body = self._read_body(handler)
        if body is None:
            return
        action = body.get("action", "")
        try:
            if action == "eval":
                result = self._debug_eval(body.get("code", ""))
            elif action == "exec":
                result = self._debug_exec(body.get("code", ""))
            elif action == "call_tool":
                result = self._debug_call_tool(
                    body.get("tool", ""), body.get("args", {}))
            elif action == "trigger":
                result = self._debug_trigger(body.get("command", ""))
            elif action == "services":
                result = self._debug_services()
            elif action == "config":
                result = self._debug_config(
                    body.get("key"), body.get("value", "__NOSET__"))
            else:
                result = {"error": "Unknown action: %s" % action}
            self._send_json(handler, 200, {"ok": True, "result": result})
        except Exception as e:
            log.exception("Debug %s error", action)
            self._send_json(handler, 500, {"ok": False, "error": str(e),
                                           "type": type(e).__name__})

    # ── Debug action implementations ─────────────────────────────────

    def _debug_eval(self, code):
        ns = self._debug_namespace()
        return repr(eval(code, ns))

    def _debug_exec(self, code):
        ns = self._debug_namespace()
        ns["_result"] = None
        exec(code, ns)
        r = ns.get("_result")
        return repr(r) if r is not None else "OK (no _result set)"

    def _debug_call_tool(self, tool_name, arguments):
        if not tool_name:
            return {"error": "Missing 'tool' parameter"}
        from plugin.framework.main_thread import execute_on_main_thread
        result = execute_on_main_thread(
            self._execute_tool_on_main, tool_name, arguments,
            timeout=60.0)
        return result

    def _execute_tool_on_main(self, tool_name, arguments):
        """Execute a tool via the ToolRegistry. Runs on main thread."""
        from plugin.framework.tool_context import ToolContext

        tools_svc = self._services.get("tools")
        if not tools_svc:
            return {"status": "error", "message": "Tool registry not available"}

        doc = None
        doc_type = "writer"
        doc_svc = self._services.get("document")
        if doc_svc:
            try:
                doc = doc_svc.get_active_document()
                if doc:
                    doc_type = doc_svc.detect_doc_type(doc)
            except Exception:
                log.debug("Could not get active document", exc_info=True)

        if doc is None:
            return {"status": "error",
                    "message": "No document open in LibreOffice."}

        ctx = None
        try:
            import uno
            ctx = uno.getComponentContext()
        except ImportError:
            pass

        context = ToolContext(
            doc=doc, ctx=ctx, doc_type=doc_type,
            services=self._services, caller="debug",
        )

        t0 = time.perf_counter()
        result = tools_svc.execute(tool_name, context, **arguments)
        elapsed = time.perf_counter() - t0

        if isinstance(result, dict):
            result["_elapsed_ms"] = round(elapsed * 1000, 1)
        return result

    def _debug_trigger(self, command):
        from plugin.main import _modules, get_services
        if command == "settings":
            from plugin.modules.core.settings_dialog import show_settings
            from plugin._manifest import MODULES
            from plugin.framework.main_thread import execute_on_main_thread
            config_svc = get_services().config
            execute_on_main_thread(
                show_settings, None, config_svc, MODULES,
                timeout=120.0)
            return "Settings dialog shown"
        return {"triggered": command, "note": "Use menu for UI commands"}

    def _debug_services(self):
        return sorted(self._services.service_names)

    def _debug_config(self, key, value):
        config_svc = self._services.get("config")
        if not config_svc:
            return {"error": "No config service"}
        if key is None:
            return config_svc.get_dict()
        if value == "__NOSET__":
            return {key: config_svc.get(key)}
        config_svc.set(key, value)
        return {key: value, "persisted": True}

    def _debug_namespace(self):
        """Build a namespace for eval/exec with useful references."""
        import plugin.main as main_mod
        ns = {
            "services": self._services,
            "tools": self._services.get("tools"),
            "events": self._services.get("events"),
            "modules": getattr(main_mod, "_modules", []),
            "log": log,
        }
        try:
            import uno
            ns["uno"] = uno
            ns["ctx"] = uno.getComponentContext()
        except ImportError:
            pass
        return ns

    # ── HTTP utility methods ─────────────────────────────────────────

    def _read_body(self, handler):
        from plugin.framework.http_server import read_json_body
        return read_json_body(handler)

    def _send_json(self, handler, status, data):
        from plugin.framework.http_server import send_json
        send_json(handler, status, data)
