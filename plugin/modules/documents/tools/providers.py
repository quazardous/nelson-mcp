# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""docgallery_providers — list available document gallery providers."""

from plugin.framework.tool_base import ToolBase


class ListDocProviders(ToolBase):
    """List all registered document gallery provider instances."""

    name = "docgallery_providers"
    aliases = ["docs_gallery_providers"]
    requires_service = "documents"
    description = (
        "List all available document gallery providers with their instance "
        "IDs. Use the returned IDs with other docs_gallery tools to target "
        "a specific provider."
    )
    parameters = {
        "type": "object",
        "properties": {},
    }
    intent = "media"
    requires_doc = False

    def execute(self, ctx, **kwargs):
        svc = ctx.services.get("documents")
        if svc is None:
            return {"status": "error",
                    "message": "Documents service is not available."}

        instances = svc.list_instances()
        active_id = svc.get_active()

        providers = []
        for inst in instances:
            for iid, registered in svc._instances.items():
                if registered is inst:
                    providers.append({
                        "id": iid,
                        "name": inst.name,
                        "type": inst.module_name,
                        "writable": inst.provider.is_writable(),
                        "active": iid == active_id if active_id else False,
                    })
                    break

        if providers and not active_id:
            providers[0]["active"] = True

        return {
            "status": "ok",
            "count": len(providers),
            "providers": providers,
        }
