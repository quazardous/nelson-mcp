# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Debug tools module — conditional diagnostics menu."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.debug")


class DebugModule(ModuleBase):
    """Provides debug actions when debug.enabled is true."""

    def initialize(self, services):
        self._services = services

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
        svc_names = sorted(self._services.list_services())
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
