# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI Images module — AI image generation provider registry."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.ai_images")


def _check_indexing_ready(services):
    """Return error message if indexing can't run, or None if OK."""
    ai_svc = services.get("ai_images")
    gallery_svc = services.get("images")

    if not ai_svc or not gallery_svc:
        return "Images or AI Images service not available."

    # Check for interrogate-capable provider that is reachable
    cfg = services.config.proxy_for("ai_images")
    interrogate_id = cfg.get("interrogate_instance") or ""
    provider = None
    if interrogate_id:
        inst = ai_svc.get_instance(interrogate_id)
        if inst:
            provider = inst.provider
    if provider is None:
        for inst in ai_svc.list_instances():
            p = inst.provider
            if hasattr(p, "supports_interrogate") and p.supports_interrogate():
                provider = p
                break
    if provider is None:
        return ("No AI provider supports interrogation (img2txt).\n"
                "Configure a Forge instance in Options > SD WebUI Forge.")

    # Check provider is reachable
    ok, err = provider.check()
    if not ok:
        return ("Interrogate provider is not reachable: %s\n"
                "Start Forge first." % err)

    # Check at least one gallery wants indexing
    has_gallery = False
    for inst in gallery_svc.list_instances():
        gp = inst.provider
        if hasattr(gp, "wants_ai_index") and gp.wants_ai_index():
            has_gallery = True
            break
    if not has_gallery:
        return ("No gallery has AI indexing enabled.\n"
                "Enable 'AI Auto-Index' and 'Allow Adding Images' on a folder\n"
                "in Options > Image Folders.")

    return None


class AiImagesModule(ModuleBase):

    def __init__(self):
        self._services = None

    def initialize(self, services):
        from plugin.modules.ai_images.service import ImageService

        self._services = services
        svc = ImageService()
        services.register(svc)

        cfg = services.config.proxy_for(self.name)
        default_id = cfg.get("default_instance") or ""
        if default_id:
            svc.set_active(default_id)

    def on_action(self, action):
        from plugin.modules.ai_images.indexer import (
            is_running, start_indexing, stop_indexing)

        if action == "ai_index_toggle":
            log.warning("ai_index_toggle: is_running=%s", is_running())
            if is_running():
                stop_indexing()
            elif self._services:
                err = _check_indexing_ready(self._services)
                if err:
                    from plugin.framework.dialogs import msgbox
                    from plugin.framework.uno_context import get_ctx
                    msgbox(get_ctx(), "Nelson", err)
                else:
                    start_indexing(self._services)
        else:
            super().on_action(action)

    def get_menu_text(self, action):
        from plugin.modules.ai_images.indexer import is_running

        if action == "ai_index_toggle":
            return "Stop AI Indexing" if is_running() else "Start AI Indexing"
        return super().get_menu_text(action)
