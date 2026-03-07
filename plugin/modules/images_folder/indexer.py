# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SQLite+FTS5 index manager for folder-based image galleries."""

import hashlib
import logging
import os
import sqlite3
import time

log = logging.getLogger("nelson.images.folder")

_CONFIG_DIR = os.path.expanduser("~/.config/nelson")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS images (
    rel_path    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    title       TEXT DEFAULT '',
    description TEXT DEFAULT '',
    keywords    TEXT DEFAULT '',
    rating      INTEGER DEFAULT 0,
    width       INTEGER DEFAULT 0,
    height      INTEGER DEFAULT 0,
    mime_type   TEXT DEFAULT '',
    file_size   INTEGER DEFAULT 0,
    file_mtime  REAL DEFAULT 0,
    xmp_mtime   REAL DEFAULT 0,
    indexed_at  REAL DEFAULT 0
);
"""

_FTS_SCHEMA = """\
CREATE VIRTUAL TABLE IF NOT EXISTS images_fts USING fts5(
    rel_path, name, title, description, keywords,
    content='images',
    content_rowid='rowid'
);
"""

_FTS_TRIGGERS = """\
CREATE TRIGGER IF NOT EXISTS images_ai AFTER INSERT ON images BEGIN
    INSERT INTO images_fts(rowid, rel_path, name, title, description, keywords)
    VALUES (new.rowid, new.rel_path, new.name, new.title, new.description, new.keywords);
END;
CREATE TRIGGER IF NOT EXISTS images_ad AFTER DELETE ON images BEGIN
    INSERT INTO images_fts(images_fts, rowid, rel_path, name, title, description, keywords)
    VALUES ('delete', old.rowid, old.rel_path, old.name, old.title, old.description, old.keywords);
END;
CREATE TRIGGER IF NOT EXISTS images_au AFTER UPDATE ON images BEGIN
    INSERT INTO images_fts(images_fts, rowid, rel_path, name, title, description, keywords)
    VALUES ('delete', old.rowid, old.rel_path, old.name, old.title, old.description, old.keywords);
    INSERT INTO images_fts(rowid, rel_path, name, title, description, keywords)
    VALUES (new.rowid, new.rel_path, new.name, new.title, new.description, new.keywords);
