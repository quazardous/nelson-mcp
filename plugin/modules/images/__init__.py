# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Images module — image gallery provider registry."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.images")


class ImagesModule(ModuleBase):

    def initialize(self, services):
        from plugin.modules.images.service import GalleryService

        svc = GalleryService()
        services.register(svc)

        cfg = services.config.proxy_for(self.name)
        default_id = cfg.get("default_instance") or ""
        if default_id:
            svc.set_active(default_id)
