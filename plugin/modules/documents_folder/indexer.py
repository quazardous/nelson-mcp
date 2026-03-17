# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SQLite+FTS5 index manager for folder-based document galleries."""

import hashlib
import logging
import os
import sqlite3
import time

log = logging.getLogger("nelson.documents.folder")

_CONFIG_DIR = os.path.expanduser("~/.config/nelson")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS documents (
    rel_path        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    title           TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    subject         TEXT DEFAULT '',
    keywords        TEXT DEFAULT '',
    creator         TEXT DEFAULT '',
    doc_type        TEXT DEFAULT '',
    mime_type       TEXT DEFAULT '',
    file_size       INTEGER DEFAULT 0,
    file_mtime      REAL DEFAULT 0,
    page_count      INTEGER DEFAULT 0,
    word_count      INTEGER DEFAULT 0,
    character_count INTEGER DEFAULT 0,
    paragraph_count INTEGER DEFAULT 0,
    image_count     INTEGER DEFAULT 0,
    table_count     INTEGER DEFAULT 0,
    indexed_at      REAL DEFAULT 0
);
"""

_FTS_SCHEMA = """\
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    rel_path, name, title, description, subject, keywords, creator,
    content='documents',
    content_rowid='rowid'
);
"""

_FTS_TRIGGERS = """\
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, rel_path, name, title, description,
                              subject, keywords, creator)
    VALUES (new.rowid, new.rel_path, new.name, new.title, new.description,
            new.subject, new.keywords, new.creator);
END;
CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, rel_path, name, title,
                              description, subject, keywords, creator)
    VALUES ('delete', old.rowid, old.rel_path, old.name, old.title,
            old.description, old.subject, old.keywords, old.creator);
END;
CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, rel_path, name, title,
                              description, subject, keywords, creator)
    VALUES ('delete', old.rowid, old.rel_path, old.name, old.title,
            old.description, old.subject, old.keywords, old.creator);
    INSERT INTO documents_fts(rowid, rel_path, name, title, description,
                              subject, keywords, creator)
    VALUES (new.rowid, new.rel_path, new.name, new.title, new.description,
            new.subject, new.keywords, new.creator);
