# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer navigation sub-module — bookmarks, heading tree, proximity."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.writer.nav")


class WriterNavModule(ModuleBase):
    """Registers navigation services for Writer documents."""

    def initialize(self, services):
        from .services.bookmarks import DEFAULT_MODE, BookmarkService
        from .services.tree import TreeService
        from .services.proximity import ProximityService

        doc_svc = services.document
        events = services.events
        cfg = services.config.proxy_for(self.name)

        # Read on every use, so a change in Options applies to the next call.
        bm = BookmarkService(
            doc_svc, events,
            mode_getter=lambda: cfg.get("heading_bookmarks", DEFAULT_MODE))
        tree = TreeService(doc_svc, bm, events)
        prox = ProximityService(doc_svc, tree, bm, events)

        services.register_instance("writer_bookmarks", bm)
        services.register_instance("writer_tree", tree)
        services.register_instance("writer_proximity", prox)
        self._bm = bm
        self._save_hook = None

    def start(self, services):
        from plugin.framework.uno_context import get_ctx
        from .services.save_hook import SaveHook

        hook = SaveHook(self._bm)
        try:
            hook.register(get_ctx())
            self._save_hook = hook
        except Exception as e:
            log.error("Heading bookmark save hook not registered: %s", e)

    def shutdown(self):
        if self._save_hook is not None:
            self._save_hook.unregister()
            self._save_hook = None
