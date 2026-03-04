# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Nelson MCP entry point — bootstraps the module framework.

Responsibilities:
1. Resolve module load order from dependency graph (_manifest.py)
2. Initialize core services first, then all other modules
3. Auto-discover tools from each module's tools/ subpackage
4. Register UNO components (MainJob, DispatchHandler)

All runtime code lives under plugin/. This file is the single entry
point registered in META-INF/manifest.xml.
"""

import logging
import os
import sys
import threading

# ── File logger (debug even when LO console is hidden) ──────────────────────
# Set up on the 'nelson' logger (not root) so it works regardless of
# root logger state configured by other extensions (e.g. mcp-libre).
# Cannot import from plugin.framework here — sys.path isn't set up yet.

_log_path = os.path.join(os.path.expanduser("~"), "nelson.log")
_logger = logging.getLogger("nelson")
_logger.handlers.clear()
_logger.propagate = False
_handler = logging.FileHandler(_log_path, mode="w", encoding="utf-8")
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s — %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.DEBUG)

log = logging.getLogger("nelson.main")

_version = "?"
try:
    _vf = os.path.join(os.path.dirname(__file__), "version.py")
    with open(_vf) as _f:
        for _line in _f:
            if _line.startswith("EXTENSION_VERSION"):
                _version = _line.split("=", 1)[1].strip().strip("\"'")
                break
except Exception:
    pass
log.info("=== Nelson MCP %s — main.py loaded ===", _version)

# Extension identifier (matches description.xml)
EXTENSION_ID = "org.extension.nelson"

# ── Singleton registries ──────────────────────────────────────────────

_services = None
_tools = None
_modules = []
_init_lock = threading.Lock()
_initialized = False


def _ensure_extension_on_path(ctx):
    """Add the extension's install directory to sys.path."""
    try:
        import uno
        pip = ctx.getValueByName(
            "/singletons/com.sun.star.deployment.PackageInformationProvider")
        ext_url = pip.getPackageLocation(EXTENSION_ID)
        if ext_url.startswith("file://"):
            ext_path = str(uno.fileUrlToSystemPath(ext_url))
        else:
            ext_path = ext_url
        if ext_path and ext_path not in sys.path:
            sys.path.insert(0, ext_path)
    except Exception:
        pass

    # Also ensure plugin/ parent is on path so "plugin.xxx" imports work
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(plugin_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)


def _load_manifest():
    """Load the generated module manifest.

    Returns a list of module descriptors sorted by dependency order.
    Each descriptor is a dict with keys: name, module_class, requires, config, ...
    """
    try:
        from plugin._manifest import MODULES
        return MODULES
    except ImportError:
        log.warning("_manifest.py not found — using fallback discovery")
        return _fallback_discover_modules()


def _fallback_discover_modules():
    """Discover modules by scanning plugin/modules/ for module.yaml files.

    Used when _manifest.py has not been generated (dev mode).
    Requires PyYAML.
    """
    modules_dir = os.path.join(os.path.dirname(__file__), "modules")
    if not os.path.isdir(modules_dir):
        return []

    result = []
    for entry in sorted(os.listdir(modules_dir)):
        yaml_path = os.path.join(modules_dir, entry, "module.yaml")
        if not os.path.isfile(yaml_path):
            continue
        try:
            import yaml
            with open(yaml_path) as f:
                manifest = yaml.safe_load(f)
            manifest.setdefault("name", entry)
            result.append(manifest)
        except Exception:
            log.exception("Failed to load %s", yaml_path)

    return _topo_sort(result)


def _topo_sort(modules):
    """Topological sort of modules by 'requires' dependencies.

    Ensures core is always first. Returns sorted list.
    """
    by_name = {m["name"]: m for m in modules}
    # Services provided by each module
    provides = {}
    for m in modules:
        for svc in m.get("provides_services", []):
            provides[svc] = m["name"]

    visited = set()
    order = []

    def visit(name):
        if name in visited:
            return
        visited.add(name)
        m = by_name.get(name)
        if m is None:
            return
        for req in m.get("requires", []):
            provider = provides.get(req, req)
            if provider in by_name:
                visit(provider)
        order.append(m)

    # core first
    if "core" in by_name:
        visit("core")
    for name in by_name:
        visit(name)

    return order


