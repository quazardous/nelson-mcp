# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Image provider ABC — contract for image generation backends."""

from abc import ABC, abstractmethod


class ImageProvider(ABC):
    """Interface that image backend modules implement."""

    name: str = None

    @abstractmethod
    def generate(self, prompt, **kwargs):
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image.
            **kwargs: width, height, model, strength, source_image, etc.

        Returns:
            (file_paths: list[str], error: str | None)
            file_paths is a list of generated image paths.
            error is None on success.
        """

    def check(self):
        """Fast connectivity check — is the backend reachable?

        Returns:
            (bool, str): (reachable, error_message).
        """
        return (True, "")

    def supports_editing(self):
        """Whether this provider supports image editing (img2img)."""
        return False
