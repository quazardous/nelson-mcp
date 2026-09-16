# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""DocumentCache keyed by UNO identity, not by proxy id() (#2642)."""

import gc

import pytest

from plugin.modules.core.services.document import DocumentCache


class Proxy:
    """Stands in for a pyuno proxy: a new object per lookup, == by target."""

    def __init__(self, target):
        self.target = target

    def __eq__(self, other):
        return isinstance(other, Proxy) and other.target is self.target

    __hash__ = None


class Model:
    pass


@pytest.fixture(autouse=True)
def clean_registry():
    saved = (DocumentCache._entries, DocumentCache._recent,
             DocumentCache._pending, DocumentCache.on_changed)
    DocumentCache._entries, DocumentCache._recent = [], []
    DocumentCache._pending, DocumentCache.on_changed = [], None
    DocumentCache._ignoring = DocumentCache._deferring = 0
    yield
    (DocumentCache._entries, DocumentCache._recent,
     DocumentCache._pending, DocumentCache.on_changed) = saved


def entry_of(model):
    return DocumentCache._find(model)


def test_new_proxy_of_the_same_document_hits_the_cache():
    doc = Model()
    DocumentCache.get(Proxy(doc)).para_ranges = ["p"]
    assert DocumentCache.get(Proxy(doc)).para_ranges == ["p"]
    assert DocumentCache.key(Proxy(doc)) == DocumentCache.key(Proxy(doc))


def test_reused_id_never_serves_another_document():
    first = Model()
    DocumentCache.get(Proxy(first)).para_ranges = ["first"]
    for _ in range(200):                       # churn ids
        other = Proxy(Model())
        cache = DocumentCache.get(other)
        assert cache.para_ranges is None
        DocumentCache.remove(other)
        del other
        gc.collect()


def test_modification_invalidates_and_notifies():
    doc, seen = Model(), []
    DocumentCache.on_changed = seen.append
    DocumentCache.get(Proxy(doc)).para_ranges = ["p"]
    DocumentCache._modified(entry_of(Proxy(doc)))
    assert DocumentCache.get(Proxy(doc)).para_ranges is None
    assert len(seen) == 1


def test_deferring_invalidates_once_when_the_outermost_call_ends():
    doc, seen = Model(), []
    DocumentCache.on_changed = seen.append
    cache = DocumentCache.get(Proxy(doc))
    cache.para_ranges = ["p"]
    with DocumentCache.deferring():                 # batch
        with DocumentCache.deferring():             # one step
            DocumentCache._modified(entry_of(Proxy(doc)))
            DocumentCache._modified(entry_of(Proxy(doc)))
        assert cache.para_ranges == ["p"]           # stable across steps
    assert cache.para_ranges is None
    assert len(seen) == 1


def test_ignoring_drops_bookkeeping_changes():
    doc = Model()
    cache = DocumentCache.get(Proxy(doc))
    cache.para_ranges = ["p"]
    with DocumentCache.deferring():
        with DocumentCache.ignoring():
            DocumentCache._modified(entry_of(Proxy(doc)))
    assert cache.para_ranges == ["p"]


def test_disposed_document_is_dropped():
    doc, seen = Model(), []
    DocumentCache.on_changed = seen.append
    DocumentCache.get(Proxy(doc)).para_ranges = ["p"]
    DocumentCache._disposed(entry_of(Proxy(doc)))
    assert DocumentCache._entries == []
    assert DocumentCache.get(Proxy(doc)).para_ranges is None
    assert len(seen) == 1


def test_doc_id_is_stable_per_document_and_distinct_between_documents():
    a, b = Model(), Model()
    first = DocumentCache.doc_id(Proxy(a))
    assert DocumentCache.doc_id(Proxy(a)) == first
    assert DocumentCache.doc_id(Proxy(b)) != first
    assert len(first) == 32


def test_peek_never_creates_an_id():
    doc = Model()
    assert DocumentCache.peek_doc_id(Proxy(doc)) is None
    assert DocumentCache._entries == []
    DocumentCache.get(Proxy(doc))                 # cached, but no id handed out
    assert DocumentCache.peek_doc_id(Proxy(doc)) is None
    given = DocumentCache.doc_id(Proxy(doc))
    assert DocumentCache.peek_doc_id(Proxy(doc)) == given


def test_doc_id_is_forgotten_when_the_document_closes():
    doc = Model()
    old = DocumentCache.doc_id(Proxy(doc))
    DocumentCache._disposed(DocumentCache._find(Proxy(doc)))
    assert DocumentCache.peek_doc_id(Proxy(doc)) is None
    assert DocumentCache.doc_id(Proxy(doc)) != old


class Untouchable:
    """A model whose document properties must never be reached."""

    def getDocumentProperties(self):
        raise AssertionError("get_doc_id touched the document's properties")


def test_get_doc_id_does_not_touch_the_document():
    from plugin.modules.core.services.document import DocumentService
    svc = DocumentService()
    model = Untouchable()
    assert svc.get_doc_id(model) == svc.get_doc_id(model)
