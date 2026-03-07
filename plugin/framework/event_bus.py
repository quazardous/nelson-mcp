# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lightweight synchronous event bus for inter-module communication."""

import logging
import weakref
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("nelson.events")


class EventBus:
    """Publish/subscribe event bus.

    All callbacks run synchronously on the calling thread. Exceptions in
    subscribers are logged but never propagated to the emitter.

    Usage::

        bus = EventBus()
        bus.subscribe("config:changed", my_callback)
        bus.emit("config:changed", key="mcp.port", value=9000)

    Weak references are supported to avoid preventing garbage collection
    of listener objects::

        bus.subscribe("document:closed", obj.on_close, weak=True)
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Tuple[Any, bool]]] = {}

    def subscribe(self, event: str, callback: Callable[..., Any],
                  weak: bool = False) -> None:
        """Register *callback* for *event*.

        Args:
            event:    Event name (e.g. "config:changed").
            callback: Callable to invoke when the event is emitted.
            weak:     If True, store a weakref to the callback's bound
                      object. The subscription auto-removes when the
                      object is garbage-collected.
        """
        if event not in self._subscribers:
            self._subscribers[event] = []

        if weak and hasattr(callback, "__self__"):
            ref = weakref.WeakMethod(callback, lambda r: self._cleanup(event, r))
            self._subscribers[event].append((ref, True))
        else:
            self._subscribers[event].append((callback, False))

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Remove *callback* from *event*."""
        subs = self._subscribers.get(event)
        if not subs:
            return
        self._subscribers[event] = [
            (cb, is_weak)
            for cb, is_weak in subs
            if self._resolve(cb, is_weak) is not callback
        ]

    def emit(self, event: str, **data: Any) -> None:
        """Emit *event*, calling all subscribers with **data as kwargs.

        Exceptions in subscribers are logged and swallowed.
        """
        subs = self._subscribers.get(event)
        if not subs:
            return

        dead: List[int] = []
        for i, (cb, is_weak) in enumerate(subs):
            resolved = self._resolve(cb, is_weak)
            if resolved is None:
                dead.append(i)
                continue
            try:
                resolved(**data)
            except Exception:
                log.exception("Error in event handler for %s", event)

        # Clean up dead weakrefs
        if dead:
            for i in reversed(dead):
                subs.pop(i)

    def _resolve(self, cb: Any, is_weak: bool) -> Optional[Callable[..., Any]]:
        if is_weak:
            return cb()  # weakref -> call to dereference
        return cb

    def _cleanup(self, event: str, ref: Any) -> None:
        """Called when a weakref target is garbage-collected."""
        subs = self._subscribers.get(event)
        if subs:
            self._subscribers[event] = [
                (cb, w) for cb, w in subs if cb is not ref
            ]
