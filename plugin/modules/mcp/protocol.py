# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""MCP JSON-RPC protocol handler.

Pure protocol logic — no HTTP server, no request handler class.
Route handlers are registered with the HTTP route registry by MCPModule.
"""

import json
import logging
import threading
import time
import uuid

from plugin.framework.main_thread import execute_on_main_thread

log = logging.getLogger("nelson.mcp.protocol")

# MCP protocol version we advertise
MCP_PROTOCOL_VERSION = "2025-11-25"

# Backpressure — one tool execution at a time
_tool_semaphore = threading.Semaphore(1)
_WAIT_TIMEOUT = 5.0
_PROCESS_TIMEOUT = 60.0


class BusyError(Exception):
    """The VCL main thread is already processing another tool call."""


# JSON-RPC helpers
def _jsonrpc_ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


# Standard JSON-RPC error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_SERVER_BUSY = -32000
_EXECUTION_TIMEOUT = -32001

# Session management
_mcp_session_id = None


class MCPProtocolHandler:
    """MCP JSON-RPC protocol — route handlers for the HTTP server."""

    def __init__(self, services):
        self.services = services
        self.tool_registry = services.tools
        self.event_bus = getattr(services, "events", None)
        self.version = "unknown"
        try:
            from plugin.version import EXTENSION_VERSION
            self.version = EXTENSION_VERSION
        except ImportError:
            pass

    # ── Raw handlers (receive GenericRequestHandler) ─────────────────

    def handle_mcp_post(self, handler):
        """POST /mcp — MCP streamable-http (JSON-RPC 2.0)."""
        body = self._read_body(handler)
        if body is None:
            return
        self._handle_mcp(body, handler)

    def handle_mcp_sse(self, handler):
        """GET /mcp — SSE notification stream (keepalive)."""
        accept = handler.headers.get("Accept", "")
        if "text/event-stream" not in accept:
            self._send_json(handler, 406, {
                "error": "Not Acceptable: must Accept text/event-stream"})
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        self._send_cors_headers(handler)
        handler.end_headers()
        try:
            while True:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                time.sleep(15)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def handle_mcp_delete(self, handler):
        """DELETE /mcp — session termination."""
        handler.send_response(200)
        self._send_cors_headers(handler)
        handler.end_headers()

    def handle_sse_stream(self, handler):
        """GET /sse — legacy SSE transport (keepalive only)."""
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Connection", "keep-alive")
            handler.send_header("X-Accel-Buffering", "no")
            self._send_cors_headers(handler)
            handler.end_headers()
            log.info("[SSE] GET stream opened")
            while True:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                time.sleep(15)
        except (BrokenPipeError, ConnectionResetError, OSError):
            log.info("[SSE] GET stream disconnected")

    def handle_sse_post(self, handler):
        """POST /sse or /messages — streamable HTTP (same as /mcp)."""
        body = self._read_body(handler)
        if body is None:
            return
        msg = body
        method = msg.get("method", "?") if isinstance(msg, dict) else "batch"
        req_id = msg.get("id") if isinstance(msg, dict) else None
        log.info("[SSE] POST <<< %s (id=%s)", method, req_id)

        result = self._process_jsonrpc(msg)
        if result is None:
            handler.send_response(202)
            self._send_cors_headers(handler)
            handler.end_headers()
            return

        status, response = result
        handler.send_response(status)
        self._send_cors_headers(handler)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        out = json.dumps(response, ensure_ascii=False, default=str)
        log.info("[SSE] POST >>> %s (id=%s) -> %d", method, req_id, status)
        handler.wfile.write(out.encode("utf-8"))

    # ── MCP protocol handler ─────────────────────────────────────────

    def _handle_mcp(self, msg, handler):
        """Route MCP JSON-RPC request(s) — single or batch."""
        global _mcp_session_id

        method = msg.get("method", "?") if isinstance(msg, dict) else "batch"
        req_id = msg.get("id") if isinstance(msg, dict) else None
        log.info("[MCP] <<< %s (id=%s)", method, req_id)

        is_initialize = (isinstance(msg, dict)
                         and msg.get("method") == "initialize")

        # Batch request
        if isinstance(msg, list):
            responses = []
            for item in msg:
                result = self._process_jsonrpc(item)
                if result is not None:
                    _status, response = result
                    responses.append(response)
            if responses:
                self._send_json(handler, 200, responses)
            else:
                handler.send_response(202)
                self._send_cors_headers(handler)
                handler.end_headers()
            return

        # Single request
        result = self._process_jsonrpc(msg)
        if result is None:
            handler.send_response(202)
            self._send_cors_headers(handler)
            if _mcp_session_id:
                handler.send_header("Mcp-Session-Id", _mcp_session_id)
            handler.end_headers()
            return
        status, response = result

        if is_initialize and status == 200:
            _mcp_session_id = str(uuid.uuid4())

        handler.send_response(status)
        self._send_cors_headers(handler)
        handler.send_header("Content-Type", "application/json")
        if _mcp_session_id:
            handler.send_header("Mcp-Session-Id", _mcp_session_id)
        handler.end_headers()
        out = json.dumps(response, ensure_ascii=False, default=str)
        log.info("[MCP] >>> %s (id=%s) -> %d", method, req_id, status)
        handler.wfile.write(out.encode("utf-8"))

    # ── MCP method handlers ──────────────────────────────────────────

    def _mcp_initialize(self, params):
        client_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)
        return {
            "protocolVersion": client_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": "Nelson MCP",
                "version": self.version,
            },
            "instructions": (
                "Nelson MCP — AI document workspace. "
                "WORKFLOW: 1) Use tools to interact with LibreOffice documents. "
                "2) Tools are filtered by document type (writer/calc/draw). "
                "3) All UNO operations run on the main thread for thread safety."
            ),
        }

    def _mcp_ping(self, params):
        return {}

    def _mcp_tools_list(self, params):
        doc_type = self._detect_active_doc_type()
        schemas = self.tool_registry.get_mcp_schemas(doc_type)
        return {"tools": schemas}

    def _mcp_resources_list(self, params):
        return {"resources": []}

    def _mcp_prompts_list(self, params):
        return {"prompts": []}

    def _mcp_tools_call(self, params):
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if not tool_name:
            raise ValueError("Missing 'name' in tools/call params")

        if self.event_bus:
            self.event_bus.emit("mcp:request", tool=tool_name, args=arguments)

        result = self._execute_with_backpressure(tool_name, arguments)

        if self.event_bus:
            snippet = str(result)[:100] if result else ""
            self.event_bus.emit("mcp:result", tool=tool_name,
                                result_snippet=snippet)

        is_error = (isinstance(result, dict)
                    and result.get("status") == "error")
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False,
                                       default=str),
                }
            ],
            "isError": is_error,
        }

    # ── JSON-RPC processing ──────────────────────────────────────────

    def _process_jsonrpc(self, msg):
        """Process a JSON-RPC message.

        Returns (http_status, response_dict) or None for notifications.
        """
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return (400, _jsonrpc_error(
                None, _INVALID_REQUEST, "Invalid JSON-RPC 2.0 request"))

        method = msg.get("method", "")
        params = msg.get("params", {})
        req_id = msg.get("id")

        if req_id is None:
            return None

        handler = {
            "initialize":      self._mcp_initialize,
            "ping":            self._mcp_ping,
            "tools/list":      self._mcp_tools_list,
            "tools/call":      self._mcp_tools_call,
            "resources/list":  self._mcp_resources_list,
            "prompts/list":    self._mcp_prompts_list,
        }.get(method)

        if handler is None:
            return (400, _jsonrpc_error(
                req_id, _METHOD_NOT_FOUND,
                "Unknown method: %s" % method))

        try:
            result = handler(params)
            return (200, _jsonrpc_ok(req_id, result))
        except BusyError as e:
            log.warning("MCP %s: busy (%s)", method, e)
            return (429, _jsonrpc_error(
                req_id, _SERVER_BUSY, str(e),
                {"retryable": True}))
        except TimeoutError as e:
            log.error("MCP %s: timeout (%s)", method, e)
            return (504, _jsonrpc_error(
                req_id, _EXECUTION_TIMEOUT, str(e)))
        except Exception as e:
            log.error("MCP %s error: %s", method, e, exc_info=True)
            return (500, _jsonrpc_error(
                req_id, _INTERNAL_ERROR, str(e)))

    # ── Backpressure execution ───────────────────────────────────────

    def _execute_with_backpressure(self, tool_name, arguments):
        """Execute a tool on the VCL main thread with backpressure."""
        acquired = _tool_semaphore.acquire(timeout=_WAIT_TIMEOUT)
        if not acquired:
            raise BusyError(
                "LibreOffice is busy processing another tool call. "
                "Please wait a moment and retry.")
        try:
            return execute_on_main_thread(
                self._execute_tool_on_main, tool_name, arguments,
                timeout=_PROCESS_TIMEOUT)
        finally:
            _tool_semaphore.release()

    def _execute_tool_on_main(self, tool_name, arguments):
        """Execute a tool via the ToolRegistry. Runs on main thread."""
        from plugin.framework.tool_context import ToolContext

        registry = self.tool_registry
        svc_registry = self.services

        # Resolve active document
        doc = None
        doc_type = "writer"
        try:
            doc_svc = svc_registry.document
            doc = doc_svc.get_active_document()
            if doc:
                doc_type = doc_svc.detect_doc_type(doc)
        except Exception:
            pass

        if doc is None:
            return {"status": "error",
                    "message": "No document open in LibreOffice."}

        # Get UNO context
        ctx = None
        try:
            import uno
            ctx = uno.getComponentContext()
        except Exception:
            pass

        context = ToolContext(
            doc=doc,
            ctx=ctx,
            doc_type=doc_type,
            services=svc_registry,
            caller="mcp",
        )

        t0 = time.perf_counter()
        result = registry.execute(tool_name, context, **arguments)
        elapsed = time.perf_counter() - t0

        if isinstance(result, dict):
            result["_elapsed_ms"] = round(elapsed * 1000, 1)

        return result

    # ── Helpers ───────────────────────────────────────────────────────

    def _detect_active_doc_type(self):
        try:
            doc_svc = self.services.document
            doc = doc_svc.get_active_document()
            if doc:
                return doc_svc.detect_doc_type(doc)
        except Exception:
            pass
        return None

    def _read_body(self, handler):
        from plugin.framework.http_server import read_json_body
        return read_json_body(handler)

    def _send_json(self, handler, status, data):
        from plugin.framework.http_server import send_json
        send_json(handler, status, data)

    def _send_cors_headers(self, handler):
        from plugin.framework.http_server import send_cors_headers
        send_cors_headers(handler)
