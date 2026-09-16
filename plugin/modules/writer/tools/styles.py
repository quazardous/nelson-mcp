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

    name = "style_list"
    aliases = ["list_styles"]
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
    is_mutation = False

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

    name = "style_info"
    aliases = ["get_style_info"]
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
    is_mutation = False

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


class SetStyle(ToolBase):
    """Change a paragraph, character or page style."""

    name = "style_set"
    intent = "edit"
    description = (
        "Change a style's formatting: font, size, bold, italic, colour, "
        "paragraph spacing and alignment, inheritance, page margins and "
        "orientation. Changing the style changes every paragraph that uses "
        "it — e.g. to change the font of the body text, set font_name on "
        "the paragraph style the body uses ('Text body' or 'Standard'; "
        "text_read and text_search report each paragraph's style). "
        "Returns each property's value before and after."
    )
    parameters = {
        "type": "object",
        "properties": {
            "style_name": {
                "type": "string",
                "description": (
                    "Style to change, as named by style_list, text_read or "
                    "text_search."),
            },
            "family": {
                "type": "string",
                "enum": ["ParagraphStyles", "CharacterStyles", "PageStyles"],
                "description": "Style family (default: ParagraphStyles).",
            },
            "properties": {
                "type": "object",
                "description": (
                    "What to change. Paragraph and character styles: "
                    "font_name, font_size (pt), bold, italic, color "
                    "('#RRGGBB'), parent_style. Paragraph styles also: "
                    "space_before, space_after (mm), line_spacing (%), "
                    "align (left, center, right, justify). Page styles: "
                    "margin_top, margin_bottom, margin_left, margin_right "
                    "(mm), orientation (portrait, landscape)."),
                "properties": {
                    "font_name": {"type": "string"},
                    "font_size": {"type": "number"},
                    "bold": {"type": "boolean"},
                    "italic": {"type": "boolean"},
                    "color": {"type": "string"},
                    "parent_style": {"type": "string"},
                    "space_before": {"type": "number"},
                    "space_after": {"type": "number"},
                    "line_spacing": {"type": "number"},
                    "align": {"type": "string",
                              "enum": ["left", "center", "right", "justify"]},
                    "margin_top": {"type": "number"},
                    "margin_bottom": {"type": "number"},
                    "margin_left": {"type": "number"},
                    "margin_right": {"type": "number"},
                    "orientation": {"type": "string",
                                    "enum": ["portrait", "landscape"]},
                },
            },
        },
        "required": ["style_name", "properties"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from plugin.modules.writer import style_props as sp

        style_name = (kwargs.get("style_name") or "").strip()
        family = kwargs.get("family") or sp.PARA
        properties = kwargs.get("properties")

        try:
            changes = sp.translate(family, properties)
        except sp.StyleValueError as e:
            return {"status": "error", "code": "invalid_style_properties",
                    "message": str(e), "retryable": False}

        families = ctx.doc.getStyleFamilies()
        styles = families.getByName(family)
        if not style_name or not styles.hasByName(style_name):
            import difflib
            names = list(styles.getElementNames())
            close = difflib.get_close_matches(style_name, names, n=5,
                                              cutoff=0.4)
            return {"status": "error", "code": "style_not_found",
                    "message": "No %s style named '%s'." % (family, style_name),
                    "similar": close,
                    "hint": "style_list family=%s lists them all." % family,
                    "retryable": False}
        style = styles.getByName(style_name)

        if "parent_style" in properties:
            parent = properties["parent_style"].strip()
            if not styles.hasByName(parent):
                return {"status": "error", "code": "style_not_found",
                        "message": "parent_style '%s' is not a %s style."
                                   % (parent, family),
                        "retryable": False}

        before = {name: sp.read_back(name, _get(style, prop))
                  for name, prop, _ in changes}

        failed = {}
        for name, prop, value in changes:
            try:
                if prop == "IsLandscape":
                    _set_orientation(style, value)
                else:
                    style.setPropertyValue(prop, _uno_value(value))
            except Exception as e:
                failed[name] = str(e) or type(e).__name__

        after = {name: sp.read_back(name, _get(style, prop))
                 for name, prop, _ in changes}
        result = {"status": "ok" if not failed else "error",
                  "style": style_name, "family": family,
                  "before": before, "after": after}
        if failed:
            result["code"] = "style_properties_failed"
            result["failed"] = failed
            result["message"] = "Some properties were not applied."

        if "font_name" in properties and not failed.get("font_name"):
            installed = _installed_fonts(ctx)
            wanted = properties["font_name"].strip()
            if installed is not None and wanted.casefold() not in installed:
                result["warning"] = (
                    "Font '%s' is not installed here: LibreOffice keeps the "
                    "name but displays a substitute." % wanted)
        return result


def _get(style, prop):
    try:
        return style.getPropertyValue(prop)
    except Exception:
        return None


def _uno_value(value):
    if isinstance(value, tuple) and value and value[0] == "enum":
        import uno
        return uno.Enum(value[1], value[2])
    if isinstance(value, tuple) and value and value[0] == "struct":
        import uno
        struct = uno.createUnoStruct(value[1])
        for field, v in value[2].items():
            setattr(struct, field, v)
        return struct
    return value


def _set_orientation(style, landscape):
    """Flip IsLandscape and swap the page size so it matches."""
    width = style.getPropertyValue("Width")
    height = style.getPropertyValue("Height")
    if landscape != (width > height):
        style.setPropertyValue("Width", height)
        style.setPropertyValue("Height", width)
    style.setPropertyValue("IsLandscape", landscape)


def _installed_fonts(ctx):
    """Casefolded names of the fonts LibreOffice can use, or None."""
    try:
        from plugin.framework.uno_context import get_ctx
        uno_ctx = ctx.ctx or get_ctx()
        toolkit = uno_ctx.getServiceManager().createInstanceWithContext(
            "com.sun.star.awt.Toolkit", uno_ctx)
        device = toolkit.createScreenCompatibleDevice(1, 1)
        return {f.Name.casefold() for f in device.getFontDescriptors()}
    except Exception:
        log.debug("font list unavailable", exc_info=True)
        return None
