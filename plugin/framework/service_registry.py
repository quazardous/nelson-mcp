# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dependency injection container for services."""

import logging
from typing import Any, Dict, List, Optional

from plugin.framework.service_base import ServiceBase

_log = logging.getLogger("nelson.services")


class ServiceRegistry:
    """Registry that holds all services and provides attribute access.

    Usage::

        services = ServiceRegistry()
        services.register(my_document_service)
        services.register(my_config_service)

        # Access by name:
        services.document.build_heading_tree(doc)
        services.config.get("mcp.port")

        # Or explicit:
        services.get("document")
    """

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}

    def register(self, service: ServiceBase) -> None:
        """Register a ServiceBase instance by its ``name`` attribute."""
        if service.name is None:
            raise ValueError(f"Service {type(service).__name__} has no name")
        if service.name in self._services:
            raise ValueError(f"Service already registered: {service.name}")
        self._services[service.name] = service

    def register_instance(self, name: str, instance: Any) -> None:
        """Register an arbitrary object as a named service."""
        if name in self._services:
            raise ValueError(f"Service already registered: {name}")
        self._services[name] = instance

    def get(self, name: str) -> Optional[Any]:
        """Get a service by name, or None if not registered."""
        return self._services.get(name)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        svc = self._services.get(name)
        if svc is not None:
            return svc
        raise AttributeError(f"No service registered: {name}")

    def __contains__(self, name: str) -> bool:
        return name in self._services

    def initialize_all(self, ctx: Any) -> None:
        """Call ``initialize(ctx)`` on every service that supports it."""
        for svc in self._services.values():
            init = getattr(svc, "initialize", None)
            if callable(init):
                init(ctx)

    def shutdown_all(self) -> None:
        """Call ``shutdown()`` on every service that supports it."""
        for svc in self._services.values():
            shutdown = getattr(svc, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    _log.debug("Error shutting down service %s",
                               getattr(svc, "name", svc), exc_info=True)

    @property
    def service_names(self) -> List[str]:
        return list(self._services.keys())
