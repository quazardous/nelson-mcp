# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for plugin.framework.schema_convert."""

from plugin.framework.tool_base import ToolBase
from plugin.framework.schema_convert import to_mcp_schema


class SampleTool(ToolBase):
    name = "sample_tool"
    description = "A sample tool"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Input text"},
        },
        "required": ["text"],
    }

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class MinimalTool(ToolBase):
    name = "minimal"
    description = ""
    parameters = None

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class TestToMcpSchema:
    def test_full_schema(self):
        schema = to_mcp_schema(SampleTool())
        assert schema["name"] == "sample_tool"
        assert schema["description"] == "A sample tool"
        assert schema["inputSchema"]["type"] == "object"
        assert "text" in schema["inputSchema"]["properties"]

    def test_minimal_schema(self):
        schema = to_mcp_schema(MinimalTool())
        assert schema["name"] == "minimal"
        assert schema["inputSchema"]["type"] == "object"

    def test_does_not_mutate_original(self):
        tool = SampleTool()
        original_params = tool.parameters.copy()
        to_mcp_schema(tool)
        assert tool.parameters == original_params


class MultiTypeTool(ToolBase):
    """A tool that groups its options per document type."""

    name = "multi_type"
    description = "Works on several document types"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "writer": {
                "type": "object",
                "properties": {"locator": {"type": "string"}},
            },
            "calc": {
                "type": "object",
                "properties": {"sheet_name": {"type": "string"}},
            },
            "draw": {
                "type": "object",
                "properties": {"page_index": {"type": "integer"}},
            },
        },
    }

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class ScalarNamedLikeADocType(ToolBase):
    """A plain parameter that happens to share a document type's name."""

    name = "scalar_calc"
    description = ""
    parameters = {
        "type": "object",
        "properties": {"calc": {"type": "string"}},
    }

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


def _props(tool, doc_type=None):
    return to_mcp_schema(tool, doc_type)["inputSchema"]["properties"]


class TestDocTypeBlockStripping:
    def test_keeps_only_the_active_document_type_block(self):
        props = _props(MultiTypeTool(), "writer")
        assert "writer" in props
        assert "calc" not in props
        assert "draw" not in props
        assert "path" in props  # shared parameters are untouched

    def test_calc_session_keeps_the_calc_block(self):
        props = _props(MultiTypeTool(), "calc")
        assert "calc" in props
        assert "writer" not in props

    def test_impress_uses_the_draw_block(self):
        props = _props(MultiTypeTool(), "impress")
        assert "draw" in props
        assert "writer" not in props

    def test_unknown_document_type_keeps_everything(self):
        # No document open: the client should still see the full schema.
        props = _props(MultiTypeTool(), None)
        for block in ("writer", "calc", "draw"):
            assert block in props

    def test_a_scalar_sharing_a_block_name_is_never_dropped(self):
        props = _props(ScalarNamedLikeADocType(), "writer")
        assert props["calc"]["type"] == "string"

    def test_stripping_does_not_mutate_the_tool(self):
        tool = MultiTypeTool()
        _props(tool, "writer")
        assert "calc" in tool.parameters["properties"]


class TestDocumentParameter:
    def test_injected_for_tools_needing_a_document(self):
        assert "_document" in _props(SampleTool(), "writer")

    def test_not_injected_when_the_tool_needs_no_document(self):
        class NoDoc(ToolBase):
            name = "no_doc"
            description = ""
            parameters = {"type": "object", "properties": {}}
            requires_doc = False

            def execute(self, ctx, **kwargs):
                return {"status": "ok"}

        assert "_document" not in _props(NoDoc(), "writer")

    def test_description_stays_terse(self):
        # Repeated on ~96 tools, so its length is a real cost.
        desc = _props(SampleTool(), "writer")["_document"]["description"]
        assert len(desc) < 150
