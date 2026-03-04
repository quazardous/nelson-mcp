# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer navigation sub-module — bookmarks, heading tree, proximity."""

from plugin.framework.module_base import ModuleBase


class WriterNavModule(ModuleBase):
    """Registers navigation services for Writer documents."""

    def initialize(self, services):
        from .services.bookmarks import BookmarkService
        from .services.tree import TreeService
        from .services.proximity import ProximityService

        doc_svc = services.document
        events = services.events

        bm = BookmarkService(doc_svc, events)
        tree = TreeService(doc_svc, bm, events)
        prox = ProximityService(doc_svc, tree, bm, events)

        services.register_instance("writer_bookmarks", bm)
        services.register_instance("writer_tree", tree)
        services.register_instance("writer_proximity", prox)
