# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Field tokens in header_footer_set (#2634)."""

import pytest

from plugin.modules.writer.tools.headers import parse_field_tokens


def test_tokens_become_fields():
    assert parse_field_tokens("Page {page} of {pages}") == [
        ("text", "Page "), ("field", "page"), ("text", " of "),
        ("field", "pages")]


def test_plain_text_and_tabs_are_untouched():
    assert parse_field_tokens("Left\tRight") == [("text", "Left\tRight")]
    assert parse_field_tokens("") == []


def test_doubled_braces_are_literal():
    assert parse_field_tokens("{{page}} is {page}") == [
        ("text", "{page} is "), ("field", "page")]


def test_case_and_spaces_in_tokens():
    assert parse_field_tokens("{ Title }") == [("field", "title")]


def test_unknown_token_is_refused_with_the_known_ones():
    with pytest.raises(ValueError, match=r"\{page\}, \{pages\}"):
        parse_field_tokens("Chapter {chapter}")


def test_lone_brace_stays_text():
    assert parse_field_tokens("a { b") == [("text", "a { b")]
