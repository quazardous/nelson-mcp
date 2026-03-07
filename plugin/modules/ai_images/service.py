# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ImageService — image provider registry.

Manages image generation provider instances and routes requests
to the active provider.
"""

import logging

from plugin.framework.service_base import ServiceBase

log = logging.getLogger("nelson.images")


class ImageInstance:
    """One image provider instance with metadata."""

    __slots__ = ("name", "module_name", "provider")

    def __init__(self, name, module_name, provider):
        self.name = name
        self.module_name = module_name
        self.provider = provider


class ImageService(ServiceBase):
    """Image provider registry.

    Instance ID convention:
      - ``"openai:My Instance"``
      - ``"horde:default"``
    """

    name = "ai_images"

    def __init__(self):
        self._instances = {}       # instance_id -> ImageInstance
        self._active_id = ""       # volatile active selection

    # -- Instance registration -------------------------------------------------

    def register_instance(self, instance_id, instance):
        """Register an image provider instance."""
        self._instances[instance_id] = instance
        log.info("Image provider registered: %s", instance_id)

    def unregister_instance(self, instance_id):
        """Remove an image provider instance."""
        self._instances.pop(instance_id, None)

    # -- Instance lookup -------------------------------------------------------

    def get_instance(self, instance_id=None):
        """Get an ImageInstance by ID or active selection.

        Returns ImageInstance or None.
        """
        if instance_id:
            return self._instances.get(instance_id)

        # Active selection
        if self._active_id:
            inst = self._instances.get(self._active_id)
            if inst:
                return inst

        # Fallback: first registered instance
        if self._instances:
            return next(iter(self._instances.values()))

        return None

    def get_provider(self, instance_id=None):
        """Get the provider object. Raises RuntimeError if none available."""
        inst = self.get_instance(instance_id=instance_id)
        if inst is None:
            available = ", ".join(self._instances.keys()) or "(none)"
            raise RuntimeError(
                "No image provider available. Registered: %s" % available
            )
        return inst.provider

    def list_instances(self):
        """List all registered instances."""
        return list(self._instances.values())

    # -- Convenience -----------------------------------------------------------

    def generate_image(self, prompt, **kwargs):
        """Generate an image via the active provider."""
        return self.get_provider().generate(prompt, **kwargs)

    # -- Active selection ------------------------------------------------------

    def set_active(self, instance_id):
        """Set the active provider instance."""
        self._active_id = instance_id
        log.info("Active image provider: %s", instance_id or "(auto)")

    def get_active(self):
        """Return the active instance ID."""
        return self._active_id


def get_writable_gallery_options(services):
    """Options provider for the ai_images.save_to_gallery config select."""
    svc = services.get("images")
    if not svc:
        return [{"value": "", "label": "(disabled)"}]
    options = [{"value": "", "label": "(disabled)"}]
    for iid, inst in svc._instances.items():
        if inst.provider.is_writable():
            label = "[%s] %s" % (inst.module_name.split(".")[-1], inst.name)
            options.append({"value": iid, "label": label})
    return options


def get_instance_options(services):
    """Options provider for the ai_images.default_instance config select."""
    svc = services.get("ai_images")
    if not svc:
        return []
    options = [{"value": "", "label": "(auto)"}]
    for iid, inst in svc._instances.items():
        label = "[%s] %s" % (inst.module_name.split(".")[-1], inst.name)
        options.append({"value": iid, "label": label})
    return options


def get_interrogate_options(services):
    """Options provider for ai_images.interrogate_instance config select."""
    svc = services.get("ai_images")
    if not svc:
        return []
    options = [{"value": "", "label": "(auto - first available)"}]
    for iid, inst in svc._instances.items():
        p = inst.provider
        supports = hasattr(p, "supports_interrogate") and p.supports_interrogate()
        label = "[%s] %s" % (inst.module_name.split(".")[-1], inst.name)
        if supports:
            label += " (CLIP)"
        options.append({"value": iid, "label": label})
    return options
