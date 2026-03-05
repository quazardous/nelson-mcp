"""Sidebar panel factory — MCP Actions and Running Jobs panels.

Creates XUIElement / XToolPanel / XSidebarPanel for the Nelson sidebar deck.
Builds controls programmatically (no XDL) via panel_layout helpers.

Registered as a UNO component in META-INF/manifest.xml.
"""

import logging
import os
import sys
import threading
import time

# Ensure plugin parent is on path so "plugin.xxx" imports work
_this_dir = os.path.dirname(os.path.abspath(__file__))
_plugin_dir = os.path.join(_this_dir, os.pardir, os.pardir)
_parent = os.path.normpath(os.path.join(_plugin_dir, os.pardir))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

log = logging.getLogger("nelson.panel.factory")


def _get_arg(args, name):
    """Extract PropertyValue from UNO args by Name."""
    for pv in args:
        if hasattr(pv, "Name") and pv.Name == name:
            return pv.Value
    return None


def _fmt_time(ts):
    """Format a timestamp as HH:MM."""
    return time.strftime("%H:%M", time.localtime(ts))


def _fmt_duration(d):
    """Format duration in seconds to a readable string."""
    if d is None:
        return ""
    if d < 1:
        return "%.0fms" % (d * 1000)
    return "%.1fs" % d


