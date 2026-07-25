# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for plugin.framework.tool_registry."""

import pytest

from plugin.framework.tool_base import ToolBase
from plugin.framework.tool_context import ToolContext
from plugin.framework.tool_registry import ToolRegistry
from plugin.framework.service_registry import ServiceRegistry


class FakeTool(ToolBase):
    name = "fake_tool"
    description = "A fake tool"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        return {"status": "ok", "text": kwargs["text"]}


class AllDocTool(ToolBase):
    name = "universal_tool"
    description = "Works everywhere"
    parameters = {"type": "object", "properties": {}}
    doc_types = None

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class FailingTool(ToolBase):
    name = "fail_tool"
    description = "Always fails"
    parameters = {"type": "object", "properties": {}}

    def execute(self, ctx, **kwargs):
        raise RuntimeError("intentional failure")


def _make_registry(*tools):
    services = ServiceRegistry()
    reg = ToolRegistry(services)
    for t in tools:
        reg.register(t)
    return reg


def _make_ctx(doc_type="writer"):
    return ToolContext(
        doc=None, ctx=None, doc_type=doc_type,
        services=ServiceRegistry(), caller="test"
    )


class TestRegister:
    def test_register_and_get(self):
        reg = _make_registry(FakeTool())
        assert reg.get("fake_tool") is not None
        assert reg.get("missing") is None

    def test_tool_names(self):
        reg = _make_registry(FakeTool(), AllDocTool())
        assert set(reg.tool_names) == {"fake_tool", "universal_tool"}

    def test_len(self):
        reg = _make_registry(FakeTool(), AllDocTool())
        assert len(reg) == 2


class TestDocTypeFiltering:
    def test_tools_for_writer(self):
        reg = _make_registry(FakeTool(), AllDocTool())
        names = [t.name for t in reg.tools_for_doc_type("writer")]
        assert "fake_tool" in names
        assert "universal_tool" in names

    def test_tools_for_calc_excludes_writer_only(self):
        reg = _make_registry(FakeTool(), AllDocTool())
        names = [t.name for t in reg.tools_for_doc_type("calc")]
        assert "fake_tool" not in names
        assert "universal_tool" in names

    def test_tools_for_none_returns_universal_only(self):
        """When doc_type is None (unknown), only universal tools are returned."""
        reg = _make_registry(FakeTool(), AllDocTool())
        names = [t.name for t in reg.tools_for_doc_type(None)]
        assert names == ["universal_tool"]


class TestExecute:
    def test_successful_execution(self):
        reg = _make_registry(FakeTool())
        ctx = _make_ctx("writer")
        result = reg.execute("fake_tool", ctx, text="hello")
        assert result == {"status": "ok", "text": "hello"}

    def test_unknown_tool_raises(self):
        reg = _make_registry()
        ctx = _make_ctx()
        with pytest.raises(KeyError, match="Unknown tool"):
            reg.execute("nope", ctx)

    # Failures are reported as structured MCP errors rather than
    # exceptions, so a client gets a machine-readable code and knows
    # whether retrying is worth it.

    def test_incompatible_doc_type_returns_error(self):
        reg = _make_registry(FakeTool())
        result = reg.execute("fake_tool", _make_ctx("calc"), text="x")
        assert result["status"] == "error"
        assert result["code"] == "incompatible_doc_type"
        assert "requires writer" in result["message"]
        assert result["retryable"] is False
        assert "hint" in result

    def test_validation_failure_returns_error(self):
        reg = _make_registry(FakeTool())
        result = reg.execute("fake_tool", _make_ctx("writer"))  # no 'text'
        assert result["status"] == "error"
        assert result["code"] == "invalid_params"
        assert "Missing required parameter: text" in result["message"]
        assert result["retryable"] is False

    def test_execution_failure_returns_error(self):
        reg = _make_registry(FailingTool())
        result = reg.execute("fail_tool", _make_ctx("writer"))
        assert result["status"] == "error"
        assert result["code"] == "execution_error"
        assert "intentional failure" in result["message"]
        # A crash inside a tool may be transient, unlike a bad request.
        assert result["retryable"] is True


class TestSchemas:
    def test_mcp_schemas(self):
        reg = _make_registry(FakeTool())
        schemas = reg.get_mcp_schemas("writer")
        assert len(schemas) == 1
        s = schemas[0]
        assert s["name"] == "fake_tool"
        assert "inputSchema" in s


# ── Aliases and merged tools ──────────────────────────────────────────


