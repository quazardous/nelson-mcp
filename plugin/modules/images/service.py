# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""GalleryService — image gallery provider registry.

Manages gallery provider instances and routes search/list requests
to the active provider.
"""

import logging

from plugin.framework.service_base import ServiceBase

log = logging.getLogger("nelson.images")


class GalleryInstance:
    """One gallery provider instance with metadata."""

    __slots__ = ("name", "module_name", "provider")

    def __init__(self, name, module_name, provider):
        self.name = name
        self.module_name = module_name
        self.provider = provider


class GalleryService(ServiceBase):
    """Image gallery provider registry.

    Instance ID convention:
      - ``"folder:My Photos"``
      - ``"immich:default"``
    """

    name = "images"

    def __init__(self):
        self._instances = {}       # instance_id -> GalleryInstance
        self._active_id = ""       # volatile active selection

    # -- Instance registration -------------------------------------------------

    def register_instance(self, instance_id, instance):
        """Register a gallery provider instance."""
        self._instances[instance_id] = instance
        log.info("Gallery provider registered: %s", instance_id)

    def unregister_instance(self, instance_id):
        """Remove a gallery provider instance."""
        self._instances.pop(instance_id, None)

    # -- Instance lookup -------------------------------------------------------

    def get_instance(self, instance_id=None):
        """Get a GalleryInstance by ID or active selection.

        Returns GalleryInstance or None.
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
                "No gallery provider available. Registered: %s" % available
            )
        return inst.provider

    def list_instances(self):
        """List all registered instances."""
        return list(self._instances.values())

    # -- Delegating methods ----------------------------------------------------

    def search(self, query, instance_id=None, limit=20):
        """Search images in a provider (default provider if not specified)."""
        provider = self.get_provider(instance_id=instance_id)
        return provider.search(query, limit=limit)

    def list_items(self, instance_id=None, path="", offset=0, limit=50):
        """List images from a provider."""
        provider = self.get_provider(instance_id=instance_id)
        return provider.list_items(path=path, offset=offset, limit=limit)

    def get_item(self, image_id, instance_id=None):
        """Get metadata for a specific image."""
        provider = self.get_provider(instance_id=instance_id)
        return provider.get_item(image_id)

    def update_metadata(self, image_id, metadata, instance_id=None):
        """Update metadata for an image via its provider."""
        provider = self.get_provider(instance_id=instance_id)
        return provider.update_metadata(image_id, metadata)

    def add_item(self, file_path, metadata=None, instance_id=None, dest_name=None):
        """Add an image file to a gallery provider."""
        provider = self.get_provider(instance_id=instance_id)
        return provider.add_item(file_path, metadata=metadata, dest_name=dest_name)

    # -- Active selection ------------------------------------------------------

    def set_active(self, instance_id):
        """Set the active provider instance."""
        self._active_id = instance_id
        log.info("Active gallery provider: %s", instance_id or "(auto)")

    def get_active(self):
        """Return the active instance ID."""
        return self._active_id


def get_instance_options(services):
    """Options provider for the images.default_instance config select."""
    svc = services.get("images")
    if not svc:
        return []
    options = [{"value": "", "label": "(auto)"}]
    for iid, inst in svc._instances.items():
        label = "[%s] %s" % (inst.module_name.split(".")[-1], inst.name)
        options.append({"value": iid, "label": label})
    return options
