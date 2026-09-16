# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Core module — provides fundamental services."""

import logging

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.core")


def check_sqlite3(services):
    """Check if sqlite3 is functional. Used by Options check widget."""
    try:
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT sqlite_version()")
        version = conn.execute("SELECT sqlite_version()").fetchone()[0]
        conn.close()
        return {"status": "ok", "message": "sqlite3 %s (via %s)" % (
            version, getattr(sqlite3, '__name__', 'unknown'))}
    except ImportError:
        return {"status": "ko", "message": "sqlite3 not available"}
    except Exception as e:
        return {"status": "ko", "message": "sqlite3 broken: %s" % e}


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
        # Auto-install declared dependencies (e.g. pysqlite3 on Windows)
        try:
            from plugin.framework.deps import check_and_run_auto
            from plugin._manifest import MODULES
            manifest = next((m for m in MODULES if m["name"] == "core"), {})
            scripts = manifest.get("scripts", {})
            if scripts:
                check_and_run_auto("core", scripts, services)
        except Exception:
            log.debug("Auto-deps check failed", exc_info=True)

        self._attach_page_logger()
        # Pre-build paragraph cache in background after doc is loaded
        import threading
        threading.Thread(
            target=self._prebuild_cache,
            daemon=True, name="nelson-prebuild").start()

    def _prebuild_cache(self):
        """Wait for a document to load, then build para_ranges cache.

        Skips if the cache was already built by a tool call.
        """
        import time
        from plugin.framework.main_thread import post_to_main_thread
        from plugin.modules.core.services.document import DocumentCache

        # Wait for a document to be available (max 30s)
        doc = None
        for _ in range(15):
            time.sleep(2)
            try:
                doc = self._doc_svc.get_active_document()
                if doc and hasattr(doc, "getText"):
                    break
                doc = None
            except Exception:
                pass
        if doc is None:
            return

        def _build():
            # The cache registry compares UNO objects and registers a
            # listener on first use: main thread only.
            cache = DocumentCache.get(doc)
            if cache.para_ranges is not None:
                return
            try:
                sb = None
                try:
                    frame = doc.getCurrentController().getFrame()
                    sb = frame.createStatusIndicator()
                    sb.start("Nelson: indexing document...", 0)
                except Exception:
                    pass

                self._doc_svc.get_paragraph_ranges(doc)

                n = len(cache.para_ranges) if cache.para_ranges else 0
                if sb:
                    sb.setText("Nelson: %d paragraphs ready" % n)
                    sb.setValue(100)
                    import threading
                    threading.Timer(
                        3.0, lambda: post_to_main_thread(sb.end)
                    ).start()
            except Exception:
                log.debug("prebuild cache failed", exc_info=True)

        post_to_main_thread(_build)

    def _on_tool_completed(self, name=None, caller=None, result=None,
                           is_mutation=False, doc=None, **_kw):
        """Auto-scroll to mutation location when follow_activity is on.

        Uses the same goto_paragraph as the panel Show button.
        """
        if not is_mutation or caller != "mcp" or doc is None:
            return
        if not self._cfg.get("follow_activity", True):
            return
        if result is None or result.get("status") == "error":
            return
        pi = result.get("paragraph_index")
        if pi is None:
            pi = result.get("para_index")
        if pi is None or not isinstance(pi, int):
            return
        try:
            self._doc_svc.goto_paragraph(doc, pi)
        except Exception:
            pass

    def _attach_page_logger(self):
        """Debug: log every page change via XSelectionChangeListener."""
        try:
            import unohelper
            from com.sun.star.view import XSelectionChangeListener
            from plugin.framework.main_thread import post_to_main_thread

            doc_svc = self._doc_svc
            last_page = [0]

            class _PageLogger(unohelper.Base, XSelectionChangeListener):
                def selectionChanged(self, event):
                    try:
                        doc = doc_svc.get_active_document()
                        if doc is None:
                            return
                        vc = doc.getCurrentController().getViewCursor()
                        page = vc.getPage()
                        if page != last_page[0]:
                            log.debug("PAGE_CHANGE: %d -> %d",
                                        last_page[0], page)
                            last_page[0] = page
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
                    controller.addSelectionChangeListener(_PageLogger())
                except Exception:
                    pass

            post_to_main_thread(_attach)
        except Exception:
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
