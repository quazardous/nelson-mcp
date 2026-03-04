# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Draw module — tools for Draw/Impress document manipulation."""

from plugin.framework.module_base import ModuleBase


class DrawModule(ModuleBase):
    """Registers Draw/Impress tools for shapes, pages/slides."""

    def initialize(self, services):
        self.services = services
