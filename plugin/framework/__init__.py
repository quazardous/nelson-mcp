# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Nelson MCP framework — base classes, registries, event bus."""

from plugin.framework.module_base import ModuleBase
from plugin.framework.tool_base import ToolBase
from plugin.framework.tool_context import ToolContext
from plugin.framework.service_base import ServiceBase
from plugin.framework.service_registry import ServiceRegistry
from plugin.framework.tool_registry import ToolRegistry
from plugin.framework.event_bus import EventBus
from plugin.framework.schema_convert import to_mcp_schema

__all__ = [
    "ModuleBase",
    "ToolBase",
    "ToolContext",
    "ServiceBase",
    "ServiceRegistry",
    "ToolRegistry",
    "EventBus",
    "to_mcp_schema",
]
