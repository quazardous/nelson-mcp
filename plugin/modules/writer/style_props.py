# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Readable style properties, and their translation to and from UNO.

style_set takes a short list of properties an agent can name without knowing
UNO — font_name, font_size, bold… — rather than raw property names and
units. Each one knows the style families it applies to, how to validate a
value, the UNO property it becomes, and how to read that property back into
the same readable form, so the tool can report before and after.

No UNO import at module level: enums and structs are described as plain
tuples here and built by the tool, which keeps this testable without
LibreOffice.
"""

import re

PARA = "ParagraphStyles"
CHAR = "CharacterStyles"
PAGE = "PageStyles"
FAMILIES = (PARA, CHAR, PAGE)

_BOLD, _NORMAL = 150.0, 100.0          # com.sun.star.awt.FontWeight
_ALIGN = {"left": "LEFT", "center": "CENTER", "right": "RIGHT",
          "justify": "BLOCK"}           # com.sun.star.style.ParagraphAdjust
_ALIGN_BACK = {v: k for k, v in _ALIGN.items()}
_ALIGN_BACK["STRETCH"] = "justify"


class StyleValueError(ValueError):
    """A property value that cannot be applied, with a readable reason."""


def _number(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StyleValueError("%s must be a number, got %r" % (name, value))
    if not low <= value <= high:
        raise StyleValueError("%s must be between %s and %s, got %s"
                              % (name, low, high, value))
    return value


def _boolean(name, value):
    if not isinstance(value, bool):
        raise StyleValueError("%s must be true or false, got %r"
                              % (name, value))
    return value


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise StyleValueError("%s must be a non-empty string" % name)
    return value.strip()


def _mm_to_hmm(value):
    return int(round(value * 100))


def _hmm_to_mm(value):
    return round(value / 100.0, 2)


def _color(name, value):
    if not isinstance(value, str) or not re.fullmatch(
            r"#?[0-9A-Fa-f]{6}", value.strip()):
        raise StyleValueError("%s must be a colour like #1A2B3C, got %r"
                              % (name, value))
    return int(value.strip().lstrip("#"), 16)


def _color_back(raw):
    if raw is None or raw < 0:          # -1: automatic
        return "auto"
    return "#%06X" % raw


def _enum_value(raw):
    return getattr(raw, "value", raw)


# name -> (families, [(uno_property, to_uno)], from_uno, description)
# to_uno returns the value to set; ("enum", type, value) and
# ("struct", type, {fields}) are built by the caller.
def _spec():
    return {
        "font_name": (
            (PARA, CHAR), "CharFontName",
            lambda v: _text("font_name", v),
            lambda raw: raw,
            "Font family, e.g. 'Liberation Serif'."),
        "font_size": (
            (PARA, CHAR), "CharHeight",
            lambda v: float(_number("font_size", v, 1, 1000)),
            lambda raw: round(raw, 2),
            "Size in points."),
        "bold": (
            (PARA, CHAR), "CharWeight",
            lambda v: _BOLD if _boolean("bold", v) else _NORMAL,
            lambda raw: raw >= _BOLD,
            "true or false."),
        "italic": (
            (PARA, CHAR), "CharPosture",
            lambda v: ("enum", "com.sun.star.awt.FontSlant",
                       "ITALIC" if _boolean("italic", v) else "NONE"),
            lambda raw: _enum_value(raw) in ("ITALIC", "OBLIQUE"),
            "true or false."),
        "color": (
            (PARA, CHAR), "CharColor",
            lambda v: _color("color", v),
            _color_back,
            "Text colour, '#RRGGBB'."),
        "space_before": (
            (PARA,), "ParaTopMargin",
            lambda v: _mm_to_hmm(_number("space_before", v, 0, 1000)),
            _hmm_to_mm,
            "Space above the paragraph, in mm."),
        "space_after": (
            (PARA,), "ParaBottomMargin",
            lambda v: _mm_to_hmm(_number("space_after", v, 0, 1000)),
            _hmm_to_mm,
            "Space below the paragraph, in mm."),
        "line_spacing": (
            (PARA,), "ParaLineSpacing",
            lambda v: ("struct", "com.sun.star.style.LineSpacing",
                       {"Mode": 0,
                        "Height": int(_number("line_spacing", v, 6, 1000))}),
            lambda raw: (raw.Height if getattr(raw, "Mode", 0) == 0
                         else None),
            "Proportional line spacing in percent (100 = single)."),
        "align": (
            (PARA,), "ParaAdjust",
            _align,
            lambda raw: _ALIGN_BACK.get(_enum_value(_adjust_name(raw))),
            "left, center, right or justify."),
        "parent_style": (
            (PARA, CHAR), "ParentStyle",
            lambda v: _text("parent_style", v),
            lambda raw: raw or None,
            "Style this one inherits from."),
        "margin_top": (
            (PAGE,), "TopMargin",
            lambda v: _mm_to_hmm(_number("margin_top", v, 0, 1000)),
            _hmm_to_mm, "Page margin, in mm."),
        "margin_bottom": (
            (PAGE,), "BottomMargin",
            lambda v: _mm_to_hmm(_number("margin_bottom", v, 0, 1000)),
            _hmm_to_mm, "Page margin, in mm."),
        "margin_left": (
            (PAGE,), "LeftMargin",
            lambda v: _mm_to_hmm(_number("margin_left", v, 0, 1000)),
            _hmm_to_mm, "Page margin, in mm."),
        "margin_right": (
            (PAGE,), "RightMargin",
            lambda v: _mm_to_hmm(_number("margin_right", v, 0, 1000)),
            _hmm_to_mm, "Page margin, in mm."),
        "orientation": (
            (PAGE,), "IsLandscape",
            _orientation,
            lambda raw: "landscape" if raw else "portrait",
            "portrait or landscape (swaps the page size as needed)."),
    }


def _align(value):
    key = value.strip().lower() if isinstance(value, str) else None
    if key not in _ALIGN:
        raise StyleValueError("align must be one of %s, got %r"
                              % (", ".join(_ALIGN), value))
    return ("enum", "com.sun.star.style.ParagraphAdjust", _ALIGN[key])


def _adjust_name(raw):
    # ParaAdjust reads back as an enum, or as its integer value in places.
    if isinstance(raw, int):
        return ("LEFT", "RIGHT", "BLOCK", "CENTER", "STRETCH")[raw] \
            if 0 <= raw <= 4 else None
    return raw


def _orientation(value):
    key = value.strip().lower() if isinstance(value, str) else None
    if key not in ("portrait", "landscape"):
        raise StyleValueError("orientation must be portrait or landscape, "
                              "got %r" % (value,))
    return key == "landscape"


PROPERTIES = _spec()


def allowed_for(family):
    return sorted(n for n, spec in PROPERTIES.items() if family in spec[0])


def translate(family, properties):
    """Validate readable *properties* for *family*.

    Returns [(name, uno_property, uno_value)] in a stable order. Raises
    StyleValueError listing what is wrong; nothing is applied then.
    """
    if family not in FAMILIES:
        raise StyleValueError("family must be one of %s, got %r"
                              % (", ".join(FAMILIES), family))
    if not isinstance(properties, dict) or not properties:
        raise StyleValueError("properties must be a non-empty object, e.g. "
                              "{\"font_name\": \"Liberation Serif\"}")
    allowed = allowed_for(family)
    unknown = sorted(set(properties) - set(allowed))
    if unknown:
        raise StyleValueError(
            "not settable on %s: %s. Allowed: %s"
            % (family, ", ".join(unknown), ", ".join(allowed)))
    out = []
    for name in sorted(properties):
        _, uno_prop, to_uno, _, _ = PROPERTIES[name]
        out.append((name, uno_prop, to_uno(properties[name])))
    return out


def read_back(name, raw):
    """Readable form of a raw UNO value for property *name*."""
    try:
        return PROPERTIES[name][3](raw)
    except Exception:
        return None
