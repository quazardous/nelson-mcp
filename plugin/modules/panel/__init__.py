# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Panel module — provides sidebar panels for MCP action history and jobs."""

from plugin.framework.module_base import ModuleBase


class Module(ModuleBase):

    def initialize(self, services):
        from plugin.modules.panel.action_log import ActionLog

        self._log = ActionLog()
        services.register_instance("action_log", self._log)

    def start(self, services):
        bus = services.events
        bus.subscribe("tool:executing", self._log.on_executing)
        bus.subscribe("tool:completed", self._log.on_completed)
        bus.subscribe("tool:failed", self._log.on_failed)
