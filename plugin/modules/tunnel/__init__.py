# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tunnel module — manages tunnel providers for exposing HTTP externally.

The parent module owns the subprocess lifecycle; each child provider supplies
its binary, command-line, and URL-parsing logic via the TunnelProvider protocol.
"""

import logging
import re
import subprocess
import threading

from plugin.framework.module_base import ModuleBase

log = logging.getLogger("nelson.tunnel")

# Windows: hide subprocess console window
_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TunnelError(Exception):
    """General tunnel error."""


class TunnelAuthError(TunnelError):
    """Provider requires authentication credentials."""


def get_provider_options(services):
    """Return available tunnel providers as option dicts.

    Called dynamically by the options handler to populate the provider
    select widget. Discovers registered providers from the tunnel_manager.
    """
    try:
        if services and hasattr(services, "tunnel_manager"):
            mgr = services.tunnel_manager
            return [
                {"value": name, "label": name.title()}
                for name in sorted(mgr.providers)
            ]
    except Exception:
        log.debug("get_provider_options: services not ready yet")
    return []


class TunnelManager:
    """Manages tunnel subprocess lifecycle using pluggable providers."""

    last_error = None

    def __init__(self, config_svc, events):
        self.providers = {}
        self._process = None
        self._public_url = None
        self._active_provider = None
        self._lock = threading.Lock()
        self._config_svc = config_svc
        self._events = events

    def register_provider(self, name, provider):
        self.providers[name] = provider
        log.info("Tunnel provider registered: %s", name)

    def get_provider(self, name):
        return self.providers.get(name)

    @property
    def public_url(self):
        return self._public_url

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    # ── Binary check ──────────────────────────────────────────────────

    def _check_binary(self, provider):
        """Verify the provider binary is installed. Returns True if OK."""
        if not provider.version_args:
            return True
        try:
            result = subprocess.run(
                provider.version_args,
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATION_FLAGS,
            )
            log.info("%s version: %s", provider.name,
                     result.stdout.strip() or result.stderr.strip())
            return True
        except FileNotFoundError:
            log.error(
                "%s binary '%s' not found. Install from: %s",
                provider.name, provider.binary_name, provider.install_url,
            )
            return False
        except Exception:
            log.exception("Error checking %s binary", provider.name)
            return False

    # ── Subprocess lifecycle ──────────────────────────────────────────

    def _run_and_parse(self, cmd, url_regex, provider):
        """Run the tunnel command, parse stdout for the public URL.

        Called in a daemon thread. Sets self._public_url when found.
        """
        log.info("Running: %s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=_CREATION_FLAGS,
            )
        except FileNotFoundError:
            log.error("Binary not found: %s", cmd[0])
            return
        except Exception:
            log.exception("Failed to start tunnel process")
            return

        self._process = proc
        pattern = re.compile(url_regex) if url_regex else None

        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if not line:
                    continue
                log.debug("[%s] %s", provider.name, line)

                if self._public_url:
                    continue

                # Try provider custom parsing first
                try:
                    custom_url = provider.parse_line(line)
                except TunnelAuthError:
                    log.error("Authentication required for %s", provider.name)
                    self._stop_process()
                    return
                except Exception:
                    custom_url = None

                if custom_url:
                    self._public_url = custom_url
                    log.info("Tunnel URL (custom): %s", self._public_url)
                    self._emit_started(provider)
                    continue

                # Fallback: regex matching
                if pattern:
                    m = pattern.search(line)
                    if m:
                        self._public_url = m.group(1)
                        log.info("Tunnel URL (regex): %s", self._public_url)
                        self._emit_started(provider)

        except Exception:
            log.exception("Error reading tunnel output")
        finally:
            ret = proc.wait()
            log.info("Tunnel process exited with code %s", ret)
            self._process = None
            if self._public_url:
                self._public_url = None
                self._emit_stopped("process_exited")

    def _emit_started(self, provider):
        if self._events:
            self._events.emit(
                "tunnel:started",
                public_url=self._public_url,
                provider=provider.name,
            )

    def _emit_stopped(self, reason):
        if self._events:
            self._events.emit("tunnel:stopped", reason=reason)

    def _stop_process(self):
        """Terminate the running tunnel process."""
        proc = self._process
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        except Exception:
            log.exception("Error stopping tunnel process")
        finally:
            self._process = None

    # ── Public API ────────────────────────────────────────────────────

    def start_tunnel(self):
        """Start the configured tunnel provider in a background thread."""
        with self._lock:
            if self.is_running:
                log.info("Tunnel already running at %s", self._public_url)
                return

            cfg = self._config_svc.proxy_for("tunnel")
            provider_name = cfg.get("provider")
            if not provider_name:
                log.info("Tunnel enabled but no provider selected")
                return

            provider = self.providers.get(provider_name)
            if provider is None:
                log.warning("Tunnel provider not found: %s", provider_name)
                return

            if not self._check_binary(provider):
                return

            # A tunnel publishes the server beyond this machine, and its
            # traffic arrives from localhost, so loopback cannot tell it
            # apart from a local client. Only a token protects it.
            http_cfg = self._config_svc.proxy_for("http")
            if not (http_cfg.get("auth_token") or "").strip():
                self.last_error = (
                    "Tunnel not started: set an access token first.\n\n"
                    "A tunnel makes this server reachable from outside your "
                    "machine. Without a token, anyone who learns the URL could "
                    "read and edit your open documents.\n\n"
                    "Set one in Options > Nelson MCP > HTTP > Access Token.")
                log.error("Tunnel not started: no HTTP access token is set")
                self._emit_stopped("no access token")
                return
            self.last_error = None

            # Get HTTP port and scheme from config
            port = http_cfg.get("port", 8766)
            scheme = "https" if http_cfg.get("use_ssl") else "http"

            # Provider-specific config
            provider_cfg = self._config_svc.proxy_for(
                "tunnel.%s" % provider_name)

            # Pre-start hook
            try:
                provider.pre_start(provider_cfg)
            except Exception:
                log.exception("Provider pre_start failed for %s", provider_name)
                return

            # Build command
            try:
                cmd, url_regex = provider.build_command(port, scheme,
                                                        provider_cfg)
            except Exception:
                log.exception("Failed to build tunnel command for %s",
                              provider_name)
                return

            self._active_provider = provider
            self._public_url = None

            # Check for pre-known URL (e.g. named cloudflare tunnel)
            pre_url = getattr(provider, "get_known_url", lambda c: None)(
                provider_cfg)
            if pre_url:
                self._public_url = pre_url
                log.info("Tunnel URL (known): %s", self._public_url)

            # Start in daemon thread
            t = threading.Thread(
                target=self._run_and_parse,
                args=(cmd, url_regex, provider),
                daemon=True,
                name="tunnel-%s" % provider_name,
            )
            t.start()

            if pre_url:
                self._emit_started(provider)

    def stop_tunnel(self):
        """Stop the current tunnel process."""
        with self._lock:
            provider = self._active_provider
            had_url = self._public_url is not None

            self._stop_process()
            self._public_url = None
            self._active_provider = None

            # Post-stop hook
            if provider:
                try:
                    provider_cfg = self._config_svc.proxy_for(
                        "tunnel.%s" % provider.name)
                    provider.post_stop(provider_cfg)
                except Exception:
                    log.exception("Provider post_stop failed for %s",
                                  provider.name)

            if had_url:
                self._emit_stopped("stopped")


class TunnelModule(ModuleBase):

    def initialize(self, services):
        self._services = services
        self._manager = TunnelManager(services.config, services.events)
        services.register_instance("tunnel_manager", self._manager)

        if hasattr(services, "events"):
            services.events.subscribe("config:changed",
                                      self._on_config_changed)

    def start_background(self, services):
        cfg = services.config.proxy_for(self.name)
        if cfg.get("auto_start"):
            self._manager.start_tunnel()

    def _on_config_changed(self, **data):
        key = data.get("key", "")
        if not key.startswith("tunnel."):
            return
        cfg = self._services.config.proxy_for(self.name)
        if cfg.get("auto_start"):
            # Restart tunnel to pick up new config
            self._manager.stop_tunnel()
            self._manager.start_tunnel()
        else:
            self._manager.stop_tunnel()

    def shutdown(self):
        self._manager.stop_tunnel()

    # ── Action dispatch ──────────────────────────────────────────────

    def on_action(self, action):
        if action == "toggle_tunnel":
            self._action_toggle()
        elif action == "tunnel_status":
            self._action_status()
        else:
            super().on_action(action)

    def get_menu_text(self, action):
        if action == "toggle_tunnel":
            return "Stop Tunnel" if self._manager.is_running else "Start Tunnel"
        if action == "tunnel_status":
            cfg = self._services.config.proxy_for(self.name)
            provider_name = cfg.get("provider")
            if provider_name:
                return "Tunnel Status (%s)" % provider_name.title()
            return "Tunnel Status (none)"
        return None

    def get_menu_icon(self, action):
        running = self._manager.is_running
        if action == "toggle_tunnel":
            return "stopped" if running else "running"
        if action == "tunnel_status":
            return "running" if running else "stopped"
        return None

    def _action_toggle(self):
        from plugin.framework.dialogs import msgbox
        from plugin.framework.uno_context import get_ctx

        ctx = get_ctx()
        if self._manager.is_running:
            self._manager.stop_tunnel()
            msgbox(ctx, "Nelson", "Tunnel stopped.")
        else:
            cfg = self._services.config.proxy_for(self.name)
            provider_name = cfg.get("provider")
            if not provider_name:
                msgbox(ctx, "Nelson",
                       "No tunnel provider configured.\n"
                       "Select one in Options > Nelson MCP > Tunnel.")
                return
            self._manager.start_tunnel()
            # Give it a moment to connect
            import time
            time.sleep(2)
            if self._manager.public_url:
                msgbox(ctx, "Nelson",
                       "Tunnel started.\nURL: %s" % self._manager.public_url)
            elif self._manager.is_running:
                msgbox(ctx, "Nelson",
                       "Tunnel starting...\n"
                       "Use Tunnel Status to check when ready.")
            elif self._manager.last_error:
                msgbox(ctx, "Nelson", self._manager.last_error)
            else:
                msgbox(ctx, "Nelson",
                       "Tunnel failed to start.\nCheck ~/nelson.log")

    def _action_status(self):
        from plugin.framework.uno_context import get_ctx

        ctx = get_ctx()
        running = self._manager.is_running
        url = self._manager.public_url or ""
        provider = self._manager._active_provider

        if not running:
            from plugin.framework.dialogs import msgbox
            cfg = self._services.config.proxy_for(self.name)
            provider_name = cfg.get("provider") or "(none)"
            msgbox(ctx, "Nelson",
                   "Tunnel is not running.\nProvider: %s" % provider_name)
            return

        provider_name = provider.name if provider else "unknown"
        base_url = url.rstrip("/") if url else ""
        mcp_url = "%s/mcp" % base_url if base_url else ""
        sse_url = "%s/sse" % base_url if base_url else ""

        # Show dialog with endpoint URLs and copy buttons
        try:
            smgr = ctx.ServiceManager

            dlg_model = smgr.createInstanceWithContext(
                "com.sun.star.awt.UnoControlDialogModel", ctx)
            dlg_model.Title = "Tunnel Status"
            dlg_model.Width = 300
            dlg_model.Height = 140

            # Status label
            lbl = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlFixedTextModel")
            lbl.Name = "Msg"
            lbl.PositionX = 10
            lbl.PositionY = 6
            lbl.Width = 280
            lbl.Height = 10
            lbl.Label = "Tunnel running via %s" % provider_name
            dlg_model.insertByName("Msg", lbl)

            # MCP endpoint (Claude, Claude Code)
            y = 22
            lbl_mcp = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlFixedTextModel")
            lbl_mcp.Name = "LblMcp"
            lbl_mcp.PositionX = 10
            lbl_mcp.PositionY = y
            lbl_mcp.Width = 280
            lbl_mcp.Height = 10
            lbl_mcp.Label = "MCP endpoint (Claude, Claude Code):"
            dlg_model.insertByName("LblMcp", lbl_mcp)

            y += 12
            fld_mcp = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlEditModel")
            fld_mcp.Name = "FldMcp"
            fld_mcp.PositionX = 10
            fld_mcp.PositionY = y
            fld_mcp.Width = 240
            fld_mcp.Height = 14
            fld_mcp.ReadOnly = True
            fld_mcp.Text = mcp_url or "(not available)"
            dlg_model.insertByName("FldMcp", fld_mcp)

            btn_copy_mcp = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlButtonModel")
            btn_copy_mcp.Name = "BtnCopyMcp"
            btn_copy_mcp.PositionX = 254
            btn_copy_mcp.PositionY = y
            btn_copy_mcp.Width = 36
            btn_copy_mcp.Height = 14
            btn_copy_mcp.Label = "Copy"
            dlg_model.insertByName("BtnCopyMcp", btn_copy_mcp)

            # SSE endpoint (ChatGPT, other clients)
            y += 22
            lbl_sse = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlFixedTextModel")
            lbl_sse.Name = "LblSse"
            lbl_sse.PositionX = 10
            lbl_sse.PositionY = y
            lbl_sse.Width = 280
            lbl_sse.Height = 10
            lbl_sse.Label = "SSE endpoint (ChatGPT, other clients):"
            dlg_model.insertByName("LblSse", lbl_sse)

            y += 12
            fld_sse = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlEditModel")
            fld_sse.Name = "FldSse"
            fld_sse.PositionX = 10
            fld_sse.PositionY = y
            fld_sse.Width = 240
            fld_sse.Height = 14
            fld_sse.ReadOnly = True
            fld_sse.Text = sse_url or "(not available)"
            dlg_model.insertByName("FldSse", fld_sse)

            btn_copy_sse = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlButtonModel")
            btn_copy_sse.Name = "BtnCopySse"
            btn_copy_sse.PositionX = 254
            btn_copy_sse.PositionY = y
            btn_copy_sse.Width = 36
            btn_copy_sse.Height = 14
            btn_copy_sse.Label = "Copy"
            dlg_model.insertByName("BtnCopySse", btn_copy_sse)

            # OK button
            ok_btn = dlg_model.createInstance(
                "com.sun.star.awt.UnoControlButtonModel")
            ok_btn.Name = "OKBtn"
            ok_btn.PositionX = 240
            ok_btn.PositionY = 118
            ok_btn.Width = 50
            ok_btn.Height = 14
            ok_btn.Label = "OK"
            ok_btn.PushButtonType = 1
            dlg_model.insertByName("OKBtn", ok_btn)

            dlg = smgr.createInstanceWithContext(
                "com.sun.star.awt.UnoControlDialog", ctx)
            dlg.setModel(dlg_model)
            toolkit = smgr.createInstanceWithContext(
                "com.sun.star.awt.Toolkit", ctx)
            dlg.createPeer(toolkit, None)

            # Wire copy button listeners
            from plugin.framework.dialogs import copy_to_clipboard
            import unohelper
            from com.sun.star.awt import XActionListener

            class CopyAction(unohelper.Base, XActionListener):
                def __init__(self, text, lo_ctx):
                    self._text = text
                    self._ctx = lo_ctx
                def actionPerformed(self, ev):
                    copy_to_clipboard(self._ctx, self._text)
                def disposing(self, ev):
                    pass

            if mcp_url:
                dlg.getControl("BtnCopyMcp").addActionListener(
                    CopyAction(mcp_url, ctx))
            if sse_url:
                dlg.getControl("BtnCopySse").addActionListener(
                    CopyAction(sse_url, ctx))

            dlg.execute()
            dlg.dispose()
        except Exception:
            log.exception("Tunnel status dialog error")
            from plugin.framework.dialogs import msgbox
            msgbox(ctx, "Nelson", "%s\nURL: %s" % (msg, url))
