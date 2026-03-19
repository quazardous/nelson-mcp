# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Central tool registry with auto-discovery and unified execution."""

import importlib
import inspect
import logging
import os
import pkgutil

from plugin.framework.tool_base import ToolBase
from plugin.framework.schema_convert import to_mcp_schema

log = logging.getLogger("nelson.tools")

_DOC_TYPE_KEYS = frozenset(("writer", "calc", "draw", "impress"))


def _flatten_doc_type_params(kwargs, doc_type):
    """Merge doc-type-specific nested params into top-level kwargs.

    Tools can declare doc-type-specific parameters as nested objects
    (e.g. ``"writer": {"locator": "..."}``).  This function extracts
    the block matching *doc_type*, merges it into the top-level dict,
    and discards blocks for other doc types.

    This lets tool code remain flat — ``kwargs["locator"]`` — while
    the MCP schema clearly groups parameters by document type.
    """
    merged = {}
    for k, v in kwargs.items():
        if k in _DOC_TYPE_KEYS:
            if k == doc_type and isinstance(v, dict):
                merged.update(v)
            # discard other doc-type blocks silently
        else:
            merged[k] = v
    return merged


class ToolRegistry:
    """Discovers, registers, and dispatches tools.

    Tools are auto-discovered from each module's ``tools/`` subpackage
    and registered here.  The MCP server uses this single registry.
    """

    def __init__(self, services):
        self._services = services
        self._tools = {}  # name -> ToolBase instance
        self.batch_mode = False  # suppress per-tool cache invalidation

    # ── Registration ──────────────────────────────────────────────────

    def register(self, tool):
        """Register a single ToolBase instance."""
        if tool.name in self._tools:
            log.warning("Tool already registered, replacing: %s", tool.name)
        self._tools[tool.name] = tool

    def register_many(self, tools):
        for t in tools:
            self.register(t)

    def discover(self, package_path, package_name):
        """Auto-discover ToolBase subclasses in a package directory.

        Scans *package_path* for Python modules, imports them, and
        registers any concrete ToolBase subclass found.

        Args:
            package_path: Filesystem path to the package directory.
            package_name: Dotted Python package name (e.g. "plugin.modules.writer.tools").
        """
        if not os.path.isdir(package_path):
            return

        count = 0
        for importer, modname, ispkg in pkgutil.iter_modules([package_path]):
            if modname.startswith("_"):
                continue
            fqn = f"{package_name}.{modname}"
            try:
                mod = importlib.import_module(fqn)
            except Exception:
                log.exception("Failed to import tool module: %s", fqn)
                continue

            for _attr_name, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(obj, ToolBase)
                    and obj is not ToolBase
                    and getattr(obj, "name", None)
                ):
                    try:
                        instance = obj()
                        self.register(instance)
                        count += 1
                    except Exception:
                        log.exception("Failed to instantiate tool: %s", obj)

        if count:
            log.info("Discovered %d tools from %s", count, package_name)

    # ── Lookup ────────────────────────────────────────────────────────

    def get(self, name):
        """Get a tool by name, or None."""
        return self._tools.get(name)

    def list_tool_names(self):
        """Return all registered tool names."""
        return list(self._tools.keys())

    def tools_for_doc_type(self, doc_type):
        """Return tools compatible with *doc_type* (or all if doc_type is None)."""
        for tool in self._tools.values():
            if tool.doc_types is None or doc_type in tool.doc_types:
                yield tool

    # ── Schema generation ─────────────────────────────────────────────

    def get_mcp_schemas(self, doc_type=None):
        """Return list of MCP tools/list schemas."""
        return [to_mcp_schema(t) for t in self.tools_for_doc_type(doc_type)]

    # ── Execution ─────────────────────────────────────────────────────

    def execute(self, tool_name, ctx, **kwargs):
        """Execute a tool by name.

        Args:
            tool_name: Registered tool name.
            ctx:       ToolContext for this invocation.
            **kwargs:  Tool arguments.

        Returns:
            dict result from the tool.

        Raises:
            KeyError:     Tool not found.
            ValueError:   Validation failed or doc_type incompatible.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Unknown tool: {tool_name}")

        bus = self._services.get("events")

        # Check doc_type compatibility
        if tool.doc_types and ctx.doc_type and ctx.doc_type not in tool.doc_types:
            err_msg = (
                "Tool '%s' requires %s but active document is %s."
                % (tool_name, "/".join(tool.doc_types), ctx.doc_type))
            if bus:
                bus.emit("tool:failed", name=tool_name, error=err_msg,
                         caller=ctx.caller)
            return {
                "status": "error",
                "code": "incompatible_doc_type",
                "message": err_msg,
                "hint": "Open a %s document first." % "/".join(tool.doc_types),
                "retryable": False,
            }

        # Validate parameters (before flattening — schema has nested doc-type objects)
        ok, err = tool.validate(**kwargs)
        if not ok:
            if bus:
                bus.emit("tool:failed", name=tool_name, error=err,
                         caller=ctx.caller)
            return {
                "status": "error",
                "code": "invalid_params",
                "message": err,
                "retryable": False,
            }

        # Flatten doc-type-specific nested params
        kwargs = _flatten_doc_type_params(kwargs, ctx.doc_type)

        # Emit executing event
        if bus:
            bus.emit("tool:executing", name=tool_name, caller=ctx.caller,
                     kwargs=kwargs)

        # Cache invalidation moved AFTER execution (see below)

        # Auto-enable track changes for MCP mutations
        if (tool.detects_mutation() and ctx.caller == "mcp"
                and ctx.doc is not None
                and tool_name != "set_track_changes"):
            self._ensure_track_changes(ctx.doc)

        # Wrap mutations in an undo context so Ctrl+Z works
        undo_mgr = None
        if tool.detects_mutation() and ctx.doc is not None:
            try:
                undo_mgr = ctx.doc.getUndoManager()
                undo_mgr.enterUndoContext("Nelson: %s" % tool_name)
            except Exception:
                undo_mgr = None

        try:
            result = tool.execute(ctx, **kwargs)
        except Exception as exc:
            if undo_mgr:
                try:
                    undo_mgr.leaveUndoContext()
                except Exception:
                    pass
            log.exception("Tool execution failed: %s", tool_name)
            if bus:
                bus.emit("tool:failed", name=tool_name, error=str(exc), caller=ctx.caller)
            return {
                "status": "error",
                "code": "execution_error",
                "message": str(exc),
                "retryable": True,
            }

        if undo_mgr:
            try:
                undo_mgr.leaveUndoContext()
            except Exception:
                pass

        if bus:
            bus.emit("tool:completed", name=tool_name, caller=ctx.caller,
                     result=result, is_mutation=tool.detects_mutation(),
                     doc=ctx.doc)

        # Invalidate cache AFTER execution so the tool uses valid data
        # and the next tool gets a fresh scan
        if tool.detects_mutation() and not self.batch_mode:
            doc_svc = self._services.get("document")
            if doc_svc:
                doc_svc.invalidate_cache(ctx.doc)

        return result

    def _ensure_track_changes(self, doc):
        """Enable RecordChanges if force_track_changes config is on."""
        try:
            cfg_svc = self._services.get("config")
            if cfg_svc is None:
                return
            if not cfg_svc.proxy_for("core").get("force_track_changes"):
                return
            if not hasattr(doc, "getPropertyValue"):
                return
            if not doc.getPropertyValue("RecordChanges"):
                doc.setPropertyValue("RecordChanges", True)
                log.info("Track changes auto-enabled (force_track_changes)")
        except Exception:
            pass  # non-writer docs or missing property

    @property
    def tool_names(self):
        return list(self._tools.keys())

    def __len__(self):
        return len(self._tools)
