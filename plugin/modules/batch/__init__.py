# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Batch module — execute_batch tool for sequential tool chaining."""

from plugin.framework.module_base import ModuleBase


class BatchModule(ModuleBase):
    """Pure tool module — no services to register."""

    def initialize(self, services):
        pass
