# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""doc_open's answer when LibreOffice stops a load to ask a question."""

import pytest

from plugin.modules.doc.load_questions import describe, lock_owner


def _locked(tmp_path, content):
    doc = tmp_path / "report.xlsx"
    doc.write_bytes(b"")
    (tmp_path / ".~lock.report.xlsx#").write_text(content)
    return str(doc)


def test_lock_owner_reads_the_lock_file(tmp_path):
    path = _locked(tmp_path, "Ana Lopez,laptop,ana,22.09.2026 10:00,"
                             "file:///home/ana/.config/libreoffice/4;")
    owner = lock_owner(path)
    assert owner["name"] == "Ana Lopez"
    assert owner["host"] == "laptop"
    assert owner["since"] == "22.09.2026 10:00"


def test_lock_owner_falls_back_to_the_user_and_tolerates_junk(tmp_path):
    assert lock_owner(_locked(tmp_path, ",pc,bob,01.01.2026 09:00,x;"))[
        "name"] == "bob"
    assert "name" not in lock_owner(_locked(tmp_path, "garbage"))
    assert lock_owner(str(tmp_path / "nothing.odt")) is None


def test_locked_document_names_the_holder(tmp_path):
    path = _locked(tmp_path, "Ana Lopez,laptop,ana,22.09.2026 10:00,x;")
    err = describe("LockedDocumentRequest", "Ana", path)
    assert err["code"] == "document_locked"
    assert "Ana Lopez on laptop since 22.09.2026 10:00" in err["message"]
    assert "read_only" in err["hint"]
    assert err["retryable"] is False
    assert err["locked_by"]["user"] == "ana"


def test_own_lock_says_it_is_the_users():
    err = describe("OwnLockOnDocumentRequest", "10:00")
    assert err["code"] == "document_locked"
    assert "you" in err["message"]


@pytest.mark.parametrize("kind, code", [
    ("DocumentPasswordRequest2", "password_required"),
    ("DocumentMSPasswordRequest2", "password_required"),
    ("BrokenPackageRequest", "document_damaged"),
    ("SomethingNew", "interaction_required"),
])
def test_other_questions_have_their_own_code(kind, code):
    err = describe(kind)
    assert err["code"] == code
    assert err["retryable"] is False
    assert err["message"]


def test_infer_kind_from_the_file(tmp_path):
    import zipfile
    from plugin.modules.doc.load_questions import infer_kind
    locked = _locked(tmp_path, "Ana,pc,ana,22.09.2026 10:00,x;")
    assert infer_kind(locked) == "LockedDocumentRequest"
    broken = tmp_path / "broken.odt"
    broken.write_bytes(b"PK\x03\x04 not really a zip")
    assert infer_kind(str(broken)) == "BrokenPackageRequest"
    fine = tmp_path / "fine.odt"
    with zipfile.ZipFile(fine, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
    assert infer_kind(str(fine)) == "unknown"
    assert infer_kind(str(tmp_path / "data.csv")) == "unknown"
