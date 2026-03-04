# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert tool definitions to MCP tool schemas."""

import copy


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

    return {
        "name": tool.name,
        "description": tool.description or "",
        "inputSchema": input_schema,
    }
