# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert tool definitions to MCP tool schemas."""

import copy


# Repeated on ~96 tools in every tools/list response, so every character
# here costs ~96x. Keep it terse.
_DOCUMENT_PARAM = {
    "type": "string",
    "description": (
        "Optional. Target another document instead of the active one: "
        "id:<doc_id>, path:<file>, or title:<frame>."
    ),
}

# Per-document-type option blocks. A tool that works on several document
# types groups its type-specific options under these keys; only the block
# matching the active document type is worth sending.
_DOC_TYPE_BLOCKS = ("writer", "calc", "draw", "impress")

# Which block a given active document type keeps (Draw and Impress share
# the "draw" block).
_BLOCK_FOR_DOC_TYPE = {
    "writer": "writer",
    "calc": "calc",
    "draw": "draw",
    "impress": "draw",
}


def _strip_off_type_blocks(input_schema, doc_type):
    """Drop type-specific option blocks that cannot apply to *doc_type*.

    With a Writer document active, the ``calc``/``draw`` option blocks of
    a multi-type tool are dead weight in the schema. When *doc_type* is
    unknown (no document open) every block is kept.
    """
    keep = _BLOCK_FOR_DOC_TYPE.get(doc_type)
    if keep is None:
        return
    props = input_schema.get("properties")
    if not props:
        return
    for name in _DOC_TYPE_BLOCKS:
        if name == keep:
            continue
        block = props.get(name)
        # Only drop genuine option blocks, never a same-named scalar param.
        if isinstance(block, dict) and block.get("type") == "object":
            del props[name]


def to_mcp_schema(tool, doc_type=None):
    """Convert a ToolBase instance to an MCP tools/list schema.

    *doc_type* is the active document type, used to drop option blocks
    that cannot apply to it. Pass None to keep the full schema.

    Returns::

        {
            "name": "nav_outline",
            "description": "...",
            "inputSchema": { ... JSON Schema ... }
        }
    """
    input_schema = copy.deepcopy(tool.parameters) if tool.parameters else {}
    if "type" not in input_schema:
        input_schema["type"] = "object"

    _strip_off_type_blocks(input_schema, doc_type)

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