END;
"""


def _db_path(root_path):
    """Compute DB path from the root folder path."""
    h = hashlib.md5(root_path.encode("utf-8")).hexdigest()[:12]
    return os.path.join(_CONFIG_DIR, "images_%s.db" % h)


class FolderIndex:
    """SQLite+FTS5 index for a single folder gallery."""

    def __init__(self, root_path):
        self._root = os.path.abspath(root_path)
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        self._db_path = _db_path(self._root)
        self._conn = None

    def _connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
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
        """Delete the SQLite database file so it is rebuilt on next access."""
        self.close()
        if os.path.isfile(self._db_path):
            os.remove(self._db_path)
            log.info("Deleted index database: %s", self._db_path)

    # -- Scanning --------------------------------------------------------------

    def scan(self, extensions, recursive, xmp_reader, force=False):
        """Incremental scan — index new/changed files, remove deleted ones.

        Args:
            extensions: set of lowercase extensions (e.g. {"jpg", "png"}).
            recursive: whether to walk subdirectories.
            xmp_reader: callable(image_path) -> dict of metadata.
            force: if True, re-index all files regardless of mtime.
        """
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
        for row in conn.execute("SELECT rel_path, file_mtime, xmp_mtime FROM images"):
            existing[row["rel_path"]] = (row["file_mtime"], row["xmp_mtime"])

        now = time.time()
        updated = 0
        inserted = 0

        for rel_path, (abs_path, file_mtime, file_size) in found.items():
            xmp_path = abs_path + ".xmp"
            xmp_mtime = 0.0
            try:
                xmp_mtime = os.path.getmtime(xmp_path)
            except OSError:
                pass

            # Check if re-index is needed
            if not force and rel_path in existing:
                old_file_mtime, old_xmp_mtime = existing[rel_path]
                if file_mtime <= old_file_mtime and xmp_mtime <= old_xmp_mtime:
                    continue  # unchanged

            # Read XMP metadata
            meta = xmp_reader(abs_path)
            title = meta.get("title", "")
            description = meta.get("description", "")
            keywords_list = meta.get("keywords", [])
            keywords = ", ".join(keywords_list) if keywords_list else ""
            rating = meta.get("rating", 0)

            # Detect mime type
            ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
            mime_type = _ext_to_mime(ext)

            # Read dimensions (best-effort, no external deps)
            width, height = _read_dimensions(abs_path, ext)

            name = os.path.basename(rel_path)

            if rel_path in existing:
                conn.execute(
                    "UPDATE images SET name=?, title=?, description=?, keywords=?, "
                    "rating=?, width=?, height=?, mime_type=?, file_size=?, "
                    "file_mtime=?, xmp_mtime=?, indexed_at=? WHERE rel_path=?",
                    (name, title, description, keywords, rating,
                     width, height, mime_type, file_size,
                     file_mtime, xmp_mtime, now, rel_path),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO images (rel_path, name, title, description, keywords, "
                    "rating, width, height, mime_type, file_size, "
                    "file_mtime, xmp_mtime, indexed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rel_path, name, title, description, keywords, rating,
                     width, height, mime_type, file_size,
                     file_mtime, xmp_mtime, now),
                )
                inserted += 1

        # Remove deleted files
        deleted = 0
        for rel_path in existing:
            if rel_path not in found:
                conn.execute("DELETE FROM images WHERE rel_path=?", (rel_path,))
                deleted += 1

        conn.commit()
        log.info(
            "Index scan complete: %d inserted, %d updated, %d deleted (%s)",
            inserted, updated, deleted, self._root,
        )
        return {"inserted": inserted, "updated": updated, "deleted": deleted}

    # -- Queries ---------------------------------------------------------------

    def search(self, query, limit=20):
        """FTS5 search. Returns list of dicts."""
        conn = self._connect()
        # Sanitize query for FTS5 — quote terms
        safe_query = " ".join(
            '"%s"' % t.replace('"', '') for t in query.split() if t.replace('"', '')
        )
        if not safe_query:
            return []
        rows = conn.execute(
            "SELECT i.*, rank FROM images_fts f "
            "JOIN images i ON i.rowid = f.rowid "
            "WHERE images_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (safe_query, limit),
        ).fetchall()
        return [_row_to_dict(row, self._root) for row in rows]

    def list_items(self, path_prefix="", offset=0, limit=50):
        """List images with optional path filter and pagination."""
        conn = self._connect()
        if path_prefix:
            rows = conn.execute(
                "SELECT * FROM images WHERE rel_path LIKE ? "
                "ORDER BY rel_path LIMIT ? OFFSET ?",
                (path_prefix + "%", limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM images ORDER BY rel_path LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_dict(row, self._root) for row in rows]

    def get_item(self, rel_path):
        """Get a single image by relative path."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM images WHERE rel_path=?", (rel_path,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row, self._root)

    def list_untagged(self, limit=50):
        """Return images with no description and no keywords."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM images "
            "WHERE (description IS NULL OR description = '') "
            "AND (keywords IS NULL OR keywords = '') "
            "ORDER BY rel_path LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(row, self._root) for row in rows]

    def count(self):
        """Total indexed images."""
        conn = self._connect()
        return conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]


# -- Helpers -------------------------------------------------------------------

def _row_to_dict(row, root):
    """Convert a sqlite3.Row to an image metadata dict."""
    d = dict(row)
    d.pop("rowid", None)
    d["id"] = d["rel_path"]
    d["file_path"] = os.path.join(root, d["rel_path"])
    # Convert keywords string back to list
    kw = d.get("keywords", "")
    d["keywords"] = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
    return d


def _ext_to_mime(ext):
    """Map file extension to MIME type."""
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif",
        "bmp": "image/bmp", "tiff": "image/tiff", "tif": "image/tiff",
        "webp": "image/webp", "svg": "image/svg+xml",
    }.get(ext, "image/unknown")


def _read_dimensions(abs_path, ext):
    """Best-effort image dimension reading using stdlib only.

    Reads PNG/JPEG/GIF headers without external libraries.
    Returns (width, height) or (0, 0).
    """
    try:
        with open(abs_path, "rb") as f:
            header = f.read(32)

        # PNG: bytes 16-23 contain width/height as 4-byte big-endian
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            import struct
            w, h = struct.unpack(">II", header[16:24])
            return (w, h)

        # GIF: bytes 6-9 contain width/height as 2-byte little-endian
        if header[:6] in (b"GIF87a", b"GIF89a"):
            import struct
            w, h = struct.unpack("<HH", header[6:10])
            return (w, h)

        # JPEG: scan for SOF markers
        if header[:2] == b"\xff\xd8":
            return _read_jpeg_dimensions(abs_path)

    except Exception:
        pass

    return (0, 0)


def _read_jpeg_dimensions(path):
    """Read JPEG dimensions by scanning for SOF0/SOF2 markers."""
    import struct
    try:
        with open(path, "rb") as f:
            f.read(2)  # skip SOI
            while True:
                marker = f.read(2)
                if len(marker) < 2:
                    break
                if marker[0] != 0xFF:
                    break
                mtype = marker[1]
                # SOF0, SOF1, SOF2
                if mtype in (0xC0, 0xC1, 0xC2):
                    length_data = f.read(2)
                    data = f.read(5)
                    if len(data) >= 5:
                        h, w = struct.unpack(">HH", data[1:5])
                        return (w, h)
                    break
                elif mtype == 0xD9:  # EOI
                    break
                elif mtype == 0xDA:  # SOS — start of scan, stop
                    break
                else:
                    seg_len = struct.unpack(">H", f.read(2))[0]
                    f.seek(seg_len - 2, 1)
    except Exception:
        pass
    return (0, 0)