class RenamedTool(ToolBase):
    """A tool that used to be called by another name."""

    name = "image_list"
    aliases = ["list_images"]
    description = "Renamed tool"
    parameters = {"type": "object", "properties": {}}
    doc_types = None
    is_mutation = False

    def execute(self, ctx, **kwargs):
        return {"status": "ok", "seen": kwargs}


class MergedTool(ToolBase):
    """Several former tools behind one name and an action argument."""

    name = "table_structure"
    aliases = {
        "add_table_rows": {"action": "add", "axis": "rows"},
        "delete_table_columns": {"action": "delete", "axis": "columns"},
    }
    description = "Merged tool"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "axis": {"type": "string"},
            "count": {"type": "integer"},
        },
    }
    doc_types = None

    def detects_mutation(self, **kwargs):
        return kwargs.get("action") != "list"

    def execute(self, ctx, **kwargs):
        return {"status": "ok", "seen": kwargs}


class TestAliases:
    def test_alias_resolves_to_the_tool(self):
        reg = _make_registry(RenamedTool())
        assert reg.get("list_images") is reg.get("image_list")

    def test_alias_is_not_advertised(self):
        reg = _make_registry(RenamedTool())
        assert "list_images" not in reg.list_tool_names()
        names = [t.name for t in reg.tools_for_doc_type("writer")]
        assert names == ["image_list"]

    def test_resolve_alias_reports_the_current_name(self):
        reg = _make_registry(RenamedTool())
        assert reg.resolve_alias("list_images") == "image_list"
        assert reg.resolve_alias("image_list") is None

    def test_calling_through_an_alias_works(self):
        reg = _make_registry(RenamedTool())
        result = reg.execute("list_images", _make_ctx())
        assert result["status"] == "ok"

    def test_alias_colliding_with_a_real_tool_is_ignored(self):
        class Collides(ToolBase):
            name = "other"
            aliases = ["image_list"]  # already a registered tool
            description = ""
            parameters = {"type": "object", "properties": {}}

            def execute(self, ctx, **kwargs):
                return {"status": "ok"}

        reg = _make_registry(RenamedTool(), Collides())
        # the real tool wins; the alias never shadows it
        assert reg.get("image_list").name == "image_list"


class TestMergedToolAliases:
    def test_alias_pins_its_arguments(self):
        reg = _make_registry(MergedTool())
        result = reg.execute("add_table_rows", _make_ctx(), count=2)
        assert result["seen"]["action"] == "add"
        assert result["seen"]["axis"] == "rows"
        assert result["seen"]["count"] == 2

    def test_each_alias_pins_its_own_arguments(self):
        reg = _make_registry(MergedTool())
        result = reg.execute("delete_table_columns", _make_ctx(), count=1)
        assert result["seen"]["action"] == "delete"
        assert result["seen"]["axis"] == "columns"

    def test_pinned_arguments_win_over_supplied_ones(self):
        # The old signature could not express action/axis, so a caller
        # cannot legitimately mean something else.
        reg = _make_registry(MergedTool())
        result = reg.execute("add_table_rows", _make_ctx(), action="delete")
        assert result["seen"]["action"] == "add"

    def test_calling_the_merged_name_directly_pins_nothing(self):
        reg = _make_registry(MergedTool())
        result = reg.execute("table_structure", _make_ctx(), action="list")
        assert result["seen"]["action"] == "list"
        assert "axis" not in result["seen"]

    def test_alias_args_only_apply_to_merged_aliases(self):
        reg = _make_registry(RenamedTool(), MergedTool())
        assert reg.alias_args("list_images") == {}
        assert reg.alias_args("add_table_rows") == {
            "action": "add", "axis": "rows"}


class TestPerCallMutationDetection:
    def test_merged_tool_classifies_each_call(self):
        tool = MergedTool()
        assert tool.detects_mutation(action="list") is False
        assert tool.detects_mutation(action="delete") is True

    def test_plain_tool_ignores_the_arguments(self):
        tool = RenamedTool()
        assert tool.detects_mutation() is False
        assert tool.detects_mutation(action="delete") is False

    def test_name_prefix_fallback_still_applies(self):
        class Unflagged(ToolBase):
            name = "get_something"
            description = ""
            parameters = {"type": "object", "properties": {}}

            def execute(self, ctx, **kwargs):
                return {"status": "ok"}

        # is_mutation unset -> inferred from the name prefix
        assert Unflagged().detects_mutation() is False
