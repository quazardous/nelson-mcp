# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Image provider ABC — contract for image generation backends."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class ImageProvider(ABC):
    """Interface that image backend modules implement."""

    name: Optional[str] = None

    @abstractmethod
    def generate(self, prompt: str,
                 **kwargs: Any) -> Tuple[List[str], Optional[str]]:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image.
            **kwargs: width, height, model, strength, source_image, etc.

        Returns:
            (file_paths, error) — file_paths is a list of generated
            image paths; error is None on success.
        """

    def check(self) -> Tuple[bool, str]:
        """Fast connectivity check — is the backend reachable?

        Returns:
            (reachable, error_message).
        """
        return (True, "")

    def supports_editing(self) -> bool:
        """Whether this provider supports image editing (img2img)."""
        return False

    def supports_interrogate(self) -> bool:
        """Whether this provider supports image-to-text (interrogate)."""
        return False

    def interrogate(self, image_b64: str,
                    model: str = "clip") -> Tuple[str, Optional[str]]:
        """Describe an image using CLIP or similar model.

        Args:
            image_b64: Base64-encoded image data.
            model: Interrogation model ("clip" or "deepbooru").

        Returns:
            (caption, error) — caption is the description; error is None
            on success.
        """
        return ("", "Interrogation not supported by this provider.")
