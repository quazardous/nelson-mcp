# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI Images module — AI image generation provider registry."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.ai_images")


class AiImagesModule(ModuleBase):

    def initialize(self, services):
        from plugin.modules.ai_images.service import ImageService

        svc = ImageService()
        services.register(svc)

        cfg = services.config.proxy_for(self.name)
        default_id = cfg.get("default_instance") or ""
        if default_id:
            svc.set_active(default_id)
