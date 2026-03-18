# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Core module — provides fundamental services."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.core")


class Module(ModuleBase):

    def initialize(self, services):
        from plugin.modules.core.services.document import DocumentService
        from plugin.modules.core.services.config import ConfigService
        from plugin.modules.core.services.events import EventBusService
        from plugin.modules.core.services.format import FormatService

        services.register(DocumentService())
        services.register(ConfigService())
        services.register(EventBusService())
        services.register(FormatService())

    def start(self, services):
        self._doc_svc = services.document
        self._cfg = services.config.proxy_for("core")
        self._services = services
        bus = services.events
        bus.subscribe("tool:completed", self._on_tool_completed)

        # --- idxV2: disabled for now ---
        # self._idle_timer = None
        # self._idle_delay = 3.0
        # self._rebuilding = False

    def start_background(self, services):
        pass
        # --- idxV2: disabled for now ---
        # self._attach_cursor_tracker()
        # self._reset_idle_timer()

    def _on_tool_completed(self, name=None, caller=None, result=None,
                           is_mutation=False, doc=None, **_kw):
        """Handle tool completion events."""
        # --- idxV2: follow_activity disabled ---
        # Auto-scroll caused freezes and wrong page jumps.
        # User uses panel "Show" button for navigation instead.
        pass

    # ==================================================================
    # idxV2: all below is disabled pending unified index redesign.
    # The goal is a single index that maps paragraphs, pages, images,
    # objects etc. without the current PageMap/idle rebuild complexity.
    # ==================================================================

    # def _reset_idle_timer(self):
    #     """Reset the idle timer. When it expires, rebuild caches."""
    #     import threading
    #     if self._idle_timer is not None:
    #         self._idle_timer.cancel()
    #     self._idle_timer = threading.Timer(
    #         self._idle_delay, self._on_idle)
    #     self._idle_timer.daemon = True
    #     self._idle_timer.start()

    # def _on_idle(self):
    #     """idxV2: idle cache rebuilder — disabled.
    #     Rebuilt para_ranges on main thread and swapped atomically.
    #     Problem: jumpToLastPage triggered cursor events → infinite loop.
    #     """
    #     pass

    # @staticmethod
    # def _statusbar_start(doc, text):
    #     """Show a brief message in the LO status bar."""
    #     try:
    #         frame = doc.getCurrentController().getFrame()
    #         sb = frame.createStatusIndicator()
    #         sb.start(text, 0)
    #         return sb
    #     except Exception:
    #         return None

    # @staticmethod
    # def _statusbar_end(sb, text=None):
    #     """Update and close status bar indicator."""
    #     if sb is None:
    #         return
    #     try:
    #         import threading
    #         from plugin.framework.main_thread import post_to_main_thread
    #         if text:
    #             sb.setText(text)
    #             sb.setValue(100)
    #         threading.Timer(
    #             2.0, lambda: post_to_main_thread(sb.end)).start()
    #     except Exception:
    #         pass

    # def _attach_cursor_tracker(self):
    #     """idxV2: cursor tracker — disabled.
    #     Attached XSelectionChangeListener to track current_page.
    #     Problem: events during rebuild caused infinite loop.
    #     """
    #     pass