def _import_module_class(module_manifest):
    """Import and return the ModuleBase subclass for a module."""
    name = module_manifest["name"]
    # Directory convention: dots in name map to underscores
    package = "plugin.modules.%s" % name.replace(".", "_")
    try:
        import importlib
        mod = importlib.import_module(package)
        # Find the ModuleBase subclass
        from plugin.framework.module_base import ModuleBase
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if (isinstance(obj, type) and issubclass(obj, ModuleBase)
                    and obj is not ModuleBase):
                return obj
    except Exception:
        log.exception("Failed to import module: %s", name)
    return None


def get_services():
    """Return the global ServiceRegistry (lazy-init)."""
    global _services
    if _services is None:
        bootstrap()
    return _services


def get_tools():
    """Return the global ToolRegistry (lazy-init)."""
    global _tools
    if _tools is None:
        bootstrap()
    return _tools


def bootstrap(ctx=None):
    """Initialize the entire framework.

    Idempotent — safe to call multiple times.
    """
    global _services, _tools, _modules, _initialized

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        if ctx:
            _ensure_extension_on_path(ctx)
            # Store fallback ctx for environments where uno module
            # is not importable (shouldn't happen in LO, but safe)
            from plugin.framework.uno_context import set_fallback_ctx
            set_fallback_ctx(ctx)

        from plugin.framework.service_registry import ServiceRegistry
        from plugin.framework.tool_registry import ToolRegistry

        _services = ServiceRegistry()
        _tools = ToolRegistry(_services)

        # Register the tool registry itself as a service
        _services.register_instance("tools", _tools)

        # Load and sort modules
        manifests = _load_manifest()

        manifest_dict = {m["name"]: m for m in manifests}

        # ── Phase 1: initialize modules ──────────────────────────────
        log.info("── Phase 1: initialize ─────────────────────────────")

        for manifest in manifests:
            name = manifest["name"]
            if name == "main":
                continue  # framework-level config, not a loadable module
            cls = _import_module_class(manifest)
            if cls is None:
                log.warning("Skipping module with no class: %s", name)
                continue

            instance = cls()
            instance.name = name

            try:
                instance.initialize(_services)
                log.info("Module initialized: %s", name)
            except Exception:
                log.exception("Failed to initialize module: %s", name)
                continue

            _modules.append(instance)

            # After core registers config service, load all config defaults
            # so subsequent modules can read their config during init
            if name == "core":
                config_svc = _services.get("config")
                if config_svc:
                    config_svc.set_manifest(manifest_dict)
                    log.info("Config defaults loaded for %d modules",
                             len(manifest_dict))
                    # Apply configured log level
                    from plugin.framework.logging import set_log_level
                    level = config_svc.proxy_for("core").get(
                        "log_level", "DEBUG")
                    set_log_level(level)
                    log.info("Log level set to %s", level)

            # Auto-discover tools from this module's tools/ subpackage
            # Directory convention: dots in name map to underscores
            # e.g. "tunnel.bore" -> modules/tunnel_bore/tools
            dir_name = name.replace(".", "_")
            tools_dir = os.path.join(
                os.path.dirname(__file__), "modules", dir_name, "tools")
            if os.path.isdir(tools_dir):
                tools_pkg = "plugin.modules.%s.tools" % dir_name
                _tools.discover(tools_dir, tools_pkg)

        # Wire event bus into config service
        if config_svc:
            events_svc = _services.get("events")
            if events_svc:
                config_svc.set_events(events_svc)

        # Initialize services that need a UNO context
        if ctx:
            _services.initialize_all(ctx)

        log.info("── Phase 1 complete: %d modules initialized ────────",
                 len(_modules))

        # Emit modules:initialized event
        events_svc = _services.get("events")
        if events_svc:
            events_svc.emit("modules:initialized",
                            modules=[m.name for m in _modules])

        # ── Phase 2a: start modules on VCL main thread ────────────────
        log.info("── Phase 2a: start (main thread) ────────────────────")

        from plugin.framework.main_thread import execute_on_main_thread

        for mod in _modules:
            try:
                execute_on_main_thread(mod.start, _services)
                log.info("Module started: %s", mod.name)
            except Exception:
                log.exception("Failed to start module: %s", mod.name)

        log.info("── Phase 2a complete: %d modules started ────────────",
                 len(_modules))

        # ── Phase 2b: start_background on Job thread ─────────────────
        log.info("── Phase 2b: start_background (job thread) ──────────")

        for mod in _modules:
            try:
                mod.start_background(_services)
                log.info("Module background started: %s", mod.name)
            except Exception:
                log.exception("Failed to background-start module: %s",
                              mod.name)

        log.info("── Phase 2b complete: %d modules background started ─",
                 len(_modules))

        # Emit modules:started event
        if events_svc:
            events_svc.emit("modules:started",
                            modules=[m.name for m in _modules])

        # Subscribe to menu:update for dynamic menu text + icons
        if events_svc:
            events_svc.subscribe("menu:update",
                                 lambda **kw: notify_menu_update())

        # Pre-load icons into ImageManager so first menu display has them
        threading.Thread(target=_update_menu_icons, daemon=True).start()


        _initialized = True
        log.info("Framework bootstrap complete: %d modules, %d tools",
                 len(_modules), len(_tools))


