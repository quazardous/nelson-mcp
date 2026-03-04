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
