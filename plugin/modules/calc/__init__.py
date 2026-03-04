# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Calc module — tools for Calc spreadsheet manipulation."""

from plugin.framework.module_base import ModuleBase


class CalcModule(ModuleBase):
    """Registers Calc tools for cells, sheets, formulas, charts."""

    def initialize(self, services):
        self.services = services
