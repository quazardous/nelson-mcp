# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gallery provider ABC — contract for image gallery backends."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ImageMeta:
    """Metadata for a single image in a gallery."""

    __slots__ = (
        "id", "name", "title", "description", "keywords",
        "rating", "file_path", "width", "height", "mime_type", "modified",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, omitting None values."""
        return {k: getattr(self, k) for k in self.__slots__
                if getattr(self, k) is not None}


class GalleryProvider(ABC):
    """Interface that gallery backend modules implement."""

    name: Optional[str] = None

    @abstractmethod
    def list_items(self, path: str = "", offset: int = 0,
                   limit: int = 50) -> List[Dict[str, Any]]:
        """List images, optionally filtered by path prefix.

        Returns:
            Image metadata dicts.
        """

    @abstractmethod
    def search(self, query: str,
               limit: int = 20) -> List[Dict[str, Any]]:
        """Full-text search across indexed metadata.

        Returns:
            Image metadata dicts with optional ``rank`` key.
        """

    @abstractmethod
    def get_item(self, image_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a single image.

        Args:
            image_id: Provider-specific identifier (typically relative path).

        Returns:
            dict or None.
        """

    def add_item(self, file_path: str, metadata: Optional[Dict[str, Any]] = None,
                 dest_name: Optional[str] = None) -> Dict[str, Any]:
        """Add an image to the gallery.

        Args:
            file_path: Source file path.
            metadata: Optional metadata dict.
            dest_name: Optional destination name (may include subdirectories).
                       Extension is preserved from file_path if not in dest_name.

        Raises NotImplementedError if the provider is read-only.

        Returns:
            Metadata of the added image.
        """
        raise NotImplementedError("This gallery provider is read-only.")

    def update_metadata(self, image_id: str,
                        metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Update XMP sidecar metadata for an image and re-index.

        Args:
            image_id: Provider-specific identifier.
            metadata: dict with optional keys: title, description, keywords, creator, rating.

        Returns:
            Updated image metadata.

        Raises NotImplementedError if the provider is read-only.
        """
        raise NotImplementedError("This gallery provider is read-only.")

    def list_untagged(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return images that have no description and no keywords."""
        return []

    def wants_ai_index(self) -> bool:
        """Whether this provider opted in to AI auto-indexing."""
        return False

    def is_writable(self) -> bool:
        """Whether this provider supports add_item / update_metadata."""
        return False
