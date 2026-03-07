# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


_READ_PREFIXES = ("get_", "read_", "list_", "find_", "search_", "count_")


class ToolBase(ABC):
    """Abstract base for every tool exposed to LLM agents and MCP clients.

    Subclasses must set ``name``, ``description``, ``parameters`` and
    implement ``execute``.

    Attributes:
        name:        Unique tool identifier (e.g. "get_document_outline").
        description: Human-readable description shown to LLMs.
        parameters:  JSON Schema dict (MCP ``inputSchema`` format).
        doc_types:   List of supported doc types (["writer"], ["calc"],
                     ["draw"], or None for all types).
        tier:        "core" = always sent to the LLM, "extended" = on demand
                     via the tool broker.  Default "extended".
        intent:      Broker group: "navigate", "edit", "review", or "media".
                     Used by request_tools(intent=...) to load tool groups.
        is_mutation:  Whether the tool mutates the document.  ``None``
                     means auto-detect from name prefix.
        long_running: Hint that the tool may take a while (e.g. image gen).
    """

    name: Optional[str] = None
    description: str = ""
    parameters: Optional[Dict[str, Any]] = None
    doc_types: Optional[List[str]] = None
    tier: str = "extended"
    intent: Optional[str] = None
    is_mutation: Optional[bool] = None
    long_running: bool = False

    def detects_mutation(self) -> bool:
        """Return True if the tool mutates the document."""
        if self.is_mutation is not None:
            return self.is_mutation
        if self.name:
            return not self.name.startswith(_READ_PREFIXES)
        return True

    def validate(self, **kwargs: Any) -> Tuple[bool, Optional[str]]:
        """Validate arguments against ``parameters`` schema.

        Returns:
            (ok, error_message) — ok is True when validation passes.
        """
        schema = self.parameters or {}
        required = schema.get("required", [])
        for key in required:
            if key not in kwargs:
                return False, f"Missing required parameter: {key}"
        props = schema.get("properties", {})
        for key in kwargs:
            if props and key not in props:
                return False, f"Unknown parameter: {key}"
        return True, None

    @abstractmethod
    def execute(self, ctx: Any, **kwargs: Any) -> Dict[str, Any]:
        """Execute the tool.

        Args:
            ctx:    ToolContext with doc, services, caller info.
            **kwargs: Tool arguments (already validated).

        Returns:
            dict with at least ``{"status": "ok"|"error", ...}``.
        """
