# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer equations: LibreOffice Math objects in a text (GitHub #49).

An equation is a TextEmbeddedObject with the Math CLSID, nearly always
anchored as a character. Its model holds the StarMath source in Formula.
What docs/analysis/equations-plan.md found over UNO, and this module
relies on:

- a paragraph's string leaves equations out; its portion enumeration has
  them as Frame portions;
- the anchor's text tells where one sits: SwXBodyText, SwXCell (with
  CellName), SwXTextFrame, SwXHeadFootText;
- Writer's undo does not see a change to Formula: the Math model keeps its
  own undo. Replacing the object is undone in one step;
- rewriting a paragraph with setString() deletes its equations;
- nothing reports a StarMath syntax error, but the MathML export of a
  broken formula has an empty <mrow/> where an operand is missing.
"""

import os
import re
import tempfile

MATH_CLSID = "078b7aba-54fc-457f-8551-6147e776a997"

#: writer.equation_update: how equation_set changes an equation.
UPDATE_MODES = ("replace", "in_place")
DEFAULT_UPDATE_MODE = "replace"

# A number cell next to a numbered equation: "(1)", "(2.3)", "[4a]".
_NUMBER_CELL = re.compile(r"^\s*[(\[]\s*[\w.\-]+\s*[)\]]\s*$")


def is_math(obj):
    clsid = _prop(obj, "CLSID")
    return isinstance(clsid, str) and clsid.lower() == MATH_CLSID


def source(obj):
    try:
        return obj.getEmbeddedObject().getPropertyValue("Formula")
    except Exception:
        return ""


def math_objects(doc):
    """{name: object} for every equation in the document."""
    found = {}
    try:
        objects = doc.getEmbeddedObjects()
        for name in objects.getElementNames():
            obj = objects.getByName(name)
            if is_math(obj):
                found[name] = obj
    except Exception:
        pass
    return found


def find(doc, name):
    return math_objects(doc).get(name)


def in_portion(portion):
    """The equations a Frame portion anchors, as {name, formula}."""
    found = []
    try:
        contents = portion.createContentEnumeration(
            "com.sun.star.text.TextContent")
    except Exception:
        return found
    while contents.hasMoreElements():
        obj = contents.nextElement()
        if is_math(obj):
            found.append({"name": obj.getName(), "formula": source(obj)})
    return found


def in_paragraph(para):
    """Names of the equations anchored in *para*, in order."""
    names = []
    try:
        portions = para.createEnumeration()
    except Exception:
        return names
    while portions.hasMoreElements():
        portion = portions.nextElement()
        if _prop(portion, "TextPortionType") == "Frame":
            names.extend(e["name"] for e in in_portion(portion))
    return names


def location(doc, obj, para_ranges, doc_svc):
    """Where *obj* sits: body paragraph, table cell, frame, header/footer."""
    loc = {}
    try:
        anchor = obj.getAnchor()
        text = anchor.getText()
        impl = text.getImplementationName()
    except Exception:
        return {"area": "unknown"}
    if impl == "SwXBodyText":
        loc["area"] = "body"
        loc["paragraph_index"] = doc_svc.find_paragraph_for_range(
            anchor, para_ranges, text)
    elif impl == "SwXCell":
        loc["area"] = "table"
        cell_name = _prop(text, "CellName")
        loc["cell"] = cell_name
        table = _table_of(doc, text, cell_name)
        if table is not None:
            loc["table"] = table.getName()
            number = _equation_number(table, cell_name)
            if number:
                loc["number"] = number
    elif impl == "SwXTextFrame":
        loc["area"] = "frame"
        try:
            loc["frame"] = text.getName()
        except Exception:
            pass
    elif impl == "SwXHeadFootText":
        loc["area"] = "header_footer"
    else:
        loc["area"] = impl
    loc["inline"] = _shares_paragraph(anchor)
    return loc


def check_syntax(obj):
    """A warning when the formula looks broken, else None.

    Heuristic: LibreOffice leaves an empty <mrow/> in the MathML of a
    formula with a missing operand ("{a over", "sqrt{", "x^^2"). A formula
    that writes an empty group on purpose ("{}") gives the same, so this
    never refuses, it warns.
    """
    formula = source(obj)
    if "{}" in formula.replace(" ", ""):
        return None
    mathml = _mathml(obj)
    if mathml is None or "<mrow/>" not in mathml:
        return None
    return ("The formula may have a syntax error: LibreOffice found a "
            "missing operand in %r. Check braces and operators." % formula)


def update_mode(config):
    try:
        mode = config.proxy_for("writer").get("equation_update")
    except Exception:
        mode = None
    return mode if mode in UPDATE_MODES else DEFAULT_UPDATE_MODE


def recording(doc):
    try:
        return bool(doc.getPropertyValue("RecordChanges"))
    except Exception:
        return False


NOT_TRACKED = ("Change recording is on, but LibreOffice does not record "
               "equation changes as tracked changes.")


def _mathml(obj):
    import uno
    from com.sun.star.beans import PropertyValue
    fd, path = tempfile.mkstemp(suffix=".mml")
    os.close(fd)
    try:
        prop = PropertyValue()
        prop.Name, prop.Value = "FilterName", "MathML XML (Math)"
        obj.getEmbeddedObject().storeToURL(
            uno.systemPathToFileUrl(path), (prop,))
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _table_of(doc, cell, cell_name):
    try:
        tables = doc.getTextTables()
        for name in tables.getElementNames():
            table = tables.getByName(name)
            try:
                if table.getCellByName(cell_name) == cell:
                    return table
            except Exception:
                continue
    except Exception:
        pass
    return None


def _equation_number(table, cell_name):
    """The number of a numbered equation: Writer's fn AutoText puts the
    equation and its number in a borderless table of two cells."""
    try:
        names = list(table.getCellNames())
    except Exception:
        return None
    if len(names) != 2 or cell_name not in names:
        return None
    other = names[1 - names.index(cell_name)]
    text = table.getCellByName(other).getString()
    return text.strip() if _NUMBER_CELL.match(text) else None


def _shares_paragraph(anchor):
    """True when the paragraph holds text besides its equations."""
    try:
        text = anchor.getText()
        cursor = text.createTextCursorByRange(anchor.getStart())
        cursor.gotoStartOfParagraph(False)
        cursor.gotoEndOfParagraph(True)
        return bool(cursor.getString().strip())
    except Exception:
        return False


def _prop(obj, name):
    try:
        return obj.getPropertyValue(name)
    except Exception:
        return None
