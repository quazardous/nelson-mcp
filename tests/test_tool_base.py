# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for plugin.framework.tool_base."""

import pytest

from plugin.framework.tool_base import (
    ToolBase, TOOL_GROUPS, _GROUP_BY_PREFIX)


class ReadTool(ToolBase):
    name = "get_something"
    description = "Reads something"
    parameters = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class WriteTool(ToolBase):
    name = "apply_content"
    description = "Writes content"
    parameters = {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
    }

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class ExplicitMutationTool(ToolBase):
    name = "get_but_actually_writes"
    is_mutation = True
    parameters = {}

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class NoParamsTool(ToolBase):
    name = "do_thing"
    parameters = None

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class TestDetectsMutation:
    def test_read_prefix_not_mutation(self):
        for prefix in ("get_", "read_", "list_", "find_", "search_", "count_"):
            tool = ReadTool()
            tool.name = f"{prefix}something"
            assert tool.detects_mutation() is False

    def test_write_prefix_is_mutation(self):
        t = WriteTool()
        assert t.detects_mutation() is True

    def test_explicit_override(self):
        t = ExplicitMutationTool()
        assert t.detects_mutation() is True

    def test_no_name_defaults_to_mutation(self):
        t = WriteTool()
        t.name = None
        assert t.detects_mutation() is True


class TestValidate:
    def test_valid_params(self):
        t = ReadTool()
        ok, err = t.validate(id="abc")
        assert ok is True
        assert err is None

    def test_missing_required(self):
        t = ReadTool()
        ok, err = t.validate()
        assert ok is False
        assert "Missing required" in err

    def test_unknown_param(self):
        t = ReadTool()
        ok, err = t.validate(id="abc", bogus="x")
        assert ok is False
        assert "Unknown parameter" in err

    def test_no_schema_accepts_anything(self):
        t = NoParamsTool()
        ok, err = t.validate(anything="goes")
        assert ok is True


# ── Tool grouping ─────────────────────────────────────────────────────


class TestToolGroup:
    """The group is derived from the name, so it cannot drift out of date.

    Its predecessor, a hand-written `intent`, was read by nothing and had
    rotted: a quarter of the tools carried none, and the document lifecycle
    tools were all tagged "media" (#27).
    """

    def _tool(self, name, **attrs):
        ns = {"name": name, "description": "", "parameters": None,
              "execute": lambda self, ctx, **kw: {"status": "ok"}}
        ns.update(attrs)
        return type("T", (ToolBase,), ns)()

    def test_group_comes_from_the_name_prefix(self):
        assert self._tool("doc_save").tool_group() == "document"
        assert self._tool("text_read").tool_group() == "text"
        assert self._tool("nav_outline").tool_group() == "navigate"
        assert self._tool("comment_add").tool_group() == "review"
        assert self._tool("image_insert").tool_group() == "media"
        assert self._tool("calc_sheet").tool_group() == "calc"
        assert self._tool("job_get").tool_group() == "system"

    def test_document_lifecycle_is_not_media(self):
        # The exact mis-tagging that made the old metadata useless.
        for name in ("doc_open", "doc_create", "doc_close", "doc_list_open"):
            assert self._tool(name).tool_group() == "document"

    def test_an_explicit_group_wins(self):
        assert self._tool("text_thing", group="review").tool_group() == "review"

    def test_an_unmapped_prefix_falls_back(self):
        assert self._tool("wibble_thing").tool_group() == "other"

    def test_every_group_is_declared(self):
        for prefix, group in _GROUP_BY_PREFIX.items():
            assert group in TOOL_GROUPS, "%s -> unknown group %s" % (prefix, group)


class TestEveryRealToolIsGrouped:
    """Scan the source so a new tool cannot land in 'other' unnoticed.

    Static on purpose: importing the tool modules needs UNO, which is not
    available here, and the check only needs the declared names.
    """

    def _declared_names(self):
        import os
        import re
        root = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "plugin", "modules")
        names = []
        for dirpath, _dirs, files in os.walk(root):
            if "tools" not in dirpath.split(os.sep):
                continue
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                with open(os.path.join(dirpath, fname), encoding="utf-8") as f:
                    names += re.findall(r'^\s*name = "([a-z0-9_]+)"', f.read(),
                                        re.M)
        return names

    def test_names_were_found(self):
        assert len(self._declared_names()) > 100, "the scan found nothing"

    def test_every_prefix_is_mapped(self):
        unmapped = sorted({
            n for n in self._declared_names()
            if n.split("_", 1)[0] not in _GROUP_BY_PREFIX})
        assert not unmapped, (
            "these tools have no group — add their prefix to "
            "_GROUP_BY_PREFIX in tool_base.py, or rename them to an "
            "existing domain: %s" % ", ".join(unmapped))
