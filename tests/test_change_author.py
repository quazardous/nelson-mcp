# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Signing the agent's tracked changes with writer.change_author (#2636)."""

import json

import pytest

from plugin.modules.writer import change_author as ca


class Config:
    def __init__(self, **values):
        self.values = {"writer." + k: v for k, v in values.items()}
        self.history = []

    def get(self, key, caller_module=None):
        return self.values.get(key, "")

    def set(self, key, value, caller_module=None):
        self.values[key] = value
        self.history.append((key, value))


class Profile:
    def __init__(self, **values):
        self.values = {k: "" for k in ca.NAME_KEYS}
        self.values.update(values)
        self.commits = []

    def getPropertyValue(self, key):
        return self.values[key]

    def setPropertyValue(self, key, value):
        self.values[key] = value

    def commitChanges(self):
        self.commits.append(dict(self.values))


class WriterDoc:
    def __init__(self, recording=True):
        self.recording = recording

    def supportsService(self, name):
        return name == "com.sun.star.text.TextDocument"

    def getPropertyValue(self, name):
        assert name == "RecordChanges"
        return self.recording


def service(config, profile):
    svc = ca.ChangeAuthor(config)
    svc._profile = lambda: profile
    return svc


def test_plan_writes_only_what_differs():
    changes, original = ca.plan_swap(
        {"givenname": "Ana", "sn": "", "fathersname": ""}, "AI agent")
    assert changes == {"givenname": "AI agent"}
    assert original == {"givenname": "Ana"}
    changes, original = ca.plan_swap(
        {"givenname": "Ana", "sn": "Lopez", "fathersname": ""}, "AI agent")
    assert changes == {"givenname": "AI agent", "sn": ""}
    assert original == {"givenname": "Ana", "sn": "Lopez"}


def test_swaps_during_the_call_and_restores_after():
    cfg, prof = Config(change_author="AI agent"), Profile(givenname="Ana",
                                                          sn="Lopez")
    with service(cfg, prof).signing(WriterDoc()) as name:
        assert name == "AI agent"
        assert prof.values == {"givenname": "AI agent", "sn": "",
                               "fathersname": ""}
        assert json.loads(cfg.values["writer.change_author_restore"]) == \
            {"givenname": "Ana", "sn": "Lopez"}
    assert prof.values == {"givenname": "Ana", "sn": "Lopez",
                           "fathersname": ""}
    assert cfg.values["writer.change_author_restore"] == ""


def test_restores_when_the_tool_raises():
    cfg, prof = Config(change_author="AI agent"), Profile(givenname="Ana")
    with pytest.raises(RuntimeError):
        with service(cfg, prof).signing(WriterDoc()):
            raise RuntimeError("tool failed")
    assert prof.values["givenname"] == "Ana"
    assert cfg.values["writer.change_author_restore"] == ""


@pytest.mark.parametrize("cfg, doc", [
    (Config(change_author=""), WriterDoc()),          # not configured
    (Config(change_author="AI agent"), WriterDoc(recording=False)),
    (Config(change_author="AI agent"), None),
])
def test_leaves_the_profile_alone_otherwise(cfg, doc):
    prof = Profile(givenname="Ana")
    with service(cfg, prof).signing(doc) as name:
        assert name is None
    assert prof.commits == [] and cfg.history == []


def test_recover_puts_the_name_back_after_a_crash():
    cfg = Config(change_author="AI agent",
                 change_author_restore=json.dumps({"givenname": "Ana"}))
    prof = Profile(givenname="AI agent")
    assert service(cfg, prof).recover() is True
    assert prof.values["givenname"] == "Ana"
    assert cfg.values["writer.change_author_restore"] == ""
    assert service(cfg, prof).recover() is False


def test_signing_name_falls_back_to_the_user_then_unknown():
    assert service(Config(change_author="Bot"), Profile()).signing_name() \
        == "Bot"
    assert service(Config(), Profile(givenname="Ana", sn="Lopez")) \
        .signing_name() == "Ana Lopez"
    assert service(Config(), Profile()).signing_name() == ca.UNKNOWN_AUTHOR