def shutdown():
    """Shut down all modules and services."""
    global _initialized

    for mod in reversed(_modules):
        try:
            mod.shutdown()
        except Exception:
            log.exception("Error shutting down module: %s", mod.name)

    if _services:
        _services.shutdown_all()

    _initialized = False


# ── UNO component registration ────────────────────────────────────────

# ── Dynamic menu text infrastructure ─────────────────────────────────

_DISPATCH_PROTOCOL = "org.extension.nelson:"

_status_listeners = []  # [(listener, url)]
_status_lock = threading.Lock()


def _dispatch_command(command):
    """Dispatch a module.action command. Used by both MainJob and DispatchHandler."""
    dot = command.find(".")
    if dot <= 0:
        log.warning("Unhandled command: %s", command)
        return

    mod_name = command[:dot]
    action = command[dot + 1:]

    # Framework actions
    if mod_name == "main":
        if action == "about":
            from plugin.framework.uno_context import get_ctx
            from plugin.framework.dialogs import about_dialog
            about_dialog(get_ctx())
        else:
            log.warning("Unhandled framework action: %s", action)
        return

    # Module actions
    for mod in _modules:
        if mod.name == mod_name:
            mod.on_action(action)
            return

    log.warning("Module not found for command: %s", command)


def get_menu_text(command):
    """Get dynamic menu text for a command, or None for default."""
    dot = command.find(".")
    if dot <= 0:
        return None
    mod_name = command[:dot]
    action = command[dot + 1:]
    for mod in _modules:
        if mod.name == mod_name:
            return mod.get_menu_text(action)
    return None


def notify_menu_update():
    """Push current menu text and icons to all registered status listeners.

    Called by modules when state changes (e.g. server start/stop).
    """
    with _status_lock:
        alive = []
        for listener, url in _status_listeners:
            command = url.Path
            text = get_menu_text(command)
            try:
                _fire_status_event(listener, url, text)
                alive.append((listener, url))
            except Exception:
                log.debug("Dropping dead status listener for %s", command)
        _status_listeners[:] = alive
    # Update icons in a background thread (avoids blocking UI)
    threading.Thread(target=_update_menu_icons, daemon=True).start()


def _fire_status_event(listener, url, text):
    """Send a FeatureStateEvent to one listener."""
    import uno
    ev = uno.createUnoStruct("com.sun.star.frame.FeatureStateEvent")
    ev.FeatureURL = url
    ev.IsEnabled = True
    ev.Requery = False
    if text is not None:
        ev.State = text
    listener.statusChanged(ev)


# ── Dynamic menu icons via XImageManager ──────────────────────────────

# LO document modules that have their own ImageManager
_IMAGE_MANAGER_MODULES = (
    "com.sun.star.text.TextDocument",
    "com.sun.star.sheet.SpreadsheetDocument",
    "com.sun.star.presentation.PresentationDocument",
    "com.sun.star.drawing.DrawingDocument",
)


def _get_menu_icon(command):
    """Get dynamic icon prefix for a command, or None."""
    dot = command.find(".")
    if dot <= 0:
        return None
    mod_name = command[:dot]
    action = command[dot + 1:]
    for mod in _modules:
        if mod.name == mod_name:
            return mod.get_menu_icon(action)
    return None


