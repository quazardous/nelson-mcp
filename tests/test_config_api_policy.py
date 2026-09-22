# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The config API tunes Nelson, but cannot undo what protects it."""

import json

import pytest

from plugin.modules.http.config_api_policy import (
    MASK, is_protected, refused_keys, shown)


@pytest.mark.parametrize("key", [
    "http.auth_token", "http.host", "http.port", "http.allowed_origins",
    "http.enable_config_api", "http.use_ssl", "tunnel.provider",
    "tunnel.ngrok.authtoken", "debug.enable_api", "launcher.terminal",
    "launcher.claude.args", "documents.folder.instances",
    "ai_images.openai.instances", "core.force_track_changes",
])
def test_settings_that_protect_nelson_are_reserved(key):
    assert is_protected(key)


@pytest.mark.parametrize("key", [
    "writer.max_content_chars", "writer.change_author", "calc.max_rows_display",
    "core.document_format", "core.log_level",
    "core.auto_enable_track_changes", "mcp.custom_endpoints",
])
def test_settings_that_tune_behaviour_are_open(key):
    assert not is_protected(key)


def test_a_batch_names_every_reserved_key():
    assert refused_keys({"writer.max_content_chars": 1000,
                         "http.auth_token": "",
                         "launcher.terminal": "sh"}) == [
        "http.auth_token", "launcher.terminal"]
    assert refused_keys({"core.document_format": "html"}) == []


def test_secrets_are_masked_and_unset_ones_stay_empty():
    assert shown("http.auth_token", "s3cret", {"widget": "password"}) == MASK
    assert shown("tunnel.ngrok.authtoken", "abc") == MASK
    assert shown("http.auth_token", "", {"widget": "password"}) == ""
    assert shown("writer.max_content_chars", 50000) == 50000


def test_provider_keys_are_masked_inside_their_entries():
    entries = json.dumps([{"name": "OpenAI", "endpoint": "https://x",
                           "api_key": "sk-123"},
                          {"name": "Local", "endpoint": "http://y",
                           "api_key": ""}])
    out = json.loads(shown("ai_images.openai.instances", entries))
    assert out[0]["api_key"] == MASK and out[0]["endpoint"] == "https://x"
    assert out[1]["api_key"] == ""
    assert shown("mcp.custom_endpoints", "not json") == "not json"
