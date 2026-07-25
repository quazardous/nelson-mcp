# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer page header / footer tools.

Read and write the header/footer text of a Writer page style. Headers
and footers live on the ``PageStyles`` style family as ``HeaderText`` /
``FooterText`` (``XText`` bodies), gated by the ``HeaderIsOn`` /
``FooterIsOn`` toggles — writing turns the region on automatically.
"""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")

# region name -> (is_on property, text property)
_REGION_PROPS = {
    "header": ("HeaderIsOn", "HeaderText"),
    "footer": ("FooterIsOn", "FooterText"),
}

# com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK
PARAGRAPH_BREAK = 0


def _height_props(region):
    """Return the (dynamic-height, dynamic-spacing, height) property names."""
    prefix = "Header" if region == "header" else "Footer"
    return (prefix + "IsDynamicHeight",
            prefix + "DynamicSpacing",
            prefix + "Height")


def _set_auto_height(style, region, enabled):
    """Let the region grow with its content (or pin it to a fixed height).

    Without this, a header keeps its fixed height and taller content —
    a letterhead logo, say — overlaps the text and spills into the body.
    """
    dyn_prop, spacing_prop, _ = _height_props(region)
    style.setPropertyValue(dyn_prop, bool(enabled))
    try:
        style.setPropertyValue(spacing_prop, bool(enabled))
    except Exception:
        pass  # not offered by every page style


def _page_styles(doc):
    return doc.getStyleFamilies().getByName("PageStyles")


def _resolve_page_style(doc, name):
    """Return (style_object, resolved_name).

    When ``name`` is empty, use the page style under the view cursor
    (the page the user is looking at), falling back to ``Standard``.
    Raises ValueError with the available names if the style is unknown.
    """
    styles = _page_styles(doc)
    if not name:
        name = "Standard"
        try:
            vc = doc.getCurrentController().getViewCursor()
            cur = vc.getPropertyValue("PageStyleName")
            if cur:
                name = cur
        except Exception:
            pass
    if not styles.hasByName(name):
        available = list(styles.getElementNames())
        raise ValueError(
            "No page style named '%s'. Available: %s"
            % (name, ", ".join(available)))
    return styles.getByName(name), name


def _read_region(style, region):
    """Return the state of a header/footer region."""
    is_on_prop, text_prop = _REGION_PROPS[region]
    enabled = bool(style.getPropertyValue(is_on_prop))
    info = {"enabled": enabled, "text": ""}
    if not enabled:
        return info
    info["text"] = style.getPropertyValue(text_prop).getString()
    dyn_prop, _, height_prop = _height_props(region)
    try:
        info["auto_height"] = bool(style.getPropertyValue(dyn_prop))
        info["height_mm"] = round(
            style.getPropertyValue(height_prop) / 100.0, 1)
    except Exception:
        pass
    return info


class GetHeaderFooter(ToolBase):
    """Read the header/footer text of a Writer page style."""

    name = "header_footer_get"
    aliases = ["get_header_footer"]
    intent = "read"
    description = (
        "Read the page header and/or footer text of a Writer page style. "
        "Returns whether each region is enabled and its text. Defaults to "
        "the page style under the cursor."
    )
    parameters = {
        "type": "object",
        "properties": {
            "page_style": {
                "type": "string",
                "description": (
                    "Page style name (e.g. 'Standard'). Defaults to the "
                    "page style under the cursor."
                ),
            },
            "region": {
                "type": "string",
                "enum": ["header", "footer", "both"],
                "description": "Which region to read (default: both).",
            },
        },
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        region = kwargs.get("region", "both")
        try:
            style, resolved = _resolve_page_style(doc, kwargs.get("page_style"))
            regions = ["header", "footer"] if region == "both" else [region]
            result = {r: _read_region(style, r) for r in regions}
            return {
                "status": "ok",
                "page_style": resolved,
                **result,
            }
        except Exception as e:
            log.exception("header_footer_get failed")
            return {"status": "error", "error": str(e)}


class SetHeaderFooter(ToolBase):
    """Write the header/footer text of a Writer page style."""

    name = "header_footer_set"
    aliases = ["set_header_footer"]
    intent = "edit"
    description = (
        "Set (or append to) the page header or footer text of a Writer "
        "page style. Writing turns the region on automatically. Use "
        "left/center/right tab-separated text to align across the page "
        "(e.g. 'Left\\tCentre\\tRight'). Pass enabled=false to turn the "
        "region off."
    )
    parameters = {
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "enum": ["header", "footer"],
                "description": "Which region to write.",
            },
            "text": {
                "type": "string",
                "description": (
                    "Text to set. Tab characters split left/centre/right "
                    "portions. Ignored when enabled=false."
                ),
            },
            "page_style": {
                "type": "string",
                "description": (
                    "Page style name (e.g. 'Standard'). Defaults to the "
                    "page style under the cursor."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["replace", "append"],
                "description": (
                    "'replace' overwrites the region text (default); "
                    "'append' adds a new line after the existing text."
                ),
            },
            "enabled": {
                "type": "boolean",
                "description": (
                    "Set false to turn the region off. Default true "
                    "(enabling it to hold the text)."
                ),
            },
            "auto_height": {
                "type": "boolean",
                "description": (
                    "Let the region grow with its content, so taller "
                    "content (e.g. a logo) is not clipped and does not "
                    "overlap the body. Left unchanged when omitted."
                ),
            },
        },
        "required": ["region"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        region = kwargs.get("region")
        if region not in _REGION_PROPS:
            return {"status": "error",
                    "error": "region must be 'header' or 'footer'."}
        is_on_prop, text_prop = _REGION_PROPS[region]
        enabled = kwargs.get("enabled", True)
        mode = kwargs.get("mode", "replace")
        text = kwargs.get("text", "")

        try:
            style, resolved = _resolve_page_style(doc, kwargs.get("page_style"))

            if not enabled:
                style.setPropertyValue(is_on_prop, False)
                return {
                    "status": "ok",
                    "page_style": resolved,
                    "region": region,
                    "enabled": False,
                }

            # Turn the region on before touching its XText (it is only
            # valid once enabled).
            if not style.getPropertyValue(is_on_prop):
                style.setPropertyValue(is_on_prop, True)

            auto_height = kwargs.get("auto_height")
            if auto_height is not None:
                _set_auto_height(style, region, auto_height)

            xtext = style.getPropertyValue(text_prop)

            if mode == "append":
                cursor = xtext.createTextCursorByRange(xtext.getEnd())
                if xtext.getString():
                    xtext.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
                xtext.insertString(cursor, text, False)
            else:
                xtext.setString(text)

            result = {
                "status": "ok",
                "page_style": resolved,
                "region": region,
                "enabled": True,
                "text": xtext.getString(),
            }
            if auto_height is not None:
                result["auto_height"] = bool(auto_height)
            return result
        except Exception as e:
            log.exception("header_footer_set failed")
            return {"status": "error", "error": str(e)}
