# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Base class for all services."""

from abc import ABC
from typing import Any, Optional


class ServiceBase(ABC):
    """Abstract base for services registered in the ServiceRegistry.

    Services provide horizontal capabilities (document manipulation,
    config access, LLM streaming, etc.) that modules and tools consume.

    Attributes:
        name: Unique service identifier (e.g. "document", "config").
    """

    name: Optional[str] = None

    def initialize(self, ctx: Any) -> None:
        """Called once during bootstrap with the UNO component context.

        Override to perform setup that requires UNO (desktop access,
        service manager, etc.).

        Args:
            ctx: UNO component context (com.sun.star.uno.XComponentContext).
        """

    def shutdown(self) -> None:
        """Called on extension unload. Override to clean up."""
