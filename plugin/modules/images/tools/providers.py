# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""gallery_providers — list available gallery provider instances."""

from plugin.framework.tool_base import ToolBase


class ListProviders(ToolBase):
    """List all registered gallery provider instances."""

    name = "gallery_providers"
    description = (
        "List all available image gallery providers with their instance IDs. "
        "Use the returned IDs with other gallery tools to target a specific provider."
    )
    parameters = {
        "type": "object",
        "properties": {},
    }
    intent = "media"

    def execute(self, ctx, **kwargs):
        svc = ctx.services.get("images")
        if svc is None:
            return {"status": "error", "message": "Images service is not available."}

        instances = svc.list_instances()
        active_id = svc.get_active()

        providers = []
        for inst in instances:
            # Reconstruct instance_id from the registry
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

        # Mark first as default if no explicit active
        if providers and not active_id:
            providers[0]["active"] = True

        return {
            "status": "ok",
            "count": len(providers),
            "providers": providers,
        }
