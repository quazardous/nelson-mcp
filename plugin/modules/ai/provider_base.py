# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""LLM provider abstract base class."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class LlmProvider(ABC):
    """Interface that LLM backend modules implement and register."""

    name: Optional[str] = None

    @abstractmethod
    def complete(self, messages: List[Dict[str, str]],
                 **kwargs) -> Dict[str, Any]:
        """Non-streaming chat completion.

        Args:
            messages: OpenAI-format messages list.
                      [{"role": "system", "content": "..."}, ...]
            **kwargs: Extra params (temperature, max_tokens, model, ...).

        Returns:
            {"content": str, "model": str, "usage": dict | None}
        """

    def check(self) -> Tuple[bool, str]:
        """Fast connectivity check.

        Returns:
            (reachable, error_message). Default: always OK.
        """
        return (True, "")
