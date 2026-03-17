# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Template manager — load and render text templates with placeholders.

Templates are plain text files with ``{placeholder}`` substitution.
Each module keeps its own templates in a ``templates/`` subdirectory.

Usage::

    from plugin.framework.template_manager import render, render_file

    # Inline template
    text = render("Hello {name}, you have {count} items.", name="World", count=3)

    # From a file (relative to caller's module)
    text = render_file("ai_images", "universe.txt",
                       folder="ief 2026", descriptions="...")

    # With language variant
    text = render_file("ai_images", "universe.txt", lang="fr",
                       folder="ief 2026")
    # Looks for: templates/fr/universe.txt, then templates/universe.txt
"""

import logging
import os

log = logging.getLogger("nelson.framework.templates")

# Cache: (module_name, template_name, lang) -> template string
_cache = {}

# Base path for all module templates
_MODULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules")


def render(template, **kwargs):
    """Render an inline template string with {placeholder} substitution.

    Missing placeholders are left as-is. Extra kwargs are ignored.
    """
    try:
        return template.format_map(_SafeDict(kwargs))
    except Exception:
        return template


def render_file(module_name, template_name, lang=None, **kwargs):
    """Load a template file from a module's templates/ dir and render it.

    Args:
        module_name: Dotted module name (e.g. "ai_images"). Underscores
                     and dots are both accepted for directory lookup.
        template_name: Filename (e.g. "universe.txt").
        lang: Optional language code (e.g. "fr"). If provided, looks for
              ``templates/{lang}/{template_name}`` first, then falls back
              to ``templates/{template_name}``.
        **kwargs: Placeholder values.

    Returns:
        Rendered template string, or empty string if not found.
    """
    key = (module_name, template_name, lang)
    if key not in _cache:
        _cache[key] = _load_template(module_name, template_name, lang)
    return render(_cache[key], **kwargs)


def clear_cache():
    """Clear the template cache (useful for development)."""
    _cache.clear()


def _load_template(module_name, template_name, lang):
    """Find and read a template file."""
    # Try both dot and underscore variants for module dir name
    candidates = [
        module_name.replace(".", "_"),
        module_name.replace("_", "."),
        module_name,
    ]

    for mod_dir_name in candidates:
        base = os.path.join(_MODULES_DIR, mod_dir_name, "templates")
        if not os.path.isdir(base):
            continue

        # Try language-specific first
        if lang:
            path = os.path.join(base, lang, template_name)
            if os.path.isfile(path):
                return _read(path)

        # Fallback to default
        path = os.path.join(base, template_name)
        if os.path.isfile(path):
            return _read(path)

    log.warning("Template not found: %s/%s (lang=%s)", module_name,
                template_name, lang)
    return ""


def _read(path):
    """Read a template file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class _SafeDict(dict):
    """Dict that returns {key} for missing keys instead of raising."""

    def __missing__(self, key):
        return "{%s}" % key