def _collect_icon_commands():
    """Collect all command URLs that declare icons in their manifest.

    Returns {command_url: (module_name, icon_prefix)} for the current state.
    """
    try:
        from plugin._manifest import MODULES
    except ImportError:
        return {}

    result = {}
    for m in MODULES:
        mod_name = m["name"]
        action_icons = m.get("action_icons", {})
        for action_name, default_icon in action_icons.items():
            cmd_url = "%s%s.%s" % (_DISPATCH_PROTOCOL, mod_name, action_name)
            # Ask the module for dynamic icon (may override the default)
            dynamic = _get_menu_icon("%s.%s" % (mod_name, action_name))
            result[cmd_url] = (mod_name, dynamic or default_icon)
    return result


def _load_icon_graphic(module_name, icon_filename):
    """Load a PNG icon from a module's icons/ directory as XGraphic."""
    try:
        import uno
        from com.sun.star.beans import PropertyValue
        ctx = uno.getComponentContext()
        smgr = ctx.ServiceManager
        pip = ctx.getValueByName(
            "/singletons/com.sun.star.deployment.PackageInformationProvider")
        ext_url = pip.getPackageLocation(EXTENSION_ID)
        if not ext_url:
            return None
        gp = smgr.createInstanceWithContext(
            "com.sun.star.graphic.GraphicProvider", ctx)
        pv = PropertyValue()
        pv.Name = "URL"
        pv.Value = "%s/plugin/modules/%s/icons/%s" % (
            ext_url, module_name, icon_filename)
        return gp.queryGraphic((pv,))
    except Exception as e:
        log.debug("Failed to load icon %s/%s: %s",
                  module_name, icon_filename, e)
        return None


def _update_menu_icons():
    """Push current-state icons into every module's ImageManager."""
    try:
        import uno
        icon_cmds = _collect_icon_commands()
        if not icon_cmds:
            return

        # Group by (module, prefix) to avoid loading the same graphic twice
        key_cmds = {}  # (mod_name, prefix) -> [cmd_urls]
        for cmd_url, (mod_name, prefix) in icon_cmds.items():
            key_cmds.setdefault((mod_name, prefix), []).append(cmd_url)

        # Load graphics
        key_graphics = {}
        for key in key_cmds:
            mod_name, prefix = key
            filename = "%s_16.png" % prefix
            graphic = _load_icon_graphic(mod_name, filename)
            if graphic:
                key_graphics[key] = graphic
            else:
                log.warning("Icon graphic is None for %s/%s", mod_name,
                            filename)

        if not key_graphics:
            return

        ctx = uno.getComponentContext()
        smgr = ctx.ServiceManager

        ok_count = 0

        supplier = smgr.createInstanceWithContext(
            "com.sun.star.ui.ModuleUIConfigurationManagerSupplier", ctx)
        for mod_id in _IMAGE_MANAGER_MODULES:
            try:
                cfg_mgr = supplier.getUIConfigurationManager(mod_id)
                img_mgr = cfg_mgr.getImageManager()
                for key, cmds in key_cmds.items():
                    graphic = key_graphics.get(key)
                    if not graphic:
                        continue
                    for cmd in cmds:
                        try:
                            if img_mgr.hasImage(0, cmd):
                                img_mgr.replaceImages(0, (cmd,), (graphic,))
                            else:
                                img_mgr.insertImages(0, (cmd,), (graphic,))
                            ok_count += 1
                        except Exception as e:
                            log.debug("ImageManager %s cmd %s: %s",
                                      mod_id, cmd, e)
            except Exception as e:
                log.debug("ImageManager skip %s: %s", mod_id, e)

        log.info("Menu icons updated (%d insertions)", ok_count)
    except Exception as e:
        log.warning("Dynamic icon update failed: %s", e)


# ── Conditional menus (visible_if) ─────────────────────────────────────

# ── UNO component registration ────────────────────────────────────────

