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
        self._idle_timer = None
        self._idle_delay = 3.0  # seconds of idle before cache rebuild
        bus = services.events
        bus.subscribe("tool:completed", self._on_tool_completed)

    def start_background(self, services):
        self._attach_cursor_tracker()
        # Trigger initial cache build after idle
        self._reset_idle_timer()

    def _reset_idle_timer(self):
        """Reset the idle timer. When it expires, rebuild caches."""
        import threading
        if self._idle_timer is not None:
            self._idle_timer.cancel()
        self._idle_timer = threading.Timer(
            self._idle_delay, self._on_idle)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _on_idle(self):
        """Called when no activity for _idle_delay seconds.

        If the cache is dirty, rebuilds paragraph ranges on the
        main thread and swaps it in atomically.
        """
        try:
            from plugin.framework.main_thread import post_to_main_thread
            from plugin.modules.core.services.document import DocumentCache

            doc = self._doc_svc.get_active_document()
            if doc is None:
                return
            cache = DocumentCache.get(doc)
            if not cache.dirty:
                return

            def _rebuild():
                try:
                    # Status bar feedback
                    sb = self._statusbar_start(doc, "Nelson: indexing paragraphs...")
                    text = doc.getText()
                    enum = text.createEnumeration()
                    fresh = []
                    while enum.hasMoreElements():
                        fresh.append(enum.nextElement())
                    # Atomic swap
                    cache.para_ranges = fresh
                    cache.length = len(fresh)
                    cache.dirty = False
                    # Seed PageMap with doc dimensions
                    pmap = cache.page_map
                    pmap.set_total(len(fresh))
                    pmap.observe(0, 1)
                    try:
                        controller = doc.getCurrentController()
                        vc = controller.getViewCursor()
                        saved = vc.getPage()
                        vc.jumpToLastPage()
                        pmap.observe(len(fresh) - 1, vc.getPage())
                        vc.jumpToPage(saved)
                    except Exception:
                        pass
                    self._statusbar_end(sb,
                        "Nelson: %d paragraphs indexed" % len(fresh))
                    log.debug("idle: rebuilt para cache (%d paras)",
                              len(fresh))
                except Exception:
                    log.debug("idle: rebuild failed", exc_info=True)

            post_to_main_thread(_rebuild)
        except Exception:
            log.debug("idle: cache rebuild failed", exc_info=True)

    @staticmethod
    def _statusbar_start(doc, text):
        """Show a brief message in the LO status bar."""
        try:
            frame = doc.getCurrentController().getFrame()
            sb = frame.createStatusIndicator()
            sb.start(text, 0)
            return sb
        except Exception:
            return None

    @staticmethod
    def _statusbar_end(sb, text=None):
        """Update and close status bar indicator."""
        if sb is None:
            return
        try:
            import threading
            from plugin.framework.main_thread import post_to_main_thread
            if text:
                sb.setText(text)
                sb.setValue(100)
            threading.Timer(
                2.0, lambda: post_to_main_thread(sb.end)).start()
        except Exception:
            pass

    def _on_tool_completed(self, name=None, caller=None, result=None,
                           is_mutation=False, doc=None, **_kw):
        """Auto-scroll to mutation location when follow_activity is on."""
        # Schedule idle rebuild after any MCP mutation
        if is_mutation and caller == "mcp":
            self._reset_idle_timer()
        if not is_mutation or caller != "mcp" or doc is None:
            return
        if not self._cfg.get("follow_activity", True):
            return
        if result is None or result.get("status") == "error":
            return

        # Priority: paragraph_index → PageMap estimate → _page fallback
        pi = result.get("paragraph_index")
        if pi is None:
            pi = result.get("para_index")

        try:
            controller = doc.getCurrentController()
            vc = controller.getViewCursor()
            cur_page = vc.getPage()

            if pi is not None and isinstance(pi, int):
                # Use goto_paragraph (PageMap + jumpToPage, no scan)
                self._doc_svc.goto_paragraph(doc, pi)
            else:
                # Fallback to _page if no paragraph info
                page = result.get("_page") or result.get("page")
                if page and isinstance(page, int) and page != cur_page:
                    vc.jumpToPage(page)
        except Exception:
            log.debug("follow_activity: jump failed", exc_info=True)

    def _attach_cursor_tracker(self):
        """Attach a lightweight listener to track the current page."""
        try:
            import unohelper
            from com.sun.star.view import XSelectionChangeListener
            from plugin.modules.core.services.document import DocumentCache
            from plugin.framework.main_thread import post_to_main_thread

            doc_svc = self._doc_svc
            module = self

            class _CursorTracker(unohelper.Base, XSelectionChangeListener):
                """Ultra-light: reads vc.getPage() + resets idle timer."""

                def selectionChanged(self, event):
                    try:
                        doc = doc_svc.get_active_document()
                        if doc is None:
                            return
                        controller = doc.getCurrentController()
                        vc = controller.getViewCursor()
                        page = vc.getPage()
                        cache = DocumentCache.get(doc)
                        cache.current_page = page
                        # Reset idle rebuild timer
                        module._reset_idle_timer()
                    except Exception:
                        pass

                def disposing(self, event):
                    pass

            def _attach():
                doc = doc_svc.get_active_document()
                if doc is None:
                    return
                try:
                    controller = doc.getCurrentController()
                    controller.addSelectionChangeListener(_CursorTracker())
                    log.debug("Cursor tracker attached")
                except Exception:
                    log.debug("Could not attach cursor tracker", exc_info=True)

            post_to_main_thread(_attach)

        except Exception:
            log.debug("_attach_cursor_tracker failed", exc_info=True)
