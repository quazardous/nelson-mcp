# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Poll a background job by ID."""

from plugin.framework.tool_base import ToolBase


class GetJob(ToolBase):
    """Get the status and result of a background job."""

    name = "get_job"
    description = "Get the status and result of a background job by its ID."
    tier = "core"
    parameters = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The job ID returned by the tool that started the job.",
            },
        },
        "required": ["job_id"],
    }
    doc_types = None
    is_mutation = False

    def execute(self, ctx, **kwargs):
        job = ctx.services.jobs.get(kwargs["job_id"])
        if not job:
            return {"status": "error", "error": "Job not found"}
        return {"status": "ok", **job.to_dict()}
