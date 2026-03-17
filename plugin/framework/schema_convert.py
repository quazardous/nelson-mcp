# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert tool definitions to MCP tool schemas."""

import copy


_DOCUMENT_PARAM = {
    "type": "string",
    "description": (
        "Optional document target. By default, tools operate on the "
        "active document. Use this to target a specific document. "
        "Formats: id:<doc_id>, path:<file_path>, title:<frame_title>, "
        "or a bare 32-char hex doc_id."
    ),
}


def to_mcp_schema(tool):
    """Convert a ToolBase instance to an MCP tools/list schema.

    Returns::

        {
            "name": "get_document_outline",
            "description": "...",
            "inputSchema": { ... JSON Schema ... }
        }
    """
    input_schema = copy.deepcopy(tool.parameters) if tool.parameters else {}
    if "type" not in input_schema:
        input_schema["type"] = "object"

    # Inject _document meta-parameter on all tools that require a document
    if getattr(tool, "requires_doc", True):
        props = input_schema.setdefault("properties", {})
        if "_document" not in props:
            props["_document"] = _DOCUMENT_PARAM

    return {
        "name": tool.name,
        "description": tool.description or "",
        "inputSchema": input_schema,
    }
