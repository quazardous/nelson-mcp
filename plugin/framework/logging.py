# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Logging for Nelson MCP.

Standard ``logging`` — setup_logging() configures the ``nelson`` logger
hierarchy with a FileHandler to ~/nelson.log.  All modules that call
``logging.getLogger("nelson.xxx")`` inherit this handler automatically.
"""

import logging
import os
import sys
import traceback
import threading

# ── Standard logging setup ─────────────────────────────────────────────

LOG_PATH = os.path.join(os.path.expanduser("~"), "nelson.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"

_setup_done = False


def setup_logging(level="DEBUG"):
    """Configure the ``nelson`` logger hierarchy.

    Forces a FileHandler on the ``nelson`` logger (not root),
    so it works regardless of root logger state set by other extensions.
    Truncates the log file on startup (mode ``"w"``) for clean sessions.

    No-op if the logger already has handlers (e.g. set up inline by main.py).
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    logger = logging.getLogger("nelson")
    if logger.handlers:
        return

    logger.propagate = False

    handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)

    numeric = getattr(logging, level.upper(), logging.DEBUG)
    logger.setLevel(numeric)


def set_log_level(level):
    """Change the ``nelson`` logger level at runtime."""
    logger = logging.getLogger("nelson")
    numeric = getattr(logging, level.upper(), logging.DEBUG)
    logger.setLevel(numeric)


# ── Exception hooks ───────────────────────────────────────────────────

_exception_hooks_installed = False


def _install_global_exception_hooks():
    """Install sys.excepthook and threading.excepthook. Idempotent."""
    global _exception_hooks_installed
    if _exception_hooks_installed:
        return
    _exception_hooks_installed = True

    _original = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
            debug_log("Unhandled exception:\n" + "".join(tb_lines).strip(),
                      context="Excepthook")
        except Exception:
            pass
        try:
            _original(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _hook

    if getattr(threading, "excepthook", None) is not None:
        _orig_t = threading.excepthook

        def _thook(args):
            try:
                msg = "Unhandled exception in thread %s: %s\n%s" % (
                    getattr(args, "thread", None),
                    getattr(args, "exc_type", args),
                    "".join(traceback.format_exception(
                        args.exc_type, args.exc_value, args.exc_traceback
                    )) if getattr(args, "exc_type", None) else "",
                )
                debug_log(msg.strip(), context="Excepthook")
            except Exception:
                pass
            try:
                if _orig_t:
                    _orig_t(args)
            except Exception:
                pass

        threading.excepthook = _thook


def install_exception_hooks():
    """Public entry point for exception hook installation."""
    _install_global_exception_hooks()


# ── Legacy file-based logging ─────────────────────────────────────────

def log_exception(ex, context="Nelson"):
    """Log an exception with traceback to the debug log."""
    try:
        tb = getattr(ex, "__traceback__", None)
        if tb is not None:
            tb_lines = traceback.format_exception(type(ex), ex, tb)
            msg = "".join(tb_lines).strip()
        else:
            msg = str(ex)
        debug_log(msg, context=context)
    except Exception:
        debug_log(str(ex), context=context)


def debug_log(msg, context=None):
    """Write one line to the log file via the nelson logger."""
    logger = logging.getLogger("nelson")
    prefix = "[%s] " % context if context else ""
    logger.debug("%s%s", prefix, msg)
