# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The paths that expose Nelson beyond this machine, and the clients it writes.

A tunnel publishes the server, and its traffic arrives from localhost, so
loopback cannot tell it apart from a local client: without a token it must
not start. And once a token is set, the configs the built-in launchers write
must carry it, or the CLI they start gets 401 on every call.
"""

import json

import pytest

from plugin.modules.launcher_claude import ClaudeProvider
from plugin.modules.launcher_gemini import GeminiProvider
from plugin.modules.launcher_opencode import OpenCodeProvider
from plugin.modules.tunnel import TunnelManager


class _Cfg(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _ConfigSvc:
    def __init__(self, sections):
        self._sections = sections

    def proxy_for(self, name):
        return _Cfg(self._sections.get(name, {}))


class _Events:
    def __init__(self):
        self.emitted = []

    def emit(self, name, **kw):
        self.emitted.append((name, kw))


class _Provider:
    name = "fake"
    version_args = None            # _check_binary passes without a binary

    def __init__(self):
        self.built = False

    def pre_start(self, cfg):
        pass

    def build_command(self, port, scheme, cfg):
        self.built = True
        return ["true"], r"(https://\S+)"


def _manager(token):
    svc = _ConfigSvc({
        "tunnel": {"provider": "fake"},
        "http": {"port": 8766, "auth_token": token},
    })
    events = _Events()
    m = TunnelManager(svc, events)
    provider = _Provider()
    m.register_provider("fake", provider)
    return m, provider, events


class TestTunnelNeedsToken:
    @pytest.mark.parametrize("token", ["", "   ", None])
    def test_refuses_without_token(self, token):
        m, provider, events = _manager(token)
        m.start_tunnel()
        assert not provider.built, "no tunnel command may be built"
        assert not m.is_running
        assert m.last_error and "access token" in m.last_error
        assert ("tunnel:stopped", {"reason": "no access token"}) in events.emitted

    def test_starts_with_token(self, monkeypatch):
        m, provider, _ = _manager("t0ken")
        monkeypatch.setattr(m, "_run_and_parse", lambda *a, **k: None)
        m.start_tunnel()
        assert provider.built
        assert m.last_error is None


URL = "http://localhost:8766"
HEADERS = {"Authorization": "Bearer t0ken"}


def _server(provider, tmp_path, headers):
    provider.setup_env(URL, {}, str(tmp_path), _Cfg(), headers=headers)
    if isinstance(provider, ClaudeProvider):
        return json.load(open(tmp_path / ".mcp.json"))["mcpServers"]["nelson"]
    if isinstance(provider, GeminiProvider):
        return json.load(open(tmp_path / "settings.json"))["mcpServers"]["nelson"]
    return json.load(open(tmp_path / "opencode.json"))["mcp"]["nelson"]


@pytest.mark.parametrize("cls", [ClaudeProvider, GeminiProvider, OpenCodeProvider])
class TestLaunchersCarryToken:
    def test_headers_written_when_token_set(self, cls, tmp_path):
        assert _server(cls(), tmp_path, HEADERS).get("headers") == HEADERS

    def test_no_headers_without_token(self, cls, tmp_path):
        assert "headers" not in _server(cls(), tmp_path, None)
