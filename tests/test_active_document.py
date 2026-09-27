# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What counts as the active document (GitHub #43).

The desktop's current component is not always a document: with no file
open, the Start Center's own component answers getCurrentComponent(). It
has no URL and no document type, so /health advertised a document that no
tool could use.
"""

import pytest

from plugin.modules.core.services.document import DocumentService
from plugin.modules.mcp.active_doc import ActiveDocumentWatcher


class Component:
    """A pyuno-ish component that answers supportsService()."""

    def __init__(self, *services):
        self.services = services

    def supportsService(self, name):
        return name in self.services


WRITER = ("com.sun.star.document.OfficeDocument",
          "com.sun.star.text.TextDocument")
# sfx2 BackingComp: the Start Center, a controller with no model.
START_CENTER = ("com.sun.star.frame.StartModule",
                "com.sun.star.frame.ProtocolHandler")


class Desktop:
    def __init__(self, current):
        self.current = current

    def getCurrentComponent(self):
        return self.current


@pytest.fixture
def svc():
    DocumentService._pinned = None
    service = DocumentService()
    yield service
    DocumentService._pinned = None


def active(svc, current):
    svc._desktop = Desktop(current)
    return svc.get_active_document()


def test_a_document_is_the_active_document(svc):
    doc = Component(*WRITER)
    assert active(svc, doc) is doc


def test_the_start_center_is_not_a_document(svc):
    assert active(svc, Component(*START_CENTER)) is None


def test_nothing_current_and_nothing_uno_give_nothing(svc):
    assert active(svc, None) is None
    assert active(svc, object()) is None


def test_is_document_covers_every_type_including_base_and_math(svc):
    for extra in ("com.sun.star.text.TextDocument",
                  "com.sun.star.sheet.SpreadsheetDocument",
                  "com.sun.star.presentation.PresentationDocument",
                  "com.sun.star.formula.FormulaProperties",
                  "com.sun.star.sdb.OfficeDatabaseDocument"):
        doc = Component("com.sun.star.document.OfficeDocument", extra)
        assert svc.is_document(doc), extra
    assert not svc.is_document(Component(*START_CENTER))


def test_health_reports_no_document_over_the_start_center(svc):
    """The snapshot /health reads, refreshed on the Start Center."""
    svc._desktop = Desktop(Component(*START_CENTER))
    watcher = ActiveDocumentWatcher(svc)
    watcher.refresh()
    state = watcher.snapshot()
    assert state["known"] is True
    assert state["available"] is False
    assert state["doc_type"] is None
    assert state["doc_id"] is None
