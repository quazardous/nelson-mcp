# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for browser-origin validation in plugin.framework.http_server.

The MCP Streamable HTTP spec requires validating the Origin header on all
incoming connections. Nelson binds to localhost, which protects nothing on
its own: without this check any page the user is visiting can drive
LibreOffice through the MCP endpoint and read the answer.
"""

import pytest

from plugin.framework import http_server
from plugin.framework.http_server import (
    origin_allowed,
    send_cors_headers,
    set_allowed_origins,
)


class _FakeHeaders(dict):
    """Header bag with the case-insensitive get() the handler relies on."""

    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeHandler:
    def __init__(self, origin=None):
        self.headers = _FakeHeaders({"Origin": origin} if origin else {})
        self.sent = []

    def send_header(self, key, value):
        self.sent.append((key, value))

    def header(self, key):
        for k, v in self.sent:
            if k.lower() == key.lower():
                return v
        return None


@pytest.fixture(autouse=True)
def _reset_origins():
    """Every test starts from the shipped default: nothing allowed."""
    set_allowed_origins("")
    yield
    set_allowed_origins("")


class TestSetAllowedOrigins:
    def test_default_is_empty(self):
        assert http_server._allowed_origins == frozenset()

    def test_parses_comma_separated_string(self):
        set_allowed_origins("https://a.example, https://b.example")
        assert http_server._allowed_origins == {
            "https://a.example", "https://b.example"}

    def test_strips_whitespace_and_blanks(self):
        set_allowed_origins("  https://a.example ,, ")
        assert http_server._allowed_origins == {"https://a.example"}

    def test_accepts_an_iterable(self):
        set_allowed_origins(["https://a.example"])
        assert http_server._allowed_origins == {"https://a.example"}

    def test_none_clears(self):
        set_allowed_origins("https://a.example")
        set_allowed_origins(None)
        assert http_server._allowed_origins == frozenset()


class TestOriginAllowed:
    def test_no_origin_header_is_allowed(self):
        """An MCP client over plain HTTP sends no Origin — must still work."""
        allowed, origin = origin_allowed(_FakeHandler())
        assert allowed is True
        assert origin is None

    def test_unknown_origin_is_refused_by_default(self):
        allowed, origin = origin_allowed(_FakeHandler("https://evil.example"))
        assert allowed is False
        assert origin == "https://evil.example"

    def test_listed_origin_is_allowed(self):
        set_allowed_origins("https://ok.example")
        allowed, _ = origin_allowed(_FakeHandler("https://ok.example"))
        assert allowed is True

    def test_match_is_exact(self):
        """Scheme, host and port all count — no prefix or suffix matching."""
        set_allowed_origins("https://ok.example")
        for other in ("http://ok.example",
                      "https://ok.example:8443",
                      "https://ok.example.evil.test",
                      "https://notok.example"):
            allowed, _ = origin_allowed(_FakeHandler(other))
            assert allowed is False, other


class TestSendCorsHeaders:
    def test_never_emits_a_wildcard(self):
        set_allowed_origins("https://ok.example")
        for origin in (None, "https://ok.example", "https://evil.example"):
            handler = _FakeHandler(origin)
            send_cors_headers(handler)
            assert handler.header("Access-Control-Allow-Origin") != "*"

    def test_echoes_the_allowed_origin(self):
        set_allowed_origins("https://ok.example")
        handler = _FakeHandler("https://ok.example")
        send_cors_headers(handler)
        assert handler.header("Access-Control-Allow-Origin") == \
            "https://ok.example"
        assert handler.header("Access-Control-Allow-Methods") is not None

    def test_refused_origin_gets_no_allow_origin(self):
        handler = _FakeHandler("https://evil.example")
        send_cors_headers(handler)
        assert handler.header("Access-Control-Allow-Origin") is None
        assert handler.header("Access-Control-Allow-Headers") is None

    def test_no_origin_gets_no_cors_headers(self):
        handler = _FakeHandler()
        send_cors_headers(handler)
        assert handler.header("Access-Control-Allow-Origin") is None

    def test_always_varies_on_origin(self):
        """Responses differ by Origin, so caches must not share them."""
        for origin in (None, "https://ok.example", "https://evil.example"):
            handler = _FakeHandler(origin)
            send_cors_headers(handler)
            assert handler.header("Vary") == "Origin"