try:
    import uno
    import unohelper
    from com.sun.star.task import XJobExecutor, XJob
    from com.sun.star.frame import XDispatch, XDispatchProvider
    from com.sun.star.lang import XInitialization, XServiceInfo

    class MainJob(unohelper.Base, XJobExecutor, XJob):
        """UNO Job component — entry point for OnStartApp bootstrap."""

        def __init__(self, ctx):
            log.info("MainJob.__init__ called")
            self.ctx = ctx

        # ── XJob.execute (OnStartApp event) ──────────────────────────

        def execute(self, args):
            """Called by the Jobs framework on OnStartApp."""
            log.info("MainJob.execute (OnStartApp) called")
            try:
                bootstrap(self.ctx)
            except Exception:
                log.exception("MainJob.execute bootstrap FAILED")
            return ()

        # ── XJobExecutor.trigger (legacy fallback) ───────────────────

        def trigger(self, args):
            """Fallback dispatch for service: protocol URLs."""
            log.info("MainJob.trigger called with: %r", args)
            try:
                bootstrap(self.ctx)
                command = args if isinstance(args, str) else ""
                _dispatch_command(command)
            except Exception:
                log.exception("MainJob.trigger FAILED")

    class DispatchHandler(unohelper.Base, XDispatch, XDispatchProvider,
                          XInitialization, XServiceInfo):
        """Protocol handler for org.extension.nelson: URLs.

        Handles menu dispatch and supports dynamic menu text via
        FeatureStateEvent / addStatusListener.
        """

        IMPL_NAME = "org.extension.nelson.DispatchHandler"
        SERVICE_NAMES = ("com.sun.star.frame.ProtocolHandler",)

        def __init__(self, ctx):
            self.ctx = ctx

        # ── XInitialization ──────────────────────────────────────────

        def initialize(self, args):
            pass

        # ── XServiceInfo ─────────────────────────────────────────────

        def getImplementationName(self):
            return self.IMPL_NAME

        def supportsService(self, name):
            return name in self.SERVICE_NAMES

        def getSupportedServiceNames(self):
            return self.SERVICE_NAMES

        # ── XDispatchProvider ────────────────────────────────────────

        def queryDispatch(self, url, target, flags):
            if url.Protocol == _DISPATCH_PROTOCOL:
                return self
            return None

        def queryDispatches(self, requests):
            return [self.queryDispatch(r.FeatureURL, r.FrameName,
                                       r.SearchFlags) for r in requests]

        # ── XDispatch ────────────────────────────────────────────────

        def dispatch(self, url, args):
            command = url.Path
            log.info("DispatchHandler.dispatch: %s", command)
            try:
                bootstrap(self.ctx)
                _dispatch_command(command)
                # After action, push updated menu text
                threading.Thread(target=notify_menu_update,
                                 daemon=True).start()
            except Exception:
                log.exception("DispatchHandler.dispatch FAILED")

        def addStatusListener(self, listener, url):
            with _status_lock:
                _status_listeners.append((listener, url))
            # Send current state immediately
            command = url.Path
            text = get_menu_text(command)
            if text is not None:
                try:
                    _fire_status_event(listener, url, text)
                except Exception:
                    log.debug("Initial status event failed for %s", command)

        def removeStatusListener(self, listener, url):
            with _status_lock:
                _status_listeners[:] = [
                    (l, u) for l, u in _status_listeners
                    if not (l is listener and u.Complete == url.Complete)
                ]

    # Register with LibreOffice
    g_ImplementationHelper = unohelper.ImplementationHelper()
    g_ImplementationHelper.addImplementation(
        MainJob,
        "org.extension.nelson.Main",
        ("com.sun.star.task.Job",),
    )
    g_ImplementationHelper.addImplementation(
        DispatchHandler,
        DispatchHandler.IMPL_NAME,
        DispatchHandler.SERVICE_NAMES,
    )
    log.info("g_ImplementationHelper registered: Main + DispatchHandler")

    # Module-level fallback auto-bootstrap (like mcp-libre)
    def _module_autostart():
        import time
        time.sleep(3)
        if not _initialized:
            log.info("Module-level auto-bootstrap (fallback)")
            try:
                ctx = uno.getComponentContext()
                bootstrap(ctx)
            except Exception:
                log.exception("Module-level auto-bootstrap FAILED")

    threading.Thread(
        target=_module_autostart, daemon=True,
        name="nelson-autoboot").start()
    log.info("Auto-bootstrap thread started (will fire in 3s)")

except ImportError as e:
    log.warning("UNO not available (not inside LO): %s", e)
except Exception as e:
    log.exception("UNO registration FAILED")
