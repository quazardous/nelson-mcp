# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the access token and the exposure refusal in http_server.

Nelson gives whoever reaches it read and write access to every open document
and doc_open on any path. Once the server can be reached from beyond this
machine — a non-loopback bind, or a tunnel — a token is the only protection.
"""

import pytest

from plugin.framework import http_server
from plugin.framework.http_server import (
    ExposureRefused,
    HttpServer,
    auth_ok,
    auth_required,
    is_loopback_host,
    set_auth_token,
)


class _FakeHeaders(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeHandler:
    def __init__(self, path="/mcp", authorization=None):
        self.path = path
        self.headers = _FakeHeaders(
            {"Authorization": authorization} if authorization else {})


@pytest.fixture(autouse=True)
def _no_token():
    set_auth_token("")
    yield
    set_auth_token("")


class TestNoToken:
    def test_default_is_open(self):
        """Out of the box nothing changes for local clients."""
        assert auth_required() is False
        assert auth_ok(_FakeHandler()) is True

    def test_whitespace_token_counts_as_none(self):
        set_auth_token("   ")
        assert auth_required() is False
        assert auth_ok(_FakeHandler()) is True


class TestWithToken:
    TOKEN = "s3cr3t-token"

    @pytest.fixture(autouse=True)
    def _token(self):
        set_auth_token(self.TOKEN)

    def test_missing_is_refused(self):
        assert auth_ok(_FakeHandler()) is False

    def test_bearer_header_is_accepted(self):
        assert auth_ok(_FakeHandler(authorization="Bearer %s" % self.TOKEN))

    def test_bearer_scheme_is_case_insensitive(self):
        assert auth_ok(_FakeHandler(authorization="bearer %s" % self.TOKEN))

    def test_wrong_token_is_refused(self):
        assert not auth_ok(_FakeHandler(authorization="Bearer nope"))

    def test_prefix_of_token_is_refused(self):
        assert not auth_ok(_FakeHandler(authorization="Bearer s3cr3t"))

    def test_other_scheme_is_refused(self):
        assert not auth_ok(_FakeHandler(authorization="Basic %s" % self.TOKEN))

    def test_query_token_is_accepted(self):
        """For hosted connectors that only take a URL."""
        assert auth_ok(_FakeHandler(path="/mcp?token=%s" % self.TOKEN))

    def test_wrong_query_token_is_refused(self):
        assert not auth_ok(_FakeHandler(path="/mcp?token=nope"))

    def test_comparison_is_constant_time(self, monkeypatch):
        calls = []
        real = http_server.hmac.compare_digest
        monkeypatch.setattr(http_server.hmac, "compare_digest",
                            lambda a, b: calls.append(1) or real(a, b))
        auth_ok(_FakeHandler(authorization="Bearer %s" % self.TOKEN))
        assert calls, "token must be compared with hmac.compare_digest"


class TestLoopback:
    @pytest.mark.parametrize("host", [
        "localhost", "LOCALHOST", "127.0.0.1", "127.1.2.3", "::1", "[::1]"])
    def test_loopback(self, host):
        assert is_loopback_host(host)

    @pytest.mark.parametrize("host", [
        "0.0.0.0", "::", "192.168.1.10", "example.com", "10.0.0.1"])
    def test_not_loopback(self, host):
        assert not is_loopback_host(host)


class TestExposureRefused:
    def test_non_loopback_without_token_refuses_before_binding(self):
        server = HttpServer(route_registry=None, port=0, host="0.0.0.0")
        with pytest.raises(ExposureRefused):
            server.start()
        assert server._server is None, "must refuse before binding a socket"

    def test_blank_token_still_refuses(self):
        server = HttpServer(route_registry=None, port=0, host="0.0.0.0",
                            auth_token="   ")
        with pytest.raises(ExposureRefused):
            server.start()
