# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Readable style properties for style_set (#2647)."""

import pytest

from plugin.modules.writer import style_props as sp


def as_dict(changes):
    return {name: (prop, value) for name, prop, value in changes}


def test_translates_units_and_enums():
    got = as_dict(sp.translate(sp.PARA, {
        "font_name": " Liberation Serif ", "font_size": 13, "bold": True,
        "italic": False, "color": "#1a2B3c", "space_before": 4.25,
        "line_spacing": 115, "align": "Justify"}))
    assert got["font_name"] == ("CharFontName", "Liberation Serif")
    assert got["font_size"] == ("CharHeight", 13.0)
    assert got["bold"] == ("CharWeight", 150.0)
    assert got["italic"] == ("CharPosture",
                             ("enum", "com.sun.star.awt.FontSlant", "NONE"))
    assert got["color"] == ("CharColor", 0x1A2B3C)
    assert got["space_before"] == ("ParaTopMargin", 425)
    assert got["line_spacing"][1][2] == {"Mode": 0, "Height": 115}
    assert got["align"] == ("ParaAdjust", ("enum",
                            "com.sun.star.style.ParagraphAdjust", "BLOCK"))


def test_properties_are_scoped_to_their_family():
    with pytest.raises(sp.StyleValueError, match="not settable on "
                       "CharacterStyles: align"):
        sp.translate(sp.CHAR, {"align": "left"})
    with pytest.raises(sp.StyleValueError, match="Allowed: margin_bottom"):
        sp.translate(sp.PAGE, {"font_name": "X"})


@pytest.mark.parametrize("props, message", [
    ({"font_size": "12"}, "font_size must be a number"),
    ({"font_size": 0}, "between 1 and 1000"),
    ({"bold": "yes"}, "bold must be true or false"),
    ({"color": "red"}, "colour like #1A2B3C"),
    ({"align": "middle"}, "align must be one of"),
    ({"CharHeight": 12}, "not settable"),
    ({}, "non-empty object"),
])
def test_rejects_bad_values_with_a_reason(props, message):
    with pytest.raises(sp.StyleValueError, match=message):
        sp.translate(sp.PARA, props)


def test_unknown_family_is_refused():
    with pytest.raises(sp.StyleValueError, match="family must be one of"):
        sp.translate("CellStyles", {"font_name": "X"})


class Enum:
    def __init__(self, value):
        self.value = value


class Spacing:
    Mode, Height = 0, 115


@pytest.mark.parametrize("name, raw, readable", [
    ("font_size", 12.0, 12.0),
    ("bold", 150.0, True),
    ("bold", 100.0, False),
    ("italic", Enum("ITALIC"), True),
    ("color", 0x00FF00, "#00FF00"),
    ("color", -1, "auto"),
    ("space_after", 425, 4.25),
    ("line_spacing", Spacing(), 115),
    ("align", 2, "justify"),            # Writer reads ParaAdjust as a short
    ("align", Enum("CENTER"), "center"),
    ("orientation", True, "landscape"),
])
def test_reads_back_in_readable_form(name, raw, readable):
    assert sp.read_back(name, raw) == readable
