#!/usr/bin/env python3
"""Seed LibreOffice profile with default registry settings (suppress first-run wizard, etc.)."""

import os
import re
import sys
from pathlib import Path

# The profile to seed: first argument, else LO_PROFILE_DIR, else the dev
# profile. The smoke test passes its throwaway profile explicitly.
PROFILE_DIR = Path(sys.argv[1] if len(sys.argv) > 1
                   else os.environ.get("LO_PROFILE_DIR", "/tmp/lo_dev_profile"))

# Settings to pre-seed
ITEMS = [
    ("/org.openoffice.Office.Common/Misc", "FirstRun", "false"),
    ("/org.openoffice.Office.Common/Misc", "ShowTipOfTheDay", "false"),
]


def seed_registry():
    user_dir = PROFILE_DIR / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    reg_file = user_dir / "registrymodifications.xcu"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry"'
        ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
    ]

    existing_keys: set[tuple[str, str]] = set()
    if reg_file.exists():
        content = reg_file.read_text()
        for m in re.finditer(
            r'<item oor:path="([^"]*)">\s*<prop oor:name="([^"]*)"[^>]*>'
            r'\s*<value>([^<]*)</value>',
            content,
        ):
            existing_keys.add((m.group(1), m.group(2)))
            lines.append(
                f'<item oor:path="{m.group(1)}">'
                f'<prop oor:name="{m.group(2)}" oor:op="fuse">'
                f'<value>{m.group(3)}</value></prop></item>'
            )

    for path, prop_name, value in ITEMS:
        if (path, prop_name) in existing_keys:
            continue
        lines.append(
            f'<item oor:path="{path}">'
            f'<prop oor:name="{prop_name}" oor:op="fuse">'
            f'<value>{value}</value></prop></item>'
        )

    lines.append("</oor:items>")
    reg_file.write_text("\n".join(lines) + "\n")
    print(f"Seeded registry: {reg_file}")


if __name__ == "__main__":
    seed_registry()
