# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""XContainerWindowEventHandler for Tools > Options > Nelson MCP pages.

Each module with config gets its own Options page (XDL generated at build time).
A hidden ``__module__`` control in each XDL identifies which module the page belongs to.

List-detail pages (widget: list_detail) are identified by an additional
``__list_detail__`` hidden control. They manage a JSON-serialized list of
items with add/remove/edit functionality.

The handler reads/writes config via ConfigService and emits config:changed events.

This file is registered as a UNO component in META-INF/manifest.xml.
"""

import json
import logging
import os
import sys

# Ensure plugin parent is on path so "plugin.xxx" imports work
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_plugin_dir)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import uno
import unohelper
from com.sun.star.awt import (
    XContainerWindowEventHandler, XActionListener, XItemListener,
    XAdjustmentListener)
from com.sun.star.lang import XServiceInfo

log = logging.getLogger("nelson.options")

# Ensure nelson logger has a handler (options_handler may load before main.py)
_nelson_logger = logging.getLogger("nelson")
if not _nelson_logger.handlers:
    _nelson_logger.propagate = False
    _lp = os.environ.get("NELSON_LOG_PATH",
                         os.path.join(os.path.expanduser("~"), "nelson.log"))
    _h = logging.FileHandler(_lp, mode="a", encoding="utf-8")
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s"))
    _nelson_logger.addHandler(_h)
    _nelson_logger.setLevel(logging.DEBUG)

log.info("options_handler.py module loaded")

# ── List-detail state and UNO listeners ──────────────────────────────


class _ListDetailState:
    """State for a list_detail widget on an Options page."""

    __slots__ = ("items", "item_fields", "field_name", "xWindow",
                 "selected_idx", "full_key", "name_field",
                 "label_func", "_updating", "_item_options")

    def __init__(self, items, item_fields, field_name, full_key, xWindow,
                 name_field="name", label_func=None):
        self.items = items
        self.item_fields = item_fields
        self.field_name = field_name
        self.full_key = full_key
        self.xWindow = xWindow
        self.selected_idx = -1
        self.name_field = name_field
        self.label_func = label_func
        self._updating = False
        self._item_options = {}  # fname -> resolved options list


class _ComboTextListener(unohelper.Base, XItemListener):
    """Select → text field sync for combo_text widget."""

    def __init__(self, sel_ctrl, txt_ctrl, values):
        self._sel = sel_ctrl
        self._txt = txt_ctrl
        self._values = values

    def itemStateChanged(self, event):
        try:
            idx = self._sel.getSelectedItemPos()
            if 0 <= idx < len(self._values):
                val = self._values[idx]
                if val is not None:  # not "(custom)"
                    self._txt.getModel().Text = val
        except Exception:
            pass

    def disposing(self, event):
        pass


class _LDItemListener(unohelper.Base, XItemListener):
    """Listbox item selection listener for list_detail."""

    def __init__(self, state, handler):
        self._state = state
        self._handler = handler

    def itemStateChanged(self, evt):
        if self._state._updating:
            return
        try:
            listbox = self._handler._get_control(
                self._state.xWindow, "lst_%s" % self._state.field_name)
            if listbox:
                new_idx = listbox.getSelectedItemPos()
                if new_idx != self._state.selected_idx:
                    self._handler._ld_on_select(self._state, new_idx)
        except Exception:
            log.exception("itemStateChanged failed")

    def disposing(self, evt):
        pass


class _LDAddListener(unohelper.Base, XActionListener):
    """Add button listener for list_detail."""

    def __init__(self, state, handler):
        self._state = state
        self._handler = handler

    def actionPerformed(self, evt):
        try:
            self._handler._ld_on_add(self._state)
        except Exception:
            log.exception("Add button failed")

    def disposing(self, evt):
        pass


class _LDRemoveListener(unohelper.Base, XActionListener):
    """Remove button listener for list_detail."""

    def __init__(self, state, handler):
        self._state = state
        self._handler = handler

    def actionPerformed(self, evt):
        try:
            self._handler._ld_on_remove(self._state)
        except Exception:
            log.exception("Remove button failed")

    def disposing(self, evt):
        pass


class _LDApplyListener(unohelper.Base, XActionListener):
    """Apply button listener for list_detail — saves current detail fields."""

    def __init__(self, state, handler):
        self._state = state
        self._handler = handler

    def actionPerformed(self, evt):
        try:
            self._handler._ld_save_current_detail(self._state)
        except Exception:
            log.exception("Apply button failed")

    def disposing(self, evt):
        pass


# ── Button action listener ───────────────────────────────────────────


class _ButtonActionListener(unohelper.Base, XActionListener):
    """Calls a user-defined callback when a button widget is clicked.

    An optional *flush* closure saves current dialog values to the
    registry before calling the action — so callbacks can read
    up-to-date config values (e.g. a select picked by the user).
    """

    def __init__(self, action_path, confirm_msg=None, flush=None):
        self._action_path = action_path
        self._confirm_msg = confirm_msg
        self._flush = flush

    def actionPerformed(self, evt):
        try:
            log.debug("Button clicked: %s", self._action_path)
            if self._confirm_msg:
                if not self._confirm(evt):
                    return
            if self._flush:
                try:
                    self._flush()
                except Exception:
                    log.debug("Button: config flush failed (non-critical)",
                              exc_info=True)
            module_path, func_name = self._action_path.rsplit(":", 1)
            import importlib
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            func()
        except Exception:
            log.exception("Button action failed: %s", self._action_path)

    def _confirm(self, evt):
        """Show a Yes/No confirmation dialog. Returns True if user clicks Yes."""
        try:
            from plugin.framework.uno_context import get_ctx
            ctx = get_ctx()
            if not ctx:
                return True
            smgr = ctx.ServiceManager
            desktop = smgr.createInstanceWithContext(
                "com.sun.star.frame.Desktop", ctx)
            frame = desktop.getCurrentFrame()
            if frame is None:
                return True
            window = frame.getContainerWindow()
            toolkit = smgr.createInstanceWithContext(
                "com.sun.star.awt.Toolkit", ctx)
            # MessageBoxType QUERYBOX=4, MessageBoxButtons YES_NO=3
            box = toolkit.createMessageBox(
                window, 4, 3, "Confirm", self._confirm_msg)
            result = box.execute()
            return result == 2  # YES
        except Exception:
            log.exception("Confirmation dialog failed")
            return False

    def disposing(self, evt):
        pass


# ── Browse button listener ───────────────────────────────────────────


class _BrowseListener(unohelper.Base, XActionListener):
    """Opens a FilePicker and writes the result to a paired textfield."""

    def __init__(self, text_ctrl, widget, file_filter=""):
        self._text_ctrl = text_ctrl
        self._widget = widget  # "file" or "folder"
        self._file_filter = file_filter

    def actionPerformed(self, evt):
        try:
            from plugin.framework.uno_context import get_ctx
            ctx = get_ctx()
            if not ctx:
                return
            smgr = ctx.ServiceManager
            if self._widget == "folder":
                picker = smgr.createInstanceWithContext(
                    "com.sun.star.ui.dialogs.FolderPicker", ctx)
                current = self._text_ctrl.getModel().Text
                if current:
                    import uno
                    picker.setDisplayDirectory(
                        uno.systemPathToFileUrl(current))
                if picker.execute() == 1:
                    import uno
                    path = uno.fileUrlToSystemPath(picker.getDirectory())
                    self._text_ctrl.getModel().Text = path
            else:
                picker = smgr.createInstanceWithContext(
                    "com.sun.star.ui.dialogs.FilePicker", ctx)
                if self._file_filter:
                    parts = self._file_filter.split("|")
                    for i in range(0, len(parts) - 1, 2):
                        picker.appendFilter(parts[i].strip(),
                                            parts[i + 1].strip())
                current = self._text_ctrl.getModel().Text
                if current:
                    import uno
                    import os
                    parent = os.path.dirname(current)
                    if parent:
                        picker.setDisplayDirectory(
                            uno.systemPathToFileUrl(parent))
                if picker.execute() == 1:
                    import uno
                    files = picker.getFiles()
                    if files:
                        path = uno.fileUrlToSystemPath(files[0])
                        self._text_ctrl.getModel().Text = path
        except Exception:
            log.exception("Browse action failed")

    def disposing(self, evt):
        pass


# ── Scroll listener ──────────────────────────────────────────────────


# Layout constants — single source of truth in plugin/_layout.py
# Loaded via exec() because UNO's import system can't resolve plugin._layout
_layout_ns = {}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_layout.py'), encoding='utf-8') as _f:
    exec(_f.read(), _layout_ns)
_PAGE_WIDTH = _layout_ns['PAGE_WIDTH']
_PAGE_HEIGHT = _layout_ns['PAGE_HEIGHT']
_SCROLLBAR_WIDTH = _layout_ns['SCROLLBAR_WIDTH']
_CONTENT_WIDTH = _layout_ns['CONTENT_WIDTH']
_VISIBLE_HEIGHT = 185   # actual visible area in LO Options (official max)
_OVERFLOW_TWEAK = 60    # extra DLU so last controls are fully visible when scrolled


class _ScrollListener(unohelper.Base, XAdjustmentListener):
    """Repositions controls when the scrollbar value changes."""

    def __init__(self, original_positions):
        # original_positions: list of (control_model, original_posY)
        self._positions = original_positions

    def adjustmentValueChanged(self, evt):
        scroll_val = evt.Value
        for model, orig_y in self._positions:
            model.PositionY = orig_y - scroll_val

    def reset(self):
        """Restore all controls to their original Y positions."""
        for model, orig_y in self._positions:
            model.PositionY = orig_y

    def disposing(self, evt):
        pass


# ── Tab listener ─────────────────────────────────────────────────────


class _TabListener(unohelper.Base, XItemListener):
    """Show/hide control groups when the tab selector changes."""

    def __init__(self, tab_data, xWindow):
        self._tab_data = tab_data  # {"tabs": [...], "controls": {...}}
        self._xWindow = xWindow

    def itemStateChanged(self, evt):
        idx = evt.Selected
        tabs = self._tab_data["tabs"]
        if idx < 0 or idx >= len(tabs):
            return
        _apply_tab_visibility(self._xWindow, self._tab_data, idx)

    def disposing(self, evt):
        pass


def _apply_tab_visibility(xWindow, tab_data, active_idx):
    """Show controls for active tab, hide all others."""
    tabs = tab_data["tabs"]
    controls = tab_data["controls"]
    active_tab = tabs[active_idx] if active_idx < len(tabs) else tabs[0]
    active_ids = set(controls.get(active_tab, []))

    # Collect all tab-managed IDs
    all_tab_ids = set()
    for ids in controls.values():
        all_tab_ids.update(ids)

    shown = 0
    hidden = 0
    missing = 0
    for ctrl_id in all_tab_ids:
        try:
            ctrl = xWindow.getControl(ctrl_id)
            if ctrl:
                visible = ctrl_id in active_ids
                ctrl.setVisible(visible)
                if visible:
                    shown += 1
                else:
                    hidden += 1
            else:
                missing += 1
        except Exception:
            missing += 1

    log.debug("Tab visibility: active=%s shown=%d hidden=%d missing=%d",
              active_tab, shown, hidden, missing)


# ── Main handler ─────────────────────────────────────────────────────


class OptionsHandler(unohelper.Base, XContainerWindowEventHandler, XServiceInfo):
    """Handles initialize / ok / back events for all Nelson MCP Options pages."""

    IMPLE_NAME = "org.extension.nelson.OptionsHandler"
    SERVICE_NAMES = (IMPLE_NAME,)

    def __init__(self, ctx):
        self.ctx = ctx
        self._cached_values = {}  # full_key -> value at init time
        self._ld_states = {}      # full_key -> _ListDetailState
        self._scroll_listeners = {}  # id(xWindow) -> _ScrollListener

    # ── XContainerWindowEventHandler ─────────────────────────────────

    def callHandlerMethod(self, xWindow, eventObject, methodName):
        log.info("OptionsHandler: method=%s event=%s", methodName, eventObject)
        if methodName != "external_event":
            return False
        try:
            if eventObject == "initialize":
                self._on_initialize(xWindow)
                return True
            elif eventObject == "ok":
                self._on_ok(xWindow)
                return True
            elif eventObject == "back":
                self._on_back(xWindow)
                return True
        except Exception:
            log.exception("OptionsHandler event '%s' failed", eventObject)
        return False

    def getSupportedMethodNames(self):
        return ("external_event",)

    # ── XServiceInfo ─────────────────────────────────────────────────

    def supportsService(self, name):
        return name in self.SERVICE_NAMES

    def getImplementationName(self):
        return self.IMPLE_NAME

    def getSupportedServiceNames(self):
        return self.SERVICE_NAMES

    # ── Event handlers ───────────────────────────────────────────────

    def _on_initialize(self, xWindow):
        """Load config values into the Options page controls."""
        module_name = self._detect_module(xWindow)
        # Reset scroll state to avoid polluting other pages
        self._reset_scroll(xWindow)
        if not module_name:
            log.warning("Could not detect module from Options page")
            return

        # Check if this is a list_detail page
        ld_field = self._detect_list_detail(xWindow)
        if ld_field:
            self._ld_on_initialize(xWindow, module_name, ld_field)
            return

        manifest = self._get_manifest()
        mod_config = self._get_module_config(manifest, module_name)
        config_svc = self._get_config_service()

        if mod_config:
            self._load_module_fields(xWindow, module_name, mod_config,
                                     config_svc, prefix="")

        # Handle inline submodules (e.g. tunnel.bore, tunnel.ngrok)
        inline_names = self._detect_inline_modules(xWindow)
        if inline_names:
            for child_name in inline_names:
                child_config = self._get_module_config(manifest, child_name)
                if not child_config:
                    continue
                child_safe = child_name.replace(".", "_")
                self._load_module_fields(
                    xWindow, child_name, child_config, config_svc,
                    prefix=child_safe + "__")

        self._setup_tabs(xWindow)
        self._setup_scroll(xWindow)

    def _log_control_positions(self, xWindow, module_name, phase):
        """Log position/size of the container and all controls for debugging."""
        try:
            pos = xWindow.getPosSize()
            model = xWindow.getModel()
            lines = ["[%s] module=%s win=(%d,%d,%dx%d) model=%dx%ddlu" % (
                phase, module_name, pos.X, pos.Y, pos.Width, pos.Height,
                getattr(model, 'Width', 0), getattr(model, 'Height', 0))]
            for ctrl in xWindow.getControls():
                m = ctrl.getModel()
                name = getattr(m, "Name", "?")
                if name.startswith("__") and name != "__scrollbar__":
                    continue  # skip hidden metadata controls
                cp = ctrl.getPosSize()  # pixel position
                lines.append("  %s: dlu(%d,%d,%d,%d) px(%d,%d,%d,%d)" % (
                    name, m.PositionX, m.PositionY, m.Width, m.Height,
                    cp.X, cp.Y, cp.Width, cp.Height))
            log.debug("Control positions:\n%s", "\n".join(lines))
        except Exception:
            log.debug("_log_control_positions failed", exc_info=True)

    def _load_module_fields(self, xWindow, module_name, mod_config,
                            config_svc, prefix=""):
        """Load config fields into controls, with optional ID prefix."""
        for field_name, schema in mod_config.items():
            widget = schema.get("widget", "text")
            if widget == "list_detail":
                if not prefix and schema.get("inline"):
                    self._ld_on_initialize(xWindow, module_name, field_name)
                continue  # non-inline handled on separate page

            if widget == "button":
                ctrl_id = prefix + field_name
                ctrl = self._get_control(xWindow, ctrl_id)
                action_path = schema.get("action")
                log.debug("Button widget: ctrl_id=%s, ctrl=%s, action=%s",
                          ctrl_id, ctrl, action_path)
                if action_path and ctrl:
                    flush = lambda _w=xWindow: self._on_ok(_w)
                    ctrl.addActionListener(
                        _ButtonActionListener(action_path,
                                              confirm_msg=schema.get("confirm"),
                                              flush=flush))
                # Update helper with last-launch info for script buttons
                if field_name.startswith("__script_") and field_name.endswith("__"):
                    self._update_script_helper(
                        xWindow, ctrl_id, module_name, field_name, schema)
                continue  # buttons don't store config values

            if widget == "check":
                ctrl_id = prefix + field_name
                ctrl = self._get_control(xWindow, ctrl_id)
                if ctrl:
                    self._run_check(ctrl, schema)
                continue  # checks don't store config values

            full_key = "%s.%s" % (module_name, field_name)

            # Read via ConfigService (uses global ctx via get_ctx())
            val = config_svc.get(full_key) if config_svc else None
            if val is None:
                val = schema.get("default")

            # If value is empty and a default_provider is defined, use it
            if not val and schema.get("default_provider"):
                val = self._call_default_provider(schema["default_provider"])

            self._cached_values[full_key] = val

            ctrl_id = prefix + field_name
            ctrl = self._get_control(xWindow, ctrl_id)
            if ctrl is None:
                continue

            try:
                if widget == "checkbox":
                    ctrl.getModel().State = 1 if val else 0
                elif widget in ("text", "password", "file", "folder"):
                    ctrl.getModel().Text = str(val) if val else ""
                elif widget == "textarea":
                    ctrl.getModel().Text = str(val) if val else ""
                elif widget in ("number", "slider"):
                    ctrl.getModel().Value = float(val) if val is not None else 0
                elif widget == "select":
                    resolved = self._resolve_options(schema)
                    self._populate_select(ctrl, resolved, val)
                elif widget == "combo":
                    resolved = self._resolve_options(schema)
                    self._populate_combo(ctrl, resolved, val)
                elif widget == "combo_text":
                    resolved = self._resolve_options(schema)
                    self._setup_combo_text(xWindow, ctrl_id, resolved, val)
            except Exception:
                log.exception("Error loading %s", full_key)

            # Wire browse button for file/folder widgets
            if widget in ("file", "folder"):
                btn = self._get_control(xWindow, "btn_%s" % ctrl_id)
                if btn and ctrl:
                    btn.addActionListener(_BrowseListener(
                        ctrl, widget, schema.get("file_filter", "")))

    def _on_ok(self, xWindow):
        """Write control values via ConfigService and emit event."""
        module_name = self._detect_module(xWindow)
        if not module_name:
            return

        # Check if this is a list_detail page
        ld_field = self._detect_list_detail(xWindow)
        if ld_field:
            self._ld_on_ok(xWindow, module_name, ld_field)
            return

        manifest = self._get_manifest()
        mod_config = self._get_module_config(manifest, module_name)

        config_svc = self._get_config_service()
        if not config_svc:
            log.error("_on_ok: ConfigService not available")
            return

        changes = {}
        if mod_config:
            changes = self._save_module_fields(xWindow, module_name, mod_config,
                                               prefix="")

        # Handle inline submodules
        inline_names = self._detect_inline_modules(xWindow)
        if inline_names:
            for child_name in inline_names:
                child_config = self._get_module_config(manifest, child_name)
                if not child_config:
                    continue
                child_safe = child_name.replace(".", "_")
                child_changes = self._save_module_fields(
                    xWindow, child_name, child_config,
                    prefix=child_safe + "__")
                changes.update(child_changes)

        if changes:
            diffs = config_svc.set_batch(changes, old_values=self._cached_values)
            # Update cache with new values
            for key, val in changes.items():
                self._cached_values[key] = val
            if diffs:
                log.info("_on_ok: %d change(s) saved for %s", len(diffs), module_name)

    def _save_module_fields(self, xWindow, module_name, mod_config, prefix=""):
        """Read control values for a module's fields. Returns dict of changes."""
        changes = {}
        for field_name, schema in mod_config.items():
            widget = schema.get("widget", "text")
            if widget == "list_detail":
                if not prefix and schema.get("inline"):
                    self._ld_on_ok(xWindow, module_name, field_name)
                continue
            if widget in ("button", "check"):
                continue  # buttons/checks don't store config values

            full_key = "%s.%s" % (module_name, field_name)
            field_type = schema.get("type", "string")

            ctrl_id = prefix + field_name
            ctrl = self._get_control(xWindow, ctrl_id)
            if ctrl is None:
                continue

            try:
                resolved = self._resolve_options(schema) if widget == "select" else schema
                new_val = self._read_control(ctrl, widget, field_type, resolved)
                changes[full_key] = new_val
            except Exception:
                log.exception("_on_ok: read control FAILED for %s", full_key)
        return changes

    def _on_back(self, xWindow):
        """Revert unsaved changes — reset scroll and reload config values.

        Unlike _on_initialize, does NOT re-setup scroll or tabs because the
        page is being deactivated (Cancel or page switch).
        """
        self._reset_scroll(xWindow)

        module_name = self._detect_module(xWindow)
        if not module_name:
            return

        # Check if this is a list_detail page
        ld_field = self._detect_list_detail(xWindow)
        if ld_field:
            self._ld_on_initialize(xWindow, module_name, ld_field)
            return

        manifest = self._get_manifest()
        mod_config = self._get_module_config(manifest, module_name)
        config_svc = self._get_config_service()

        if mod_config:
            self._load_module_fields(xWindow, module_name, mod_config,
                                     config_svc, prefix="")

        inline_names = self._detect_inline_modules(xWindow)
        if inline_names:
            for child_name in inline_names:
                child_config = self._get_module_config(manifest, child_name)
                if not child_config:
                    continue
                child_safe = child_name.replace(".", "_")
                self._load_module_fields(
                    xWindow, child_name, child_config, config_svc,
                    prefix=child_safe + "__")

    # ── List-detail page handlers ────────────────────────────────────

    def _ld_on_initialize(self, xWindow, module_name, field_name):
        """Initialize a list_detail page."""
        full_key = "%s.%s" % (module_name, field_name)

        manifest = self._get_manifest()
        mod_config = self._get_module_config(manifest, module_name)
        schema = mod_config.get(field_name, {})
        item_fields = schema.get("item_fields", {})
        name_field = schema.get("name_field", "name")

        # Resolve label_func (optional Python callable path)
        label_func = self._resolve_label_func(schema.get("label_func"))

        config_svc = self._get_config_service()
        json_str = config_svc.get(full_key) if config_svc else None
        if json_str is None:
            json_str = schema.get("default", "[]")

        try:
            items = json.loads(json_str)
            if not isinstance(items, list):
                items = []
        except (json.JSONDecodeError, TypeError):
            items = []

        self._cached_values[full_key] = json_str

        state = _ListDetailState(
            items=items,
            item_fields=item_fields,
            field_name=field_name,
            full_key=full_key,
            xWindow=xWindow,
            name_field=name_field,
            label_func=label_func,
        )
        self._ld_states[full_key] = state

        # Pre-resolve options for select/combo item_fields (options_from / options_provider)
        for fname, fschema in item_fields.items():
            if fschema.get("widget") not in ("select", "combo"):
                continue
            options = list(fschema.get("options", []))
            # options_from: reference another config field's options
            ref = fschema.get("options_from")
            if ref:
                ref_schema = mod_config.get(ref, {})
                ref_resolved = self._resolve_options(ref_schema)
                ref_options = ref_resolved.get("options", [])
                seen = {o.get("value") for o in options}
                options = [o for o in ref_options if o.get("value") not in seen] + options
            # options_provider: call a function directly
            elif fschema.get("options_provider"):
                resolved = self._resolve_options(fschema)
                extra = resolved.get("options", [])
                seen = {o.get("value") for o in options}
                options = [o for o in extra if o.get("value") not in seen] + options
            if options:
                state._item_options[fname] = options

        # Populate listbox
        listbox = self._get_control(xWindow, "lst_%s" % field_name)
        if listbox:
            labels = tuple(
                self._ld_get_item_label(state, item) for item in items)
            listbox.getModel().StringItemList = labels
            if items:
                listbox.selectItemPos(0, True)
                state.selected_idx = 0

            # Attach item selection listener
            listbox.addItemListener(_LDItemListener(state, self))

        # Show first item's details (or blank)
        self._ld_show_detail(state, 0 if items else -1)

        # Wire add/remove/apply buttons
        add_btn = self._get_control(xWindow, "add_%s" % field_name)
        if add_btn:
            add_btn.addActionListener(_LDAddListener(state, self))

        del_btn = self._get_control(xWindow, "del_%s" % field_name)
        if del_btn:
            del_btn.addActionListener(_LDRemoveListener(state, self))

        apply_btn = self._get_control(xWindow, "apply_%s" % field_name)
        if apply_btn:
            apply_btn.addActionListener(_LDApplyListener(state, self))

        # Wire browse buttons for file/folder item_fields
        for fname, fschema in item_fields.items():
            if fschema.get("widget") not in ("file", "folder"):
                continue
            ctrl_id = "%s__%s" % (field_name, fname)
            ctrl = self._get_control(xWindow, ctrl_id)
            btn = self._get_control(xWindow, "btn_%s" % ctrl_id)
            if btn and ctrl:
                btn.addActionListener(_BrowseListener(
                    ctrl, fschema["widget"], fschema.get("file_filter", "")))

        self._setup_scroll(xWindow)

        log.info("List-detail initialized: %s (%d items)", full_key, len(items))

    def _ld_on_ok(self, xWindow, module_name, field_name):
        """Save list_detail state to config as JSON."""
        full_key = "%s.%s" % (module_name, field_name)
        state = self._ld_states.get(full_key)
        if not state:
            return

        # Save current detail fields to current item
        self._ld_save_current_detail(state)

        # Serialize to JSON
        new_json = json.dumps(state.items, ensure_ascii=False)
        old_json = self._cached_values.get(full_key, "[]")

        config_svc = self._get_config_service()
        if config_svc and new_json != old_json:
            config_svc.set(full_key, new_json, caller_module=None)
            self._cached_values[full_key] = new_json
            log.info("List-detail saved: %s (%d items)",
                     full_key, len(state.items))

    def _ld_on_select(self, state, new_idx):
        """Handle listbox selection change."""
        if state.selected_idx >= 0:
            self._ld_save_current_detail(state, update_label=False)
        state.selected_idx = new_idx
        self._ld_show_detail(state, new_idx)

    def _ld_on_add(self, state):
        """Add a new item."""
        # Save current detail (no label update, we're switching away)
        if state.selected_idx >= 0:
            self._ld_save_current_detail(state, update_label=False)

        # Create item with defaults
        new_item = {}
        for fname, fschema in state.item_fields.items():
            default = fschema.get("default")
            if default is not None:
                new_item[fname] = default
            else:
                new_item[fname] = ""
        if state.name_field in new_item or state.name_field in state.item_fields:
            new_item[state.name_field] = "New"

        state.items.append(new_item)
        idx = len(state.items) - 1

        listbox = self._get_control(state.xWindow, "lst_%s" % state.field_name)
        if listbox:
            listbox.addItem(self._ld_get_item_label(state, new_item), idx)
            listbox.selectItemPos(idx, True)

        state.selected_idx = idx
        self._ld_show_detail(state, idx)

    def _ld_on_remove(self, state):
        """Remove the selected item."""
        idx = state.selected_idx
        if idx < 0 or idx >= len(state.items):
            return

        state.items.pop(idx)

        listbox = self._get_control(state.xWindow, "lst_%s" % state.field_name)
        if listbox:
            listbox.removeItems(idx, 1)

        if state.items:
            new_idx = min(idx, len(state.items) - 1)
            state.selected_idx = new_idx
            if listbox:
                listbox.selectItemPos(new_idx, True)
            self._ld_show_detail(state, new_idx)
        else:
            state.selected_idx = -1
            self._ld_show_detail(state, -1)

    def _ld_show_detail(self, state, idx):
        """Populate detail fields from an item (or clear if idx=-1)."""
        item = state.items[idx] if 0 <= idx < len(state.items) else {}
        has_item = 0 <= idx < len(state.items)

        for fname, fschema in state.item_fields.items():
            ctrl_id = "%s__%s" % (state.field_name, fname)
            ctrl = self._get_control(state.xWindow, ctrl_id)
            if ctrl is None:
                continue

            widget = fschema.get("widget", "text")
            val = item.get(fname, fschema.get("default", ""))

            try:
                if widget == "checkbox":
                    ctrl.getModel().State = 1 if val else 0
                elif widget in ("text", "password"):
                    ctrl.getModel().Text = str(val) if val else ""
                elif widget in ("number", "slider"):
                    ctrl.getModel().Value = float(val) if val is not None else 0
                elif widget == "select":
                    opts = state._item_options.get(fname)
                    sel_schema = dict(fschema, options=opts) if opts else fschema
                    self._populate_select(ctrl, sel_schema, val)
                elif widget == "combo":
                    opts = state._item_options.get(fname)
                    combo_schema = dict(fschema, options=opts) if opts else fschema
                    self._populate_combo(ctrl, combo_schema, val)
                elif widget == "combo_text":
                    self._setup_combo_text(
                        state.xWindow, ctrl_id, fschema, val)
                else:
                    ctrl.getModel().Text = str(val) if val else ""

                ctrl.getModel().Enabled = has_item
                # Also enable/disable the select part of combo_text
                if widget == "combo_text":
                    sel = self._get_control(
                        state.xWindow, "sel_%s" % ctrl_id)
                    if sel:
                        sel.getModel().Enabled = has_item
            except Exception:
                log.exception("Error showing detail field %s", ctrl_id)

    def _ld_save_current_detail(self, state, update_label=True):
        """Save detail fields to the current item.

        Args:
            update_label: If True, also update the listbox display text.
                Set to False when called during selection change to avoid glitch.
        """
        idx = state.selected_idx
        if idx < 0 or idx >= len(state.items):
            return

        item = state.items[idx]

        for fname, fschema in state.item_fields.items():
            ctrl_id = "%s__%s" % (state.field_name, fname)
            ctrl = self._get_control(state.xWindow, ctrl_id)
            if ctrl is None:
                continue

            widget = fschema.get("widget", "text")
            field_type = fschema.get("type", "string")
            try:
                if widget == "select" and fname in state._item_options:
                    read_schema = dict(fschema, options=state._item_options[fname])
                else:
                    read_schema = fschema
                item[fname] = self._read_control(ctrl, widget, field_type, read_schema)
            except Exception:
                log.exception("Error reading detail field %s", ctrl_id)

        if not update_label:
            return

        # Update listbox display text using remove+add to avoid full list reset
        listbox = self._get_control(state.xWindow, "lst_%s" % state.field_name)
        if listbox and idx >= 0:
            new_label = self._ld_get_item_label(state, item)
            try:
                state._updating = True
                listbox.removeItems(idx, 1)
                listbox.addItem(new_label, idx)
                listbox.selectItemPos(idx, True)
            except Exception:
                log.debug("Failed to update listbox text at %d", idx)
            finally:
                state._updating = False

    # ── List-detail label helpers ────────────────────────────────────

    def _ld_get_item_label(self, state, item):
        """Compute the display label for a list_detail item.

        If a label_func is set, call it. Otherwise join all field values
        with " - ".
        """
        if state.label_func:
            try:
                return state.label_func(item)
            except Exception:
                log.debug("label_func failed, falling back to default")

        # Default: join all field values with " - "
        parts = []
        for fname in state.item_fields:
            val = item.get(fname, "")
            if val:
                parts.append(str(val))
        return " - ".join(parts) if parts else "?"

    def _resolve_label_func(self, func_path):
        """Import a label_func from a dotted path. Returns callable or None."""
        if not func_path:
            return None
        try:
            module_path, func_name = func_path.rsplit(":", 1)
            import importlib
            mod = importlib.import_module(module_path)
            return getattr(mod, func_name)
        except Exception:
            log.exception("Failed to resolve label_func: %s", func_path)
            return None

    # ── Scroll support ────────────────────────────────────────────────

    def _reset_scroll(self, xWindow):
        """Restore original positions of all controls (doc_undo scroll offset).

        Prefers the stored _ScrollListener which holds exact original positions.
        Falls back to arithmetic (PositionY + ScrollValue) when no listener.
        """
        scroll_id = "__scrollbar__"
        listener = self._scroll_listeners.pop(id(xWindow), None)
        try:
            dialog_model = xWindow.getModel()
            has_sb = dialog_model.hasByName(scroll_id)

            if listener is not None:
                # Best path: restore exact original positions
                listener.reset()
                log.debug("_reset_scroll: restored via listener")
            elif has_sb:
                # Fallback: arithmetic reversal
                sb_model = dialog_model.getByName(scroll_id)
                scroll_val = getattr(sb_model, "ScrollValue", 0) or 0
                if scroll_val:
                    controls = xWindow.getControls()
                    for ctrl in controls:
                        m = ctrl.getModel()
                        if getattr(m, "Name", "") == scroll_id:
                            continue
                        m.PositionY = m.PositionY + scroll_val
                    log.debug("_reset_scroll: reversed offset %d (fallback)", scroll_val)

            # Remove scrollbar control and model
            if has_sb:
                dialog_model.removeByName(scroll_id)
        except Exception:
            log.debug("_reset_scroll: cleanup error", exc_info=True)

    def _setup_tabs(self, xWindow):
        """Set up tab switching if __tabs__ hidden control exists."""
        tab_data = self._detect_tabs(xWindow)
        if not tab_data:
            log.debug("_setup_tabs: no tab data found")
            return

        try:
            tabs = tab_data.get("tabs", [])
            if len(tabs) < 2:
                log.debug("_setup_tabs: only %d tab(s), skipping", len(tabs))
                return

            selector = self._get_control(xWindow, "__tab_selector__")
            if not selector:
                log.warning("_setup_tabs: __tab_selector__ control not found")
                return

            model = selector.getModel()

            # Set items on model (persists across page switches, unlike addItem)
            model.StringItemList = tuple(tabs)

            # Select first tab if nothing is selected
            if selector.getSelectedItemPos() < 0:
                selector.selectItemPos(0, True)

            # Apply visibility for the current tab
            idx = max(selector.getSelectedItemPos(), 0)
            _apply_tab_visibility(xWindow, tab_data, idx)

            # Attach listener only once (use Tag as flag)
            if getattr(model, "Tag", "") != "tabs_init":
                selector.addItemListener(_TabListener(tab_data, xWindow))
                model.Tag = "tabs_init"

            log.info("Tabs configured: %s (active=%d)", tabs, idx)
        except Exception:
            log.exception("_setup_tabs failed")

    def _setup_scroll(self, xWindow):
        """Add a scrollbar if the page content exceeds _PAGE_HEIGHT."""
        content_height = self._detect_content_height(xWindow)
        if content_height is None or content_height <= _PAGE_HEIGHT:
            return

        try:
            peer = xWindow.getPeer()
            if peer is None:
                return

            scroll_id = "__scrollbar__"
            original_positions = []
            controls = xWindow.getControls()
            for ctrl in controls:
                model = ctrl.getModel()
                name = getattr(model, "Name", "")
                if name == scroll_id:
                    continue
                original_positions.append((model, model.PositionY))

            dialog_model = xWindow.getModel()
            if dialog_model.hasByName(scroll_id):
                dialog_model.removeByName(scroll_id)

            # Create scrollbar with model positions (will be repositioned
            # in pixels below to match actual container size)
            sb_model = dialog_model.createInstance(
                "com.sun.star.awt.UnoControlScrollBarModel")
            sb_model.Name = scroll_id
            sb_model.Orientation = 1  # vertical

            # Scrollbar sits at the right edge of the content area.
            # Space is always reserved: controls use _CONTENT_WIDTH, scrollbar at _CONTENT_WIDTH.
            sb_model.PositionX = _CONTENT_WIDTH
            sb_model.PositionY = 0
            sb_model.Width = _SCROLLBAR_WIDTH
            sb_model.Height = _PAGE_HEIGHT
            sb_model.ScrollValueMin = 0
            sb_model.ScrollValueMax = content_height - _VISIBLE_HEIGHT + _OVERFLOW_TWEAK
            sb_model.VisibleSize = _VISIBLE_HEIGHT
            sb_model.LineIncrement = 10
            sb_model.BlockIncrement = _VISIBLE_HEIGHT // 3

            dialog_model.insertByName(scroll_id, sb_model)

            sb_ctrl = xWindow.getControl(scroll_id)
            if sb_ctrl:
                listener = _ScrollListener(original_positions)
                self._scroll_listeners[id(xWindow)] = listener
                sb_ctrl.addAdjustmentListener(listener)

            log.debug("Scrollbar added: content=%d page=%d",
                      content_height, _PAGE_HEIGHT)
        except Exception:
            log.exception("_setup_scroll failed")

    def _detect_content_height(self, xWindow):
        """Read the hidden __content_height__ control. Returns int or None."""
        try:
            ctrl = xWindow.getControl("__content_height__")
            if ctrl:
                model = ctrl.getModel()
                raw = getattr(model, "Label", "") or getattr(model, "Text", "")
                if raw:
                    return int(raw)
        except Exception:
            pass
        return None

    def _detect_tabs(self, xWindow):
        """Read the hidden __tabs__ control. Returns parsed dict or None."""
        try:
            ctrl = xWindow.getControl("__tabs__")
            if ctrl:
                model = ctrl.getModel()
                raw = getattr(model, "Label", "") or getattr(model, "Text", "")
                if raw:
                    import json as _json
                    return _json.loads(raw)
        except Exception:
            log.debug("_detect_tabs: no tab data")
        return None

    # ── Helpers ──────────────────────────────────────────────────────

    def _read_control(self, ctrl, widget, field_type, schema):
        """Read the current value from a control."""
        if widget == "checkbox":
            return ctrl.getModel().State == 1
        elif widget in ("text", "password", "textarea", "file", "folder",
                         "combo", "combo_text"):
            return ctrl.getModel().Text or ""
        elif widget in ("number", "slider"):
            raw = ctrl.getModel().Value
            return int(raw) if field_type == "int" else float(raw)
        elif widget == "select":
            return self._read_select(ctrl, schema)
        return ctrl.getModel().Text or ""

    def _detect_module(self, xWindow):
        """Read the hidden __module__ control to find which module this page is for.

        dlg:text controls expose their dlg:value via the Label property on the model.
        """
        try:
            ctrl = xWindow.getControl("__module__")
            if ctrl:
                model = ctrl.getModel()
                # dlg:text (XFixedText) stores dlg:value in Label, not Text
                return getattr(model, "Label", "") or getattr(model, "Text", "")
        except Exception:
            log.exception("_detect_module failed")
        return None

    def _detect_list_detail(self, xWindow):
        """Read the hidden __list_detail__ control. Returns field name or None."""
        try:
            ctrl = xWindow.getControl("__list_detail__")
            if ctrl:
                model = ctrl.getModel()
                return getattr(model, "Label", "") or getattr(model, "Text", "")
        except Exception:
            pass
        return None

    def _detect_inline_modules(self, xWindow):
        """Read the hidden __inline_modules__ control. Returns list of names or None."""
        try:
            ctrl = xWindow.getControl("__inline_modules__")
            if ctrl:
                model = ctrl.getModel()
                raw = getattr(model, "Label", "") or getattr(model, "Text", "")
                if raw:
                    return [n.strip() for n in raw.split(",") if n.strip()]
        except Exception:
            pass
        return None

    def _get_control(self, xWindow, field_name):
        """Get a control by field name, searching sub-containers (multipage)."""
        try:
            ctrl = xWindow.getControl(field_name)
            if ctrl:
                return ctrl
        except Exception:
            pass
        # Search inside sub-containers (multipage pages)
        try:
            for ctrl in xWindow.getControls():
                try:
                    container = ctrl.queryInterface(
                        uno.getTypeByName(
                            "com.sun.star.awt.XControlContainer"))
                    if container:
                        found = container.getControl(field_name)
                        if found:
                            return found
                        # Search one level deeper (page inside multipage)
                        for sub in container.getControls():
                            try:
                                sub_c = sub.queryInterface(
                                    uno.getTypeByName(
                                        "com.sun.star.awt.XControlContainer"))
                                if sub_c:
                                    found = sub_c.getControl(field_name)
                                    if found:
                                        return found
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _get_config_service(self):
        """Get the ConfigService from the framework."""
        try:
            from plugin.main import get_services
            services = get_services()
            return services.config if services else None
        except Exception:
            log.exception("Could not get ConfigService")
            return None

    def _get_manifest(self):
        """Get the manifest modules list."""
        try:
            from plugin._manifest import MODULES
            return MODULES
        except ImportError:
            return []

    def _get_module_config(self, manifest, module_name):
        """Find the config dict for a given module name."""
        for m in manifest:
            if m.get("name") == module_name:
                return m.get("config", {})
        return {}

    def _call_default_provider(self, provider_path):
        """Call a default_provider function to get a fallback value."""
        try:
            module_path, func_name = provider_path.rsplit(":", 1)
            import importlib
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            from plugin.main import get_services
            return func(get_services())
        except Exception:
            log.exception("Failed to call default_provider: %s", provider_path)
            return None

    def _resolve_options(self, schema):
        """If schema has an options_provider, call it to get dynamic options."""
        provider_path = schema.get("options_provider")
        if not provider_path:
            return schema
        try:
            options = self._call_options_provider(provider_path)
            return dict(schema, options=options)
        except Exception:
            log.exception("Failed to resolve options_provider: %s", provider_path)
            return schema

    # ── Check widget ───────────────────────────────────────────────

    def _update_script_helper(self, xWindow, ctrl_id, module_name, field_name,
                              schema):
        """Append last-launch timestamp to a script button's helper text."""
        try:
            hlp_ctrl = self._get_control(xWindow, "hlp_%s" % ctrl_id)
            if not hlp_ctrl:
                return
            # Decode script identity from field_name: __script_install_deps__
            script_key = field_name[len("__script_"):-len("__")]
            script_name = script_key.replace("_", "-")

            from plugin.framework.deps import get_last_launch, _get_script_def
            script_def = _get_script_def(module_name, script_name)
            last = get_last_launch(module_name, script_name)
            base = schema.get("helper") or schema.get("description") or ""

            # Check if a version bump requires re-run
            needs_update = False
            if script_def and script_def.get("once"):
                from plugin.framework.deps import _is_done
                version = str(script_def.get("version", "1"))
                if last and not _is_done(module_name, script_name, version):
                    needs_update = True

            if needs_update:
                suffix = " [update available — click to re-run]"
            elif last:
                suffix = " [last run: %s]" % last
            else:
                suffix = " [never launched]"
            hlp_ctrl.getModel().Label = base + suffix
        except Exception:
            log.debug("Failed to update script helper", exc_info=True)

    _CHECK_ICONS = {"ok": "[OK]", "ko": "[FAIL]", "unknown": "[?]"}

    def _run_check(self, ctrl, schema):
        """Call the check_provider and display the result."""
        provider_path = schema.get("check_provider")
        if not provider_path:
            ctrl.getModel().Label = "\u2753 No check_provider defined"
            return
        try:
            module_path, func_name = provider_path.rsplit(":", 1)
            import importlib
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            from plugin.main import get_services
            result = func(get_services())
            # result: {"status": "ok"|"ko"|"unknown", "message": "..."}
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                message = result.get("message", "")
            else:
                status = "ok" if result else "ko"
                message = str(result) if result else ""
            icon = self._CHECK_ICONS.get(status, self._CHECK_ICONS["unknown"])
            ctrl.getModel().Label = "%s %s" % (icon, message)
        except Exception:
            log.exception("Check provider failed: %s", provider_path)
            ctrl.getModel().Label = "%s Error running check" % self._CHECK_ICONS["ko"]

    def _call_options_provider(self, provider_path):
        """Import a module and call a function to get options.

        provider_path format: "plugin.modules.core.services.ai:get_text_instance_options"
        The function receives the ServiceRegistry as its argument.
        """
        module_path, func_name = provider_path.rsplit(":", 1)
        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        from plugin.main import get_services
        services = get_services()
        return func(services)

    def _populate_combo(self, ctrl, schema, current_value):
        """Populate a combobox dropdown with options and set text value.

        Note: dlg:combobox dropdown doesn't work in LO Options pages.
        Kept for potential use in standalone dialogs.
        """
        options = schema.get("options", [])
        if options:
            labels = tuple(o.get("label", o.get("value", "")) for o in options)
            ctrl.getModel().StringItemList = labels
        ctrl.setText(str(current_value) if current_value else "")

    def _setup_combo_text(self, xWindow, field_name, schema, current_value):
        """Wire a combo_text widget: select (sel_<field>) + text (<field>).

        Selecting in the dropdown fills the text field with the value.
        The text field holds the real config value.
        """
        sel_ctrl = self._get_control(xWindow, "sel_%s" % field_name)
        txt_ctrl = self._get_control(xWindow, field_name)
        if not sel_ctrl or not txt_ctrl:
            return

        options = list(schema.get("options", []))
        values = [o.get("value", "") for o in options]
        labels = [o.get("label", o.get("value", "")) for o in options]

        # Add "(custom)" entry at the end
        labels.append("(custom)")
        values.append(None)

        model = sel_ctrl.getModel()
        model.StringItemList = tuple(labels)

        # Set text field
        val = str(current_value) if current_value else ""
        txt_ctrl.getModel().Text = val

        # Select matching entry or "(custom)"
        if val in values:
            model.SelectedItems = (values.index(val),)
        else:
            model.SelectedItems = (len(labels) - 1,)  # (custom)

        # Listener: select → update text
        sel_ctrl.addItemListener(
            _ComboTextListener(sel_ctrl, txt_ctrl, values))

    def _populate_select(self, ctrl, schema, current_value):
        """Populate a menulist/listbox with options and select current value.

        If current_value is not in the options list, it is appended so that
        custom/unknown values are preserved in the UI.
        """
        options = list(schema.get("options", []))
        if not options:
            return

        values = [o.get("value", "") for o in options]

        # Inject current value if not already in options (preserves custom values)
        if current_value and current_value not in values:
            options.append({"value": current_value, "label": current_value})
            values.append(current_value)

        labels = tuple(o.get("label", o.get("value", "")) for o in options)

        model = ctrl.getModel()
        model.StringItemList = labels

        if current_value in values:
            ctrl.selectItemPos(values.index(current_value), True)
        elif options:
            ctrl.selectItemPos(0, True)

    def _read_select(self, ctrl, schema):
        """Read the selected value from a menulist/listbox."""
        options = schema.get("options", [])
        sel = ctrl.getSelectedItemPos()
        if 0 <= sel < len(options):
            return options[sel].get("value", "")
        return schema.get("default", "")


# ── UNO component registration ──────────────────────────────────────

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    OptionsHandler,
    OptionsHandler.IMPLE_NAME,
    OptionsHandler.SERVICE_NAMES,
)