def _fmt_elapsed(created_at):
    """Format elapsed time since created_at."""
    elapsed = time.time() - created_at
    if elapsed < 60:
        return "%ds" % int(elapsed)
    return "%dm%ds" % (int(elapsed) // 60, int(elapsed) % 60)


try:
    import uno
    import unohelper
    from com.sun.star.ui import (
        XUIElementFactory, XUIElement, XToolPanel, XSidebarPanel)
    from com.sun.star.ui.UIElementType import TOOLPANEL
    from com.sun.star.awt import XWindowListener, XItemListener

    # ── Shared panel wrapper ──────────────────────────────────────

    class NelsonToolPanel(unohelper.Base, XToolPanel, XSidebarPanel):
        """Holds the panel window; implements XToolPanel + XSidebarPanel."""

        def __init__(self, panel_window, parent_window, ctx):
            self.ctx = ctx
            self.PanelWindow = panel_window
            self.Window = panel_window
            self.parent_window = parent_window

        def getWindow(self):
            return self.Window

        def createAccessible(self, parent_accessible):
            return self.PanelWindow

        def getHeightForWidth(self, width):
            h = 280
            if self.parent_window and self.PanelWindow and width > 0:
                parent_rect = self.parent_window.getPosSize()
                if parent_rect.Height > 0:
                    h = parent_rect.Height
                self.PanelWindow.setPosSize(0, 0, width, h, 15)
            return uno.createUnoStruct(
                "com.sun.star.ui.LayoutSize", h, -1, h)

        def getMinimalWidth(self):
            return 180

    # ── Actions panel ─────────────────────────────────────────────

    class ActionsPanelElement(unohelper.Base, XUIElement):
        """MCP Actions history panel."""

        def __init__(self, ctx, frame, parent_window, resource_url):
            self.ctx = ctx
            self.xFrame = frame
            self.xParentWindow = parent_window
            self.ResourceURL = resource_url
            self.Frame = frame
            self.Type = TOOLPANEL
            self.toolpanel = None
            self._root = None
            self._action_log = None
            self._selected_index = -1

        def getRealInterface(self):
            if not self.toolpanel:
                try:
                    root = self._create_panel_window()
                    self.toolpanel = NelsonToolPanel(
                        root, self.xParentWindow, self.ctx)
                    self._wire(root)
                except Exception:
                    log.exception("ActionsPanelElement.getRealInterface failed")
                    raise
            return self.toolpanel

        def _create_panel_window(self):
            from plugin.framework.panel_layout import (
                create_panel_window, add_control)

            self._root = create_panel_window(self.ctx, self.xParentWindow)

            add_control(self.ctx, self._root, "label", "FixedText",
                        {"Label": "MCP Actions"})
            add_control(self.ctx, self._root, "list", "ListBox",
                        {"MultiSelection": False})
            add_control(self.ctx, self._root, "detail", "Edit",
                        {"ReadOnly": True, "MultiLine": True,
                         "VScroll": True})
            add_control(self.ctx, self._root, "image", "ImageControl",
                        {"ScaleImage": True, "ScaleMode": 1})
            return self._root

        def _wire(self, root):
            from plugin.main import bootstrap, get_services
            from plugin.framework.main_thread import post_to_main_thread

            bootstrap(self.ctx)
            services = get_services()

            self._action_log = services.get("action_log")

            label_ctrl = root.getControl("label")
            list_ctrl = root.getControl("list")
            detail_ctrl = root.getControl("detail")
            image_ctrl = root.getControl("image")

            image_ctrl.setVisible(False)

            ctrls = {
                "label": label_ctrl,
                "list": list_ctrl,
                "detail": detail_ctrl,
                "image": image_ctrl,
            }

            # ── List selection handler ────────────────────────────

            class _ListSelect(unohelper.Base, XItemListener):
                def __init__(self, panel_element):
                    self._pe = panel_element

                def itemStateChanged(self, evt):
                    try:
                        sel = list_ctrl.getSelectedItemPos()
                        self._pe._show_detail(sel, detail_ctrl, image_ctrl,
                                              root)
                    except Exception:
                        pass

                def disposing(self, evt):
                    pass

            list_ctrl.addItemListener(_ListSelect(self))

            # ── Resize handler ────────────────────────────────────

            class _Resize(unohelper.Base, XWindowListener):
                def windowResized(self, evt):
                    try:
                        _layout_panel(evt.Source, ctrls)
                    except Exception:
                        pass

                def windowMoved(self, evt):
                    pass

                def windowShown(self, evt):
                    pass

                def windowHidden(self, evt):
                    pass

                def disposing(self, evt):
                    pass

            root.addWindowListener(_Resize())

            # ── Event-driven refresh ──────────────────────────────

            def _refresh():
                try:
                    self._refresh_list(label_ctrl, list_ctrl)
                except Exception:
                    pass

            if self._action_log:
                self._action_log._on_change = lambda: post_to_main_thread(
                    _refresh)

            # Initial layout + data
            _layout_panel(root, ctrls)
            _refresh()

        def _refresh_list(self, label_ctrl, list_ctrl):
            """Rebuild the ListBox from action log entries."""
            if not self._action_log:
                return
            entries = self._action_log.entries(limit=100)
            total = self._action_log.count()

            label_ctrl.getModel().Label = "MCP Actions (%d)" % total

            list_ctrl.removeItems(0, list_ctrl.getItemCount())
            for entry in entries:
                ts = _fmt_time(entry.timestamp)
                dur = _fmt_duration(entry.duration)
                status = entry.status
                line = "%s %-20s %s" % (ts, entry.tool_name, status)
                if dur:
                    line += " %s" % dur
                list_ctrl.addItem(line, list_ctrl.getItemCount())

        def _show_detail(self, index, detail_ctrl, image_ctrl, root):
            """Show detail for the selected action entry."""
            if not self._action_log:
                return
            entries = self._action_log.entries(limit=100)
            if index < 0 or index >= len(entries):
                return
            self._selected_index = index
            entry = entries[index]

            lines = [
                "Tool: %s" % entry.tool_name,
                "Caller: %s" % (entry.caller or "-"),
                "Status: %s" % entry.status,
                "Time: %s" % _fmt_time(entry.timestamp),
            ]
            if entry.duration is not None:
                lines.append("Duration: %s" % _fmt_duration(entry.duration))
            if entry.error:
                lines.append("Error: %s" % entry.error)
            if entry.params_snippet:
                lines.append("Params: %s" % entry.params_snippet)

            detail_ctrl.getModel().Text = "\n".join(lines)

            # Image preview
            has_image = bool(entry.image_path
                             and os.path.isfile(entry.image_path))
            image_ctrl.setVisible(has_image)
            if has_image:
                image_ctrl.getModel().ImageURL = (
                    uno.systemPathToFileUrl(entry.image_path))

            # Re-layout to account for image visibility change
            ctrls = {
                "label": root.getControl("label"),
                "list": root.getControl("list"),
                "detail": detail_ctrl,
                "image": image_ctrl,
            }
            _layout_panel(root, ctrls)

    # ── Jobs panel ────────────────────────────────────────────────

    class JobsPanelElement(unohelper.Base, XUIElement):
        """Running Jobs panel."""

        def __init__(self, ctx, frame, parent_window, resource_url):
            self.ctx = ctx
            self.xFrame = frame
            self.xParentWindow = parent_window
            self.ResourceURL = resource_url
            self.Frame = frame
            self.Type = TOOLPANEL
            self.toolpanel = None
            self._root = None
            self._job_mgr = None
            self._timer = None
            self._alive = True
            self._selected_job_id = None

        def getRealInterface(self):
            if not self.toolpanel:
                try:
                    root = self._create_panel_window()
                    self.toolpanel = NelsonToolPanel(
                        root, self.xParentWindow, self.ctx)
                    self._wire(root)
                except Exception:
                    log.exception("JobsPanelElement.getRealInterface failed")
                    raise
            return self.toolpanel

        def _create_panel_window(self):
            from plugin.framework.panel_layout import (
                create_panel_window, add_control)

            self._root = create_panel_window(self.ctx, self.xParentWindow)

            add_control(self.ctx, self._root, "label", "FixedText",
                        {"Label": "Jobs"})
            add_control(self.ctx, self._root, "list", "ListBox",
                        {"MultiSelection": False})
            add_control(self.ctx, self._root, "detail", "Edit",
                        {"ReadOnly": True, "MultiLine": True,
                         "VScroll": True})
            add_control(self.ctx, self._root, "image", "ImageControl",
                        {"ScaleImage": True, "ScaleMode": 1})
            return self._root

        def _wire(self, root):
            from plugin.main import bootstrap, get_services
            from plugin.framework.main_thread import post_to_main_thread

            bootstrap(self.ctx)
            services = get_services()

            self._job_mgr = services.get("jobs")

            label_ctrl = root.getControl("label")
            list_ctrl = root.getControl("list")
            detail_ctrl = root.getControl("detail")
            image_ctrl = root.getControl("image")

            image_ctrl.setVisible(False)

            ctrls = {
                "label": label_ctrl,
                "list": list_ctrl,
                "detail": detail_ctrl,
                "image": image_ctrl,
            }

            # ── List selection handler ────────────────────────────

            class _ListSelect(unohelper.Base, XItemListener):
                def __init__(self, panel_element):
                    self._pe = panel_element

                def itemStateChanged(self, evt):
                    try:
                        sel = list_ctrl.getSelectedItemPos()
                        self._pe._show_detail(sel, detail_ctrl, image_ctrl,
                                              root)
                    except Exception:
                        pass

                def disposing(self, evt):
                    pass

            list_ctrl.addItemListener(_ListSelect(self))

            # ── Resize handler ────────────────────────────────────

            class _Resize(unohelper.Base, XWindowListener):
                def windowResized(self, evt):
                    try:
                        _layout_panel(evt.Source, ctrls)
                    except Exception:
                        pass

                def windowMoved(self, evt):
                    pass

                def windowShown(self, evt):
                    pass

                def windowHidden(self, evt):
                    pass

                def disposing(self, evt):
                    pass

            root.addWindowListener(_Resize())

            # ── Periodic refresh via timer ────────────────────────

            def _tick():
                while self._alive:
                    try:
                        post_to_main_thread(
                            lambda: self._refresh_list(
                                label_ctrl, list_ctrl))
                    except Exception:
                        pass
                    # Sleep in small increments so we can exit quickly
                    for _ in range(20):
                        if not self._alive:
                            break
                        threading.Event().wait(0.1)

            self._timer = threading.Thread(
                target=_tick, daemon=True, name="nelson-jobs-panel-timer")
            self._timer.start()

            # Initial layout + data
            _layout_panel(root, ctrls)
            self._refresh_list(label_ctrl, list_ctrl)

        def _refresh_list(self, label_ctrl, list_ctrl):
            """Rebuild the ListBox from job manager."""
            if not self._job_mgr:
                return
            jobs = self._job_mgr.list(limit=50)
            running = sum(1 for j in jobs if j.status in ("pending", "running"))

            if running:
                label_ctrl.getModel().Label = "Jobs (%d running)" % running
            else:
                label_ctrl.getModel().Label = "Jobs (%d)" % len(jobs)

            # Preserve selection
            prev_sel = list_ctrl.getSelectedItemPos()
            list_ctrl.removeItems(0, list_ctrl.getItemCount())

            self._job_ids = []
            for job in jobs:
                if job.status == "running":
                    icon = "\u27F3"  # rotating arrows
                    suffix = _fmt_elapsed(job.created_at)
                elif job.status == "done":
                    icon = "\u2713"  # checkmark
                    suffix = "done"
                elif job.status == "error":
                    icon = "\u2717"  # X mark
                    suffix = "err"
                else:
                    icon = "\u00B7"  # middle dot
                    suffix = "pending"

                line = "%s %s %s %s" % (
                    icon, job.job_id[:4], job.kind or "-", suffix)
                list_ctrl.addItem(line, list_ctrl.getItemCount())
                self._job_ids.append(job.job_id)

            # Restore selection if still valid
            if 0 <= prev_sel < list_ctrl.getItemCount():
                list_ctrl.selectItemPos(prev_sel, True)

        def _show_detail(self, index, detail_ctrl, image_ctrl, root):
            """Show detail for the selected job."""
            if not self._job_mgr or not hasattr(self, "_job_ids"):
                return
            if index < 0 or index >= len(self._job_ids):
                return
            job_id = self._job_ids[index]
            self._selected_job_id = job_id
            job = self._job_mgr.get(job_id)
            if not job:
                return

            lines = [
                "Job: %s" % job.job_id,
                "Kind: %s" % (job.kind or "-"),
                "Status: %s" % job.status,
                "Created: %s" % _fmt_time(job.created_at),
            ]
            if job.finished_at:
                dur = job.finished_at - job.created_at
                lines.append("Duration: %s" % _fmt_duration(dur))
            if job.params:
                params_str = str(job.params)
                if len(params_str) > 200:
                    params_str = params_str[:200] + "..."
                lines.append("Params: %s" % params_str)
            if job.result:
                result_str = str(job.result)
                if len(result_str) > 300:
                    result_str = result_str[:300] + "..."
                lines.append("Result: %s" % result_str)
            if job.error:
                lines.append("Error: %s" % job.error)

            detail_ctrl.getModel().Text = "\n".join(lines)

            # Image preview — extract file path from job result
            image_path = None
            if job.result and isinstance(job.result, dict):
                # Direct file_paths key
                paths = job.result.get("file_paths")
                # Or nested in value: {'value': ([paths], error)}
                if not paths:
                    val = job.result.get("value")
                    if isinstance(val, (list, tuple)) and val:
                        candidate = val[0]
                        if isinstance(candidate, list):
                            paths = candidate
                        elif isinstance(candidate, str):
                            paths = [candidate]
                if paths and isinstance(paths, list):
                    for p in paths:
                        if isinstance(p, str) and os.path.isfile(p):
                            image_path = p
                            break

            has_image = image_path is not None
            image_ctrl.setVisible(has_image)
            if has_image:
                image_ctrl.getModel().ImageURL = (
                    uno.systemPathToFileUrl(image_path))

            # Re-layout to account for image visibility change
            ctrls = {
                "label": root.getControl("label"),
                "list": root.getControl("list"),
                "detail": detail_ctrl,
                "image": image_ctrl,
            }
            _layout_panel(root, ctrls)

        def __del__(self):
            self._alive = False

    # ── Shared layout logic ───────────────────────────────────────

    def _layout_panel(win, ctrls):
        """Reflow panel controls to fill the available space.

        Layout:
        - Label: fixed 16px
        - ListBox: ~50% of remaining (or more if image hidden)
        - Detail Edit: ~25-35% of remaining
        - ImageControl: ~25% of remaining (hidden when no image)
        """
        r = win.getPosSize()
        w, h = r.Width, r.Height
        if w <= 0 or h <= 0:
            return

        m = 6
        gap = 4
        label_h = 16
        cw = w - 2 * m

        image_ctrl = ctrls.get("image")
        image_visible = (image_ctrl and image_ctrl.isVisible()
                         if image_ctrl else False)

        y = m
        c = ctrls.get("label")
        if c:
            c.setPosSize(m, y, cw, label_h, 15)
        y += label_h + gap

        remaining = h - y - m
        if remaining < 60:
            remaining = 60

        if image_visible:
            list_h = int(remaining * 0.45)
            detail_h = int(remaining * 0.25)
            image_h = remaining - list_h - detail_h - 2 * gap
        else:
            list_h = int(remaining * 0.55)
            detail_h = remaining - list_h - gap
            image_h = 0

        c = ctrls.get("list")
        if c:
            c.setPosSize(m, y, cw, list_h, 15)
        y += list_h + gap

        c = ctrls.get("detail")
        if c:
            c.setPosSize(m, y, cw, detail_h, 15)
        y += detail_h + gap

        if image_visible and image_ctrl:
            image_ctrl.setPosSize(m, y, cw, max(30, image_h), 15)

    # ── Factory ───────────────────────────────────────────────────

    class NelsonPanelFactory(unohelper.Base, XUIElementFactory):
        """Factory that creates Actions and Jobs panel elements."""

        def __init__(self, ctx):
            self.ctx = ctx

        def createUIElement(self, resource_url, args):
            log.info("createUIElement: %s", resource_url)

            frame = _get_arg(args, "Frame")
            parent_window = _get_arg(args, "ParentWindow")
            if not parent_window:
                from com.sun.star.lang import IllegalArgumentException
                raise IllegalArgumentException("ParentWindow is required")

            if "ActionsPanel" in resource_url:
                return ActionsPanelElement(
                    self.ctx, frame, parent_window, resource_url)
            if "JobsPanel" in resource_url:
                return JobsPanelElement(
                    self.ctx, frame, parent_window, resource_url)

            from com.sun.star.container import NoSuchElementException
            raise NoSuchElementException(
                "Unknown resource: " + resource_url)

    # Register with LibreOffice
    g_ImplementationHelper = unohelper.ImplementationHelper()
    g_ImplementationHelper.addImplementation(
        NelsonPanelFactory,
        "org.extension.nelson.NelsonPanelFactory",
        ("com.sun.star.ui.UIElementFactory",),
    )

except ImportError:
    # Not running inside LibreOffice
    pass
