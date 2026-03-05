# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Folder gallery provider — scans local folders, indexes with SQLite+FTS5."""

import logging
import os
import shutil

from plugin.modules.images.provider_base import GalleryProvider
from plugin.modules.images.xmp import read_xmp, write_xmp
from plugin.modules.images_folder.indexer import FolderIndex

log = logging.getLogger("nelson.images.folder")


class FolderGalleryProvider(GalleryProvider):
    """Image gallery backed by a local folder with XMP sidecar metadata."""

    def __init__(self, config_dict):
        self._config = config_dict
        self._root = os.path.abspath(config_dict.get("path", ""))
        self._recursive = config_dict.get("recursive", True)
        self._writable = config_dict.get("writable", False)
        self._sync_gallery = config_dict.get("sync_gallery", False)
        ext_str = config_dict.get("extensions", "jpg,jpeg,png,gif,bmp,tiff,tif,webp,svg")
        self._extensions = {e.strip().lower() for e in ext_str.split(",") if e.strip()}
        self.name = config_dict.get("name", "folder")
        self._index = FolderIndex(self._root)

    def list_items(self, path="", offset=0, limit=50):
        return self._index.list_items(path_prefix=path, offset=offset, limit=limit)

    def search(self, query, limit=20):
        return self._index.search(query, limit=limit)

    def get_item(self, image_id):
        return self._index.get_item(image_id)

    def add_item(self, file_path, metadata=None, dest_name=None):
        if not self._writable:
            raise NotImplementedError("This gallery provider is read-only.")

        if not os.path.isfile(file_path):
            raise FileNotFoundError("Source file not found: %s" % file_path)

        if dest_name:
            # Preserve original extension if dest_name has none
            _, src_ext = os.path.splitext(file_path)
            _, dest_ext = os.path.splitext(dest_name)
            if not dest_ext and src_ext:
                dest_name = dest_name + src_ext
            dest = os.path.join(self._root, dest_name)
        else:
            dest = os.path.join(self._root, os.path.basename(file_path))

        # Create subdirectories if needed
        dest_dir = os.path.dirname(dest)
        if dest_dir and not os.path.isdir(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)

        if os.path.abspath(file_path) != os.path.abspath(dest):
            shutil.copy2(file_path, dest)

        if metadata:
            write_xmp(dest, metadata)

        # Re-index this single file
        self.rescan()
        rel_path = os.path.relpath(dest, self._root)
        return self._index.get_item(rel_path)

    def update_metadata(self, image_id, metadata):
        if not self._writable:
            raise NotImplementedError("This gallery provider is read-only.")

        abs_path = os.path.join(self._root, image_id)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError("Image not found: %s" % image_id)

        # Merge with existing XMP
        existing = read_xmp(abs_path)
        existing.update(metadata)
        write_xmp(abs_path, existing)

        # Re-index to pick up changes
        self.rescan()
        return self._index.get_item(image_id)

    def is_writable(self):
        return self._writable

    def reset_db(self):
        """Delete the index database so it is rebuilt on next rescan."""
        self._index.reset()

    def rescan(self, force=False):
        if not os.path.isdir(self._root):
            log.warning("Gallery folder does not exist: %s", self._root)
            return

        result = self._index.scan(
            extensions=self._extensions,
            recursive=self._recursive,
            xmp_reader=read_xmp,
            force=force,
        )

        if self._sync_gallery:
            self._sync_to_lo_gallery()

        return result

    def _sync_to_lo_gallery(self):
        """Sync indexed images to a LibreOffice Gallery theme."""
        try:
            from plugin.framework.uno_context import get_ctx
            from plugin.framework.image_utils import add_image_to_gallery

            ctx = get_ctx()
            items = self._index.list_items(limit=10000)
            for item in items:
                fp = item.get("file_path", "")
                if fp and os.path.isfile(fp):
                    try:
                        add_image_to_gallery(ctx, fp, item.get("title", ""))
                    except Exception as e:
                        log.debug("Gallery sync failed for %s: %s", fp, e)
        except Exception as e:
            log.warning("LO Gallery sync failed: %s", e)
