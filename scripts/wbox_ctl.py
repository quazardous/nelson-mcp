#!/usr/bin/env python3
# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Drive a wbox compositor from make, without going through MCP.

wbox-mcp only exposes its compositor as MCP tools, which a Makefile cannot
call. This script uses the same library directly, so `make` can start
LibreOffice inside a nested compositor, stop it and screenshot it.

It must run under wbox's own interpreter (wbox lives in its own venv, on a
different Python than the system one pyuno needs), which is why the Makefile
invokes it through $(WBOX_PYTHON) rather than python3.

    wbox_ctl.py up    CONFIG [-s key=value ...]
    wbox_ctl.py down  CONFIG [-s key=value ...]
    wbox_ctl.py shot  CONFIG [-s key=value ...] [--name NAME]
    wbox_ctl.py status CONFIG [-s key=value ...]

Headless by default: the compositor renders offscreen and nothing appears on
the desktop. Set WBOX_VISIBLE=1 to get a window, for when the assertion is
something you have to look at. An explicit `-s headless=...` still wins.

The instance is identified by the config's `name`, and its PIDs live in a
state file, so `down` can stop an instance a previous `up` started — and the
lo-wbox MCP tools see the same instance when the name matches.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from wbox.config import apply_overrides, load_config
from wbox.server import _build_app_cmd, _build_app_env, build_compositor

_TRUE = ("1", "true", "yes", "on")


def _headless_from_env():
    return os.environ.get("WBOX_VISIBLE", "").strip().lower() not in _TRUE


def _load(argv):
    if not argv:
        sys.exit(__doc__)
    config_path = Path(argv[0]).resolve()
    overrides, name, i = [], None, 1
    while i < len(argv):
        if argv[i] in ("-s", "--set") and i + 1 < len(argv):
            overrides.append(argv[i + 1])
            i += 2
        elif argv[i] == "--name" and i + 1 < len(argv):
            name = argv[i + 1]
            i += 2
        else:
            sys.exit("unknown argument: %s" % argv[i])

    cfg = load_config(config_path)
    cfg["headless"] = _headless_from_env()
    apply_overrides(cfg, overrides)          # explicit overrides win
    cfg["_config_dir"] = str(config_path.parent)
    # Relative paths in the config (log dir, screenshots, pre_launch scripts)
    # are relative to the config file, as they are for wbox-mcp serve.
    os.chdir(config_path.parent)
    return cfg, name


def _run_pre_launch(cfg):
    for script in cfg.get("app", {}).get("pre_launch", []) or []:
        result = subprocess.run(script, shell=True, cwd=cfg["_config_dir"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            sys.exit("pre_launch failed: %s\n%s%s"
                     % (script, result.stdout, result.stderr))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    command, rest = sys.argv[1], sys.argv[2:]
    cfg, name = _load(rest)
    comp = build_compositor(cfg)

    if command == "up":
        _run_pre_launch(cfg)
        result = comp.launch(_build_app_cmd(cfg), _build_app_env(cfg))
        result["headless"] = cfg["headless"]
    elif command == "down":
        result = comp.kill()
    elif command == "shot":
        result = comp.screenshot(name)
    elif command == "status":
        result = {"running": comp.is_running(), "headless": cfg["headless"]}
    else:
        sys.exit("unknown command: %s\n%s" % (command, __doc__))

    print(json.dumps(result, default=str))
    return 1 if isinstance(result, dict) and result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
