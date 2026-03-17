# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI text module — minimal LLM provider registry.

Manages LLM provider instances (Ollama, OpenAI-compatible, etc.)
and exposes a simple ``complete(messages)`` interface for internal
consumers like the gallery indexer pass 2/3.
"""

import logging

from plugin.framework.module_base import ModuleBase
from plugin.framework.service_base import ServiceBase

log = logging.getLogger("nelson.ai")


class AiInstance:
    """One LLM provider instance with metadata."""

    __slots__ = ("name", "module_name", "provider")

    def __init__(self, name, module_name, provider):
        self.name = name
        self.module_name = module_name
        self.provider = provider


class AiService(ServiceBase):
    """Minimal LLM provider registry.

    Instance ID convention: ``"ai_ollama:llama3"``
    """

    name = "ai"

    def __init__(self):
        self._instances = {}   # instance_id -> AiInstance
        self._active_id = ""

    # -- Registration ----------------------------------------------------------

    def register_instance(self, instance_id, instance):
        self._instances[instance_id] = instance
        log.info("LLM provider registered: %s", instance_id)

    def unregister_instance(self, instance_id):
        self._instances.pop(instance_id, None)

    # -- Lookup ----------------------------------------------------------------

    def get_instance(self, instance_id=None):
        if instance_id:
            return self._instances.get(instance_id)
        if self._active_id:
            inst = self._instances.get(self._active_id)
            if inst:
                return inst
        if self._instances:
            return next(iter(self._instances.values()))
        return None

    def get_provider(self, instance_id=None):
        inst = self.get_instance(instance_id=instance_id)
        if inst is None:
            available = ", ".join(self._instances.keys()) or "(none)"
            raise RuntimeError(
                "No LLM provider available. Registered: %s" % available)
        return inst.provider

    def list_instances(self):
        return list(self._instances.values())

    # -- Convenience -----------------------------------------------------------

    def complete(self, messages, **kwargs):
        """Complete via the active provider. Shortcut for indexer etc."""
        return self.get_provider().complete(messages, **kwargs)

    def check(self):
        """Check the active provider."""
        try:
            return self.get_provider().check()
        except RuntimeError:
            return (False, "No LLM provider configured")

    # -- Active selection ------------------------------------------------------

    def set_active(self, instance_id):
        self._active_id = instance_id
        log.info("Active LLM provider: %s", instance_id or "(auto)")

    def get_active(self):
        return self._active_id


class AiModule(ModuleBase):

    def initialize(self, services):
        svc = AiService()
        services.register(svc)

        cfg = services.config.proxy_for(self.name)
        default_id = cfg.get("default_instance") or ""
        if default_id:
            svc.set_active(default_id)


def get_instance_options(services):
    """Options provider for the ai.default_instance config select."""
    svc = services.get("ai")
    if not svc:
        return []
    options = [{"value": "", "label": "(auto)"}]
    for iid, inst in svc._instances.items():
        label = "[%s] %s" % (inst.module_name.split(".")[-1], inst.name)
        options.append({"value": iid, "label": label})
    return options
