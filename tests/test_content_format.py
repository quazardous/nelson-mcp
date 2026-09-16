# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Which filter imports an agent's content, and which format it reads (#2650)."""

import pytest

from plugin.modules.writer import format_support as fs


@pytest.mark.parametrize("content, expected", [
    ("<h1>Title</h1><p>body</p>", "html"),
    ("<p>price < 10 and # of items</p>", "html"),
    ("# Title\n\nSome **bold** text.", "markdown"),
    ("- one\n- two", "markdown"),
    ("1. first\n2. second", "markdown"),
    ("| a | b |\n|---|---|\n| 1 | 2 |", "markdown"),
    ("See [the docs](https://example.org).", "markdown"),
    ("Use `code` here.", "markdown"),
    ("Just a sentence.", None),
    ("a < b and c > d", None),
    ("Price: 5 * 3 = 15", None),
    ("", None),
])
def test_detects_the_content_format(content, expected):
    assert fs.detect_content_format(content) == expected


def test_an_explicit_format_wins_over_detection():
    assert fs.resolve_import_format("<p>x</p>", "markdown") == "markdown"
    assert fs.resolve_import_format("# x", "html") == "html"


def test_markdown_is_never_sent_to_the_html_filter():
    # #2635: the filter used to come from the global setting (html).
    assert fs.resolve_import_format("# Report\n\n**4.2 M**") == "markdown"


def test_plain_text_keeps_the_html_path():
    assert fs.resolve_import_format("line one\n\nline two") == "html"


class Config:
    def __init__(self, value):
        self.value = value

    def get(self, key, caller_module=None):
        assert key == "core.document_format"
        return self.value


def test_export_format_prefers_the_call_then_the_setting():
    assert fs.resolve_export_format(Config("markdown")) == "markdown"
    assert fs.resolve_export_format(Config("markdown"), "html") == "html"
    assert fs.resolve_export_format(Config("bogus")) == "html"
    assert fs.resolve_export_format(None) == "html"
