# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Folder gallery sub-module — registers folder instances."""

import json
import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.images.folder")


def _show_statusbar(text, duration=5.0):
    """Show a message in the LibreOffice status bar for a few seconds."""
    try:
        from plugin.framework.uno_context import get_ctx
        ctx = get_ctx()
        if not ctx:
            return
        desktop = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)
        frame = desktop.getCurrentFrame()
        if frame is None:
            return
        sb = frame.createStatusIndicator()
        sb.start(text, 100)
        sb.setValue(100)

        import threading

        def _clear():
            from plugin.framework.main_thread import post_to_main_thread
            post_to_main_thread(sb.end)

        threading.Timer(duration, _clear).start()
    except Exception:
        log.debug("Could not show statusbar message: %s", text)


def on_rescan():
    """Callback for the Rescan Folders button in Options."""
    from plugin.main import get_services
    services = get_services()
    if not services:
        log.warning("on_rescan: services not available")
        return

    svc = services.get("images")
    if svc is None:
        log.warning("on_rescan: images service not available")
        return

    inserted = 0
    updated = 0
    deleted = 0
    for inst in svc.list_instances():
        if inst.module_name != "images.folder":
            continue
        try:
            result = inst.provider.rescan()
            if result:
                inserted += result.get("inserted", 0)
                updated += result.get("updated", 0)
                deleted += result.get("deleted", 0)
            log.info("on_rescan: rescanned %s", inst.name)
        except Exception:
            log.exception("on_rescan: failed for %s", inst.name)

    msg = "Rescan: %d new, %d updated, %d deleted" % (inserted, updated, deleted)
    log.info("on_rescan: %s", msg)

    # Show result in statusbar — deferred to main thread after Options closes
    import threading

    def _deferred():
        from plugin.framework.main_thread import post_to_main_thread
        post_to_main_thread(lambda: _show_statusbar(msg))

    threading.Timer(1.0, _deferred).start()


def on_reset_db():
    """Callback for the Reset Database button in Options."""
    from plugin.main import get_services
    services = get_services()
    if not services:
        log.warning("on_reset_db: services not available")
        return

    svc = services.get("images")
    if svc is None:
        log.warning("on_reset_db: images service not available")
        return

    count = 0
    for inst in svc.list_instances():
        if inst.module_name != "images.folder":
            continue
        try:
            inst.provider.reset_db()
            count += 1
            log.info("on_reset_db: reset %s", inst.name)
        except Exception:
            log.exception("on_reset_db: failed for %s", inst.name)

    msg = "Database reset: %d provider(s) cleared" % count

    # Emit event so ai_images can re-index
    bus = services.get("events")
    if bus:
        bus.emit("gallery:reset", kind="images")

    import threading

    def _deferred():
        from plugin.framework.main_thread import post_to_main_thread
        post_to_main_thread(lambda: _show_statusbar(msg))

    threading.Timer(1.0, _deferred).start()


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
        """Trigger initial rescan for all folder instances if enabled."""
        if not hasattr(self, "_svc"):
            return
        cfg = services.config.proxy_for(self.name)
        if not cfg.get("rescan_on_startup", True):
            log.info("Rescan on startup disabled, skipping")
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

    def add_item(self, file_path, metadata=None, dest_name=None):
        return self._ensure().add_item(file_path, metadata=metadata, dest_name=dest_name)

    def update_metadata(self, image_id, metadata):
        return self._ensure().update_metadata(image_id, metadata)

    def is_writable(self):
        return self._ensure().is_writable()

    def reset_db(self, **kwargs):
        return self._ensure().reset_db(**kwargs)

    def rescan(self, **kwargs):
        return self._ensure().rescan(**kwargs)

    def wants_ai_index(self):
        return self._ensure().wants_ai_index()

    def list_untagged(self, limit=50):
        return self._ensure().list_untagged(limit=limit)
