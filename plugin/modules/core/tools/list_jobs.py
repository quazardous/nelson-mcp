# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""List recent background jobs."""

from plugin.framework.tool_base import ToolBase


class ListJobs(ToolBase):
    """List recent background jobs with their status."""

    name = "list_jobs"
    description = "List recent background jobs with their status."
    tier = "core"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of jobs to return (default: 10).",
            },
        },
    }
    doc_types = None
    is_mutation = False

    def execute(self, ctx, **kwargs):
        jobs = ctx.services.jobs.list(limit=kwargs.get("limit", 10))
        return {"status": "ok", "jobs": [j.to_dict() for j in jobs]}
