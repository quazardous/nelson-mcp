# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer equation tools (GitHub #49): list, set, insert, delete.

Equations are LibreOffice Math objects; see plugin/modules/writer/equations.py
for what they are over UNO and docs/analysis/equations-plan.md for the
choices made here.
"""

from plugin.framework.tool_base import ToolBase
from plugin.modules.writer import equations as eq

_SYNTAX_NOTE = (
    "StarMath syntax, as in LibreOffice Math: '{a} over {b}', 'x^2', "
    "'x_{i}', 'sqrt{x}', 'sum from {i=1} to {n} x_i', 'alpha', 'int from a "
    "to b f(x) dx'. LibreOffice normalizes spacing and braces, so the source "
    "read back may differ in form from what was written.")


def _not_found(ctx, name):
    return {"status": "error", "code": "equation_not_found",
            "message": "No equation named '%s'." % name,
            "available": sorted(eq.math_objects(ctx.doc)),
            "retryable": False}


def _describe(ctx, name, obj, detail=False):
    doc_svc = ctx.services.document
    para_ranges = doc_svc.get_paragraph_ranges(ctx.doc)
    entry = {"name": name, "formula": eq.source(obj)}
    entry.update(eq.location(ctx.doc, obj, para_ranges, doc_svc))
    if detail:
        model = obj.getEmbeddedObject()
        for key, prop in (("base_font_size", "BaseFontHeight"),
                          ("alignment", "Alignment")):
            try:
                value = model.getPropertyValue(prop)
            except Exception:
                continue
            if prop == "Alignment":
                value = {0: "left", 1: "center", 2: "right"}.get(value, value)
            entry[key] = value
        try:
            entry["anchor"] = obj.getPropertyValue("AnchorType").value
        except Exception:
            pass
    return entry


def _order(entry):
    # Body equations first, in reading order; then the rest by name.
    if entry.get("area") == "body":
        return (0, entry.get("paragraph_index", -1), entry["name"])
    return (1, 0, entry["name"])


class ListEquations(ToolBase):
    """List the equations of a Writer document, or read one."""

    name = "equation_list"
    description = (
        "List the equations (LibreOffice Math objects) in the document: "
        "name, StarMath source, and where each sits (body paragraph_index, "
        "table and cell, frame, header/footer; inline when it shares its "
        "paragraph with text; number for a numbered equation). Give name to "
        "read one equation with its base font size and alignment.")
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Equation name from the list, e.g. 'Object1'.",
            },
        },
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        objects = eq.math_objects(ctx.doc)
        name = kwargs.get("name")
        if name:
            obj = objects.get(name)
            if obj is None:
                return _not_found(ctx, name)
            return {"status": "ok",
                    "equation": _describe(ctx, name, obj, detail=True)}
        listed = sorted((_describe(ctx, n, o) for n, o in objects.items()),
                        key=_order)
        return {"status": "ok", "equations": listed, "count": len(listed)}


class SetEquation(ToolBase):
    """Change an equation's source, in place."""

    name = "equation_set"
    description = (
        "Change an equation: its StarMath source, and optionally its base "
        "font size. Position, anchoring and numbering stay. " + _SYNTAX_NOTE)
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string",
                     "description": "Equation name from equation_list."},
            "formula": {"type": "string",
                        "description": "New StarMath source."},
            "base_font_size": {"type": "integer",
                               "description": "Base font size in points."},
        },
        "required": ["name", "formula"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        name = kwargs["name"]
        old = eq.find(ctx.doc, name)
        if old is None:
            return _not_found(ctx, name)
        mode = eq.update_mode(ctx.services.get("config"))
        result = {"status": "ok", "name": name, "mode": mode}
        if mode == "replace" and _as_character(old):
            target = _replace(ctx.doc, old, kwargs["formula"])
        else:
            target = old
            target.getEmbeddedObject().setPropertyValue(
                "Formula", kwargs["formula"])
            result["mode"] = "in_place"
            result["undo"] = False
            _warn(result, "Changed in place: doc_undo does not revert an "
                          "equation's source (setting "
                          "writer.equation_update).")
        size = kwargs.get("base_font_size")
        if size:
            target.getEmbeddedObject().setPropertyValue(
                "BaseFontHeight", int(size))
        result["formula"] = eq.source(target)
        _warn(result, eq.check_syntax(target))
        if eq.recording(ctx.doc):
            _warn(result, eq.NOT_TRACKED)
        return result


class InsertEquation(ToolBase):
    """Insert an equation."""

    name = "equation_insert"
    description = (
        "Insert an equation. display 'block' puts it in a paragraph of its "
        "own, centred, before or after the target paragraph; 'inline' "
        "appends it to the target paragraph's text. Give table_name and "
        "cell to put it in a table cell instead. Returns its name. "
        + _SYNTAX_NOTE)
    parameters = {
        "type": "object",
        "properties": {
            "formula": {"type": "string", "description": "StarMath source."},
            "paragraph_index": {"type": "integer",
                                "description": "Target paragraph (0-based)."},
            "locator": {"type": "string",
                        "description": ("Target locator ('paragraph:N', "
                                        "'heading_text:Title', ...). "
                                        "Overrides paragraph_index.")},
            "display": {"type": "string", "enum": ["block", "inline"],
                        "description": "Default 'block'."},
            "position": {"type": "string", "enum": ["before", "after"],
                         "description": ("For block: before or after the "
                                         "target paragraph (default "
                                         "'after').")},
            "table_name": {"type": "string",
                           "description": "Table to insert into."},
            "cell": {"type": "string",
                     "description": "Cell of table_name, e.g. 'B2'."},
            "base_font_size": {"type": "integer",
                               "description": "Base font size in points."},
        },
        "required": ["formula"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK

        doc = ctx.doc
        if kwargs.get("table_name") or kwargs.get("cell"):
            cell = _cell(doc, kwargs.get("table_name"), kwargs.get("cell"))
            if isinstance(cell, dict):
                return cell
            text, cursor = cell, cell.createTextCursor()
            cursor.gotoEnd(False)
        else:
            from plugin.modules.writer.tools.content import \
                _resolve_para_index
            para_index = _resolve_para_index(ctx, kwargs)
            if para_index is None:
                return {"status": "error", "code": "invalid_params",
                        "message": ("Give paragraph_index or locator, or "
                                    "table_name and cell."),
                        "retryable": False}
            paras = ctx.services.document.get_paragraph_ranges(doc)
            if not 0 <= para_index < len(paras) \
                    or not hasattr(paras[para_index], "getStart"):
                return {"status": "error", "code": "invalid_params",
                        "message": "Paragraph %d is not a text paragraph."
                        % para_index, "retryable": False}
            target = paras[para_index]
            text = doc.getText()
            if kwargs.get("display", "block") == "inline":
                cursor = text.createTextCursorByRange(target.getEnd())
            elif kwargs.get("position", "after") == "before":
                cursor = text.createTextCursorByRange(target.getStart())
                text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
                cursor.gotoPreviousParagraph(False)
                _centre(cursor)
            else:
                cursor = text.createTextCursorByRange(target.getEnd())
                text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
                _centre(cursor)

        obj = _new_equation(doc, text, cursor, kwargs["formula"])
        size = kwargs.get("base_font_size")
        if size:
            obj.getEmbeddedObject().setPropertyValue(
                "BaseFontHeight", int(size))
        result = {"status": "ok", "name": obj.getName(),
                  "formula": eq.source(obj)}
        result.update(eq.location(
            doc, obj, ctx.services.document.get_paragraph_ranges(doc),
            ctx.services.document))
        _warn(result, eq.check_syntax(obj))
        if eq.recording(doc):
            _warn(result, eq.NOT_TRACKED)
        return result


class DeleteEquation(ToolBase):
    """Delete an equation."""

    name = "equation_delete"
    description = (
        "Delete an equation. A body paragraph left empty by it is removed "
        "too.")
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string",
                     "description": "Equation name from equation_list."},
        },
        "required": ["name"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        name = kwargs["name"]
        obj = eq.find(ctx.doc, name)
        if obj is None:
            return _not_found(ctx, name)
        anchor = obj.getAnchor()
        text = anchor.getText()
        cursor = text.createTextCursorByRange(anchor.getStart())
        text.removeTextContent(obj)
        removed_paragraph = False
        if text.getImplementationName() == "SwXBodyText":
            cursor.gotoStartOfParagraph(False)
            cursor.gotoEndOfParagraph(True)
            if not cursor.getString() and not eq.in_paragraph(
                    _paragraph_at(text, cursor)):
                # Take the paragraph break with it, unless it is the last.
                if cursor.goRight(1, True):
                    cursor.setString("")
                    removed_paragraph = True
        result = {"status": "ok", "name": name,
                  "removed_paragraph": removed_paragraph}
        if eq.recording(ctx.doc):
            _warn(result, eq.NOT_TRACKED)
        return result


# ── helpers ──────────────────────────────────────────────────────────────

def _new_equation(doc, text, cursor, formula):
    import uno
    obj = doc.createInstance("com.sun.star.text.TextEmbeddedObject")
    obj.setPropertyValue("CLSID", eq.MATH_CLSID.upper())
    obj.setPropertyValue("AnchorType", uno.Enum(
        "com.sun.star.text.TextContentAnchorType", "AS_CHARACTER"))
    text.insertTextContent(cursor, obj, False)
    obj.getEmbeddedObject().setPropertyValue("Formula", formula)
    return obj


def _replace(doc, old, formula):
    """Swap *old* for a new equation at the same place, same name.

    Writer's undo does not see a change to a Math model's source, but it
    does see an object inserted and one removed: one doc_undo brings the
    old equation back. The new one takes the old one's properties and name.
    """
    anchor = old.getAnchor()
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor.getStart())
    name = old.getName()
    new = _new_equation(doc, text, cursor, formula)
    _copy_model(old.getEmbeddedObject(), new.getEmbeddedObject())
    for prop in ("VertOrient", "VertOrientPosition", "VertOrientRelation"):
        try:
            new.setPropertyValue(prop, old.getPropertyValue(prop))
        except Exception:
            pass
    text.removeTextContent(old)
    try:
        new.setName(name)
    except Exception:
        pass
    return new


def _copy_model(src, dst):
    """Copy the Math model's settings (fonts, sizes, spacing, alignment)."""
    try:
        props = src.getPropertySetInfo().getProperties()
    except Exception:
        return
    from com.sun.star.beans.PropertyAttribute import READONLY
    for prop in props:
        if prop.Name in ("Formula", "RuntimeUID") or prop.Attributes & READONLY:
            continue
        try:
            dst.setPropertyValue(prop.Name, src.getPropertyValue(prop.Name))
        except Exception:
            continue


def _as_character(obj):
    try:
        return obj.getPropertyValue("AnchorType").value == "AS_CHARACTER"
    except Exception:
        return False


def _cell(doc, table_name, cell_name):
    tables = doc.getTextTables()
    if not table_name or not cell_name or not tables.hasByName(table_name):
        return {"status": "error", "code": "invalid_params",
                "message": "Table '%s' not found; give table_name and cell."
                % table_name,
                "available": list(tables.getElementNames()),
                "retryable": False}
    cell = tables.getByName(table_name).getCellByName(cell_name)
    if cell is None:
        return {"status": "error", "code": "invalid_params",
                "message": "Table '%s' has no cell '%s'."
                % (table_name, cell_name), "retryable": False}
    return cell


def _centre(cursor):
    # ParaAdjust is a short holding a ParagraphAdjust value: CENTER is 3.
    cursor.setPropertyValue("ParaAdjust", 3)


def _paragraph_at(text, cursor):
    """The paragraph element under *cursor*, for a portion walk."""
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        para = enum.nextElement()
        try:
            if text.compareRegionStarts(para.getStart(), cursor) >= 0 \
                    and text.compareRegionEnds(para.getEnd(), cursor) <= 0:
                return para
        except Exception:
            continue
    return None


def _warn(result, text):
    if not text:
        return
    previous = result.get("warning")
    result["warning"] = "%s %s" % (previous, text) if previous else text
