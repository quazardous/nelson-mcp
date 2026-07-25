# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""docgallery_rescan — trigger a rescan of folder document providers."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.documents.folder")


class RescanDocFolder(ToolBase):
    """Rescan folder document providers to pick up new/changed documents."""

    name = "docgallery_rescan"
    aliases = ["docs_folder_rescan"]
    requires_service = "documents"
    description = (
        "Rescan document gallery folders to discover new, changed or "
        "deleted documents. Rescans all folder providers by default, "
        "or a specific one."
    )
    parameters = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "description": (
                    "Provider instance ID (e.g. 'folder:My Docs'). "
                    "Omit to rescan all folder providers."
                ),
            },
            "force": {
                "type": "boolean",
                "description": (
                    "Force re-index even if files are unchanged "
                    "(default: false)."
                ),
            },
        },
    }
    intent = "media"
    requires_doc = False

    def execute(self, ctx, **kwargs):
        provider_id = kwargs.get("provider")
        force = kwargs.get("force", False)

        svc = ctx.services.get("documents")
        if svc is None:
            return {"status": "error",
                    "message": "Documents service is not available."}

        folder_instances = [
            i for i in svc.list_instances()
            if i.module_name == "documents.folder"
        ]
        if not folder_instances:
            return {"status": "error",
                    "message": "No folder document providers configured."}

        totals = {"inserted": 0, "updated": 0, "deleted": 0}
        providers = []

        if provider_id:
            inst = svc.get_instance(provider_id)
            if inst is None or inst.module_name != "documents.folder":
                available = [i.name for i in folder_instances]
                return {
                    "status": "error",
                    "message": (
                        "Folder provider '%s' not found. Available: %s"
                        % (provider_id, ", ".join(available))
                    ),
                }
            result = inst.provider.rescan(force=force) or {}
            providers.append({
                "name": provider_id,
                "inserted": result.get("inserted", 0),
                "updated": result.get("updated", 0),
                "deleted": result.get("deleted", 0),
            })
        else:
            for inst in folder_instances:
                try:
                    result = inst.provider.rescan(force=force) or {}
                    providers.append({
                        "name": inst.name,
                        "inserted": result.get("inserted", 0),
                        "updated": result.get("updated", 0),
                        "deleted": result.get("deleted", 0),
                    })
                except Exception as e:
                    log.warning("Rescan failed for %s: %s", inst.name, e)
                    providers.append({"name": inst.name, "error": str(e)})

        for p in providers:
            if "error" not in p:
                totals["inserted"] += p["inserted"]
                totals["updated"] += p["updated"]
                totals["deleted"] += p["deleted"]

        return {
            "status": "ok",
            "providers": providers,
            **totals,
        }
