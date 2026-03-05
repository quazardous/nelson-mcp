# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gallery provider ABC — contract for image gallery backends."""

from abc import ABC, abstractmethod


class ImageMeta:
    """Metadata for a single image in a gallery."""

    __slots__ = (
        "id", "name", "title", "description", "keywords",
        "rating", "file_path", "width", "height", "mime_type", "modified",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self):
        """Serialize to dict, omitting None values."""
        return {k: getattr(self, k) for k in self.__slots__
                if getattr(self, k) is not None}


class GalleryProvider(ABC):
    """Interface that gallery backend modules implement."""

    name: str = None

    @abstractmethod
    def list_items(self, path="", offset=0, limit=50):
        """List images, optionally filtered by path prefix.

        Returns:
            list[dict]: Image metadata dicts.
        """

    @abstractmethod
    def search(self, query, limit=20):
        """Full-text search across indexed metadata.

        Returns:
            list[dict]: Image metadata dicts with optional ``rank`` key.
        """

    @abstractmethod
    def get_item(self, image_id):
        """Get metadata for a single image.

        Args:
            image_id: Provider-specific identifier (typically relative path).

        Returns:
            dict or None.
        """

    def add_item(self, file_path, metadata=None, dest_name=None):
        """Add an image to the gallery.

        Args:
            file_path: Source file path.
            metadata: Optional metadata dict.
            dest_name: Optional destination name (may include subdirectories).
                       Extension is preserved from file_path if not in dest_name.

        Raises NotImplementedError if the provider is read-only.

        Returns:
            dict: Metadata of the added image.
        """
        raise NotImplementedError("This gallery provider is read-only.")

    def update_metadata(self, image_id, metadata):
        """Update XMP sidecar metadata for an image and re-index.

        Args:
            image_id: Provider-specific identifier.
            metadata: dict with optional keys: title, description, keywords, creator, rating.

        Returns:
            dict: Updated image metadata.

        Raises NotImplementedError if the provider is read-only.
        """
        raise NotImplementedError("This gallery provider is read-only.")

    def is_writable(self):
        """Whether this provider supports add_item / update_metadata."""
        return False

