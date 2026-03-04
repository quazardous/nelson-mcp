# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Folder gallery sub-module — registers folder instances."""

import json
import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.images.folder")


class ImagesFolderModule(ModuleBase):

    def initialize(self, services):
        from plugin.modules.images.service import GalleryInstance

        svc = services.images
        cfg = services.config.proxy_for(self.name)
        raw = cfg.get("instances") or "[]"
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(items, list):
            return

        self._items = items
        self._svc = svc

        for item in items:
            name = item.get("name") or "default"
            instance_id = "folder:%s" % name
            svc.register_instance(instance_id, GalleryInstance(
                name=name,
                module_name="images.folder",
                provider=_LazyProvider(item),
            ))

    def start_background(self, services):
        """Trigger initial rescan for all folder instances."""
        if not hasattr(self, "_svc"):
            return
        for inst in self._svc.list_instances():
            if inst.module_name == "images.folder":
                try:
                    inst.provider.rescan()
                except Exception as e:
                    log.warning("Initial rescan failed for %s: %s", inst.name, e)


class _LazyProvider:
    """Deferred folder provider — avoids import at startup."""

    def __init__(self, config_dict):
        self._config = config_dict
        self._real = None

    def _ensure(self):
        if self._real is None:
            from plugin.modules.images_folder.provider import (
                FolderGalleryProvider)
            self._real = FolderGalleryProvider(self._config)
        return self._real

    def list_items(self, path="", offset=0, limit=50):
        return self._ensure().list_items(path=path, offset=offset, limit=limit)

    def search(self, query, limit=20):
        return self._ensure().search(query, limit=limit)

    def get_item(self, image_id):
        return self._ensure().get_item(image_id)

    def add_item(self, file_path, metadata=None):
        return self._ensure().add_item(file_path, metadata=metadata)

    def update_metadata(self, image_id, metadata):
        return self._ensure().update_metadata(image_id, metadata)

    def is_writable(self):
        return self._ensure().is_writable()

    def rescan(self):
        return self._ensure().rescan()
