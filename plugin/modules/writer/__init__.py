# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer module — tools for Writer document manipulation."""

from plugin.framework.module_base import ModuleBase


class WriterModule(ModuleBase):
    """Registers Writer tools for outline, content, comments, styles, etc."""

    def initialize(self, services):
        self.services = services
        from plugin.modules.writer.change_author import ChangeAuthor
        self._change_author = ChangeAuthor(services.config)
        services.register_instance("change_author", self._change_author)

    def start(self, services):
        # A call that died mid-swap left the agent's name in the profile.
        self._change_author.recover()
