# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Style inspection tools for all document types."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")

# Properties to attempt reading per style family.
_FAMILY_PROPS = {
    "ParagraphStyles": [
        "ParentStyle", "FollowStyle",
        "CharFontName", "CharHeight", "CharWeight",
        "ParaAdjust", "ParaTopMargin", "ParaBottomMargin",
    ],
    "CharacterStyles": [
        "ParentStyle", "CharFontName", "CharHeight",
        "CharWeight", "CharPosture", "CharColor",
    ],
    "CellStyles": [
        "ParentStyle", "CellBackColor",
    ],
}


class ListStyles(ToolBase):
    """List available styles in a given family."""

    name = "list_styles"
    intent = "edit"
    description = (
        "List available styles in the document. "
        "Omit family to list all available style families. "
        "Works on all document types (Writer, Calc, Draw, Impress)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "family": {
                "type": "string",
                "description": (
                    "Style family to list (e.g. ParagraphStyles, "
                    "CellStyles, PageStyles). Omit to list families."
                ),
            },
        },
        "required": [],
    }
    doc_types = None  # all document types

    def execute(self, ctx, **kwargs):
        family = kwargs.get("family")
        doc = ctx.doc
        families = doc.getStyleFamilies()

        # No family specified → list available families
        if not family:
            available = list(families.getElementNames())
            return {
                "status": "ok",
                "families": available,
                "count": len(available),
            }

        if not families.hasByName(family):
            available = list(families.getElementNames())
            return {
                "status": "error",
                "message": "Unknown style family: %s" % family,
                "available_families": available,
            }

        style_family = families.getByName(family)
        styles = []
        for name in style_family.getElementNames():
            style = style_family.getByName(name)
            entry = {
                "name": name,
                "is_user_defined": style.isUserDefined(),
                "is_in_use": style.isInUse(),
            }
            try:
                entry["parent_style"] = style.getPropertyValue("ParentStyle")
            except Exception:
                pass
            styles.append(entry)

        return {
            "status": "ok",
            "family": family,
            "styles": styles,
            "count": len(styles),
        }


class GetStyleInfo(ToolBase):
    """Get detailed properties of a named style."""

    name = "get_style_info"
    intent = "edit"
    description = (
        "Get detailed properties of a specific style "
        "(font, size, margins, etc.). "
        "Works on all document types."
    )
    parameters = {
        "type": "object",
        "properties": {
            "style_name": {
                "type": "string",
                "description": "Name of the style to inspect.",
            },
            "family": {
                "type": "string",
                "description": (
                    "Style family (e.g. ParagraphStyles, CellStyles). "
                    "Default: first available family."
                ),
            },
        },
        "required": ["style_name"],
    }
    doc_types = None  # all document types

    def execute(self, ctx, **kwargs):
        style_name = kwargs.get("style_name", "")
        family = kwargs.get("family")

        if not style_name:
            return {"status": "error", "message": "style_name is required."}

        doc = ctx.doc
        families = doc.getStyleFamilies()

        # Default to first family if not specified
        if not family:
            family = families.getElementNames()[0]

        if not families.hasByName(family):
            return {
                "status": "error",
                "message": "Unknown style family: %s" % family,
                "available_families": list(families.getElementNames()),
            }

        style_family = families.getByName(family)
        if not style_family.hasByName(style_name):
            return {
                "status": "error",
                "message": "Style '%s' not found in %s." % (style_name, family),
            }

        style = style_family.getByName(style_name)
        info = {
            "name": style_name,
            "family": family,
            "is_user_defined": style.isUserDefined(),
            "is_in_use": style.isInUse(),
        }
        for prop_name in _FAMILY_PROPS.get(family, []):
            try:
                info[prop_name] = style.getPropertyValue(prop_name)
            except Exception:
                pass

        return {"status": "ok", **info}
