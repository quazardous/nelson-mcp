# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What /api/config may change, and what it may show.

The config API lets an agent tune Nelson on its own: read limits, the
exchange format, the name on its tracked changes. It must not let the same
agent undo the limits set for it. So the settings that decide what is
exposed, what runs and what can be reached stay reserved to Options:

- ``http.*``: the access token, the address and port, allowed origins,
  SSL, and the config API switch itself;
- ``tunnel.*``: publishing the server;
- ``debug.*``: the debug API;
- ``launcher.*``: the terminal and arguments of a command Nelson runs;
- ``*.instances``: folders the tools can reach, and the endpoints and keys
  of the AI providers;
- ``core.force_track_changes``: the guard against an agent switching off
  change recording.

Secrets are never returned: a password-type setting, or a key or token
inside a provider entry, reads as ``"***"`` when set.
"""

import json

PROTECTED_PREFIXES = ("http.", "tunnel.", "debug.", "launcher.")
PROTECTED_SUFFIXES = (".instances",)
PROTECTED_KEYS = frozenset({"core.force_track_changes"})

MASK = "***"
_SECRET_FIELDS = ("api_key", "apikey", "key", "token", "authtoken",
                  "password", "secret")


def is_protected(key):
    return (key in PROTECTED_KEYS
            or key.startswith(PROTECTED_PREFIXES)
            or key.endswith(PROTECTED_SUFFIXES))


def refused_keys(changes):
    """The keys of a POST body the API must not write, in order."""
    return [k for k in changes if is_protected(str(k))]


def _secret_field(name):
    name = str(name).lower()
    return name in _SECRET_FIELDS or name.endswith(("_key", "_token",
                                                    "_secret", "password"))


def _mask_entries(value):
    """Mask secret fields inside a provider list (a JSON string)."""
    try:
        entries = json.loads(value)
    except (TypeError, ValueError):
        return value
    changed = False

    def walk(node):
        nonlocal changed
        if isinstance(node, dict):
            for k, v in node.items():
                if _secret_field(k) and isinstance(v, str) and v:
                    node[k] = MASK
                    changed = True
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(entries)
    return json.dumps(entries) if changed else value


def shown(key, value, schema=None):
    """*value* as /api/config returns it: secrets masked."""
    if value in (None, ""):
        return value
    widget = (schema or {}).get("widget")
    if widget == "password" or _secret_field(key.rsplit(".", 1)[-1]):
        return MASK
    if key.endswith(".instances"):
        return _mask_entries(value)
    return value
