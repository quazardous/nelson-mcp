# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer full-text search sub-module with stemming."""

from plugin.framework.module_base import ModuleBase


class WriterIndexModule(ModuleBase):
    """Registers the IndexService for full-text search."""

    def initialize(self, services):
        from .services.index import IndexService

        idx = IndexService(services.document, services.writer_tree,
                           services.writer_bookmarks, services.events)
        services.register_instance("writer_index", idx)