END;
"""


def _db_path(root_path):
    """Compute DB path from the root folder path."""
    h = hashlib.md5(root_path.encode("utf-8")).hexdigest()[:12]
    return os.path.join(_CONFIG_DIR, "documents_%s.db" % h)


class DocumentIndex:
    """SQLite+FTS5 index for a single document folder gallery."""

    def __init__(self, root_path):
        self._root = os.path.abspath(root_path)
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        self._db_path = _db_path(self._root)
        self._conn = None

    def _connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.executescript(_FTS_SCHEMA)
            self._conn.executescript(_FTS_TRIGGERS)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def reset(self):
        """Clear all indexed data (soft reset — truncates tables)."""
        conn = self._connect()
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM documents_fts")
        conn.commit()
        log.info("Document index cleared (soft reset): %s", self._db_path)

    # -- Scanning --------------------------------------------------------------

    def scan(self, extensions, recursive, metadata_reader, force=False):
        """Incremental scan — index new/changed files, remove deleted ones.

        Args:
            extensions: set of lowercase extensions (e.g. {"odt", "pdf"}).
            recursive: whether to walk subdirectories.
            metadata_reader: callable(file_path) -> dict of metadata.
            force: if True, re-index all files regardless of mtime.
        """
        from plugin.modules.documents_folder.metadata import (
            detect_doc_type, ext_to_mime,
        )

        conn = self._connect()

        # Collect all current files
        found = {}  # rel_path -> (abs_path, file_mtime, file_size)
        if recursive:
            for dirpath, _dirs, filenames in os.walk(self._root):
                for fn in filenames:
                    ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
                    if ext not in extensions:
                        continue
                    abs_path = os.path.join(dirpath, fn)
                    rel_path = os.path.relpath(abs_path, self._root)
                    try:
                        st = os.stat(abs_path)
                    except OSError:
                        continue
                    found[rel_path] = (abs_path, st.st_mtime, st.st_size)
        else:
            for fn in os.listdir(self._root):
                ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
                if ext not in extensions:
                    continue
                abs_path = os.path.join(self._root, fn)
                if not os.path.isfile(abs_path):
                    continue
                try:
                    st = os.stat(abs_path)
                except OSError:
                    continue
                found[fn] = (abs_path, st.st_mtime, st.st_size)

        # Get existing indexed entries
        existing = {}
        for row in conn.execute(
                "SELECT rel_path, file_mtime FROM documents"):
            existing[row["rel_path"]] = row["file_mtime"]

        now = time.time()
        updated = 0
        inserted = 0

        for rel_path, (abs_path, file_mtime, file_size) in found.items():
            # Check if re-index is needed
            if not force and rel_path in existing:
                if file_mtime <= existing[rel_path]:
                    continue  # unchanged

            # Read document metadata
            meta = metadata_reader(abs_path)
            ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
            name = os.path.basename(rel_path)

            title = meta.get("title", "")
            description = meta.get("description", "")
            subject = meta.get("subject", "")
            keywords_list = meta.get("keywords", [])
            keywords = ", ".join(keywords_list) if keywords_list else ""
            creator = meta.get("creator", "")
            doc_type = detect_doc_type(ext)
            mime_type = ext_to_mime(ext)

            page_count = meta.get("page_count", 0)
            word_count = meta.get("word_count", 0)
            character_count = meta.get("character_count", 0)
            paragraph_count = meta.get("paragraph_count", 0)
            image_count = meta.get("image_count", 0)
            table_count = meta.get("table_count", 0)

            params = (
                name, title, description, subject, keywords, creator,
                doc_type, mime_type, file_size, file_mtime,
                page_count, word_count, character_count,
                paragraph_count, image_count, table_count, now,
            )

            if rel_path in existing:
                conn.execute(
                    "UPDATE documents SET name=?, title=?, description=?, "
                    "subject=?, keywords=?, creator=?, doc_type=?, "
                    "mime_type=?, file_size=?, file_mtime=?, "
                    "page_count=?, word_count=?, character_count=?, "
                    "paragraph_count=?, image_count=?, table_count=?, "
                    "indexed_at=? WHERE rel_path=?",
                    params + (rel_path,),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO documents (rel_path, name, title, "
                    "description, subject, keywords, creator, doc_type, "
                    "mime_type, file_size, file_mtime, page_count, "
                    "word_count, character_count, paragraph_count, "
                    "image_count, table_count, indexed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?)",
                    (rel_path,) + params,
                )
                inserted += 1

        # Remove deleted files
        deleted = 0
        for rel_path in existing:
            if rel_path not in found:
                conn.execute(
                    "DELETE FROM documents WHERE rel_path=?", (rel_path,))
                deleted += 1

        conn.commit()
        log.info(
            "Document index scan: %d inserted, %d updated, %d deleted (%s)",
            inserted, updated, deleted, self._root,
        )
        return {"inserted": inserted, "updated": updated, "deleted": deleted}

    # -- Queries ---------------------------------------------------------------

    def search(self, query, limit=20, doc_type=None):
        """FTS5 search. Returns list of dicts."""
        conn = self._connect()
        safe_query = " ".join(
            '"%s"' % t.replace('"', '')
            for t in query.split() if t.replace('"', '')
        )
        if not safe_query:
            return []

        if doc_type:
            rows = conn.execute(
                "SELECT d.*, rank FROM documents_fts f "
                "JOIN documents d ON d.rowid = f.rowid "
                "WHERE documents_fts MATCH ? AND d.doc_type = ? "
                "ORDER BY rank LIMIT ?",
                (safe_query, doc_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT d.*, rank FROM documents_fts f "
                "JOIN documents d ON d.rowid = f.rowid "
                "WHERE documents_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (safe_query, limit),
            ).fetchall()
        return [_row_to_dict(row, self._root) for row in rows]

    def list_items(self, path_prefix="", offset=0, limit=50, doc_type=None):
        """List documents with optional path/type filter and pagination."""
        conn = self._connect()
        clauses = []
        params = []

        if path_prefix:
            clauses.append("rel_path LIKE ?")
            params.append(path_prefix + "%")
        if doc_type:
            clauses.append("doc_type = ?")
            params.append(doc_type)

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])

        rows = conn.execute(
            "SELECT * FROM documents%s ORDER BY rel_path LIMIT ? OFFSET ?"
            % where,
            params,
        ).fetchall()
        return [_row_to_dict(row, self._root) for row in rows]

    def get_item(self, rel_path):
        """Get a single document by relative path."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM documents WHERE rel_path=?", (rel_path,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row, self._root)

    def count(self, doc_type=None):
        """Total indexed documents, optionally filtered by doc_type."""
        conn = self._connect()
        if doc_type:
            return conn.execute(
                "SELECT COUNT(*) FROM documents WHERE doc_type=?",
                (doc_type,),
            ).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM documents").fetchone()[0]


# -- Helpers -------------------------------------------------------------------

def _row_to_dict(row, root):
    """Convert a sqlite3.Row to a document metadata dict."""
    d = dict(row)
    d.pop("rowid", None)
    d["id"] = d["rel_path"]
    d["file_path"] = os.path.join(root, d["rel_path"])
    # Convert keywords string back to list
    kw = d.get("keywords", "")
    d["keywords"] = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
    # Drop zero stats for cleaner output
    for key in ("page_count", "word_count", "character_count",
                "paragraph_count", "image_count", "table_count"):
        if d.get(key) == 0:
            d.pop(key, None)
    return d
