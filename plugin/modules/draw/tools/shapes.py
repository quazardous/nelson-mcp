# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shape tools for all document types with drawing layer."""

from plugin.framework.tool_base import ToolBase


def _parse_color(color_str):
    if not color_str:
        return None
    color_str = color_str.strip().lower()
    names = {
        "red": 0xFF0000,
        "green": 0x00FF00,
        "blue": 0x0000FF,
        "yellow": 0xFFFF00,
        "white": 0xFFFFFF,
        "black": 0x000000,
        "orange": 0xFF8C00,
        "purple": 0x800080,
        "gray": 0x808080,
    }
    if color_str in names:
        return names[color_str]
    if color_str.startswith("#"):
        try:
            return int(color_str[1:], 16)
        except ValueError:
            return None
    return None


def _resolve_page(ctx, **kwargs):
    """Resolve draw page from context + kwargs (after flatten)."""
    from plugin.modules.draw.bridge import get_draw_page
    return get_draw_page(
        ctx,
        page_index=kwargs.get("page_index"),
        sheet_name=kwargs.get("sheet_name"),
    )


class ListPages(ToolBase):
    name = "list_pages"
    description = (
        "List all pages/slides in a Draw/Impress document. "
        "For Calc, lists sheets (use list_sheets instead). "
        "For Writer, returns the single drawing layer."
    )
    parameters = {"type": "object", "properties": {}, "required": []}
    doc_types = ["draw", "impress"]
    tier = "core"

    def execute(self, ctx, **kwargs):
        from plugin.modules.draw.bridge import DrawBridge
        bridge = DrawBridge(ctx.doc)
        pages = bridge.get_pages()
        return {
            "status": "ok",
            "pages": ["Page %d" % i for i in range(pages.getCount())],
            "count": pages.getCount(),
        }


class GetDrawSummary(ToolBase):
    name = "get_draw_summary"
    intent = "edit"
    description = (
        "Return a summary of shapes on a page. "
        "Works on all document types with a drawing layer."
    )
    parameters = {
        "type": "object",
        "properties": {
            "draw": {
                "type": "object",
                "description": "Draw/Impress options",
                "properties": {
                    "page_index": {
                        "type": "integer",
                        "description": "0-based page index (active page if omitted)",
                    },
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc options",
                "properties": {
                    "sheet_name": {
                        "type": "string",
                        "description": "Sheet name (active sheet if omitted)",
                    },
                },
            },
        },
        "required": [],
    }
    doc_types = None  # all document types

    def execute(self, ctx, **kwargs):
        page, _ = _resolve_page(ctx, **kwargs)
        shapes = []
        for i in range(page.getCount()):
            s = page.getByIndex(i)
            info = {
                "index": i,
                "type": s.getShapeType(),
                "x": s.getPosition().X,
                "y": s.getPosition().Y,
                "width": s.getSize().Width,
                "height": s.getSize().Height,
            }
            if hasattr(s, "getString"):
                info["text"] = s.getString()
            shapes.append(info)
        return {"status": "ok", "shapes": shapes}


class CreateShape(ToolBase):
    name = "create_shape"
    description = (
        "Create a new shape on the drawing layer. "
        "Works on all document types."
    )
    parameters = {
        "type": "object",
        "properties": {
            "shape_type": {
                "type": "string",
                "enum": ["rectangle", "ellipse", "text", "line"],
                "description": "Type of shape",
            },
            "x": {"type": "integer", "description": "X position (1/100 mm)"},
            "y": {"type": "integer", "description": "Y position (1/100 mm)"},
            "width": {"type": "integer", "description": "Width (1/100 mm)"},
            "height": {"type": "integer", "description": "Height (1/100 mm)"},
            "text": {"type": "string", "description": "Initial text"},
            "bg_color": {
                "type": "string",
                "description": "Hex (#FF0000) or name (red)",
            },
            "draw": {
                "type": "object",
                "description": "Draw/Impress options",
                "properties": {
                    "page_index": {
                        "type": "integer",
                        "description": "Page index (active page if omitted)",
                    },
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc options",
                "properties": {
                    "sheet_name": {
                        "type": "string",
                        "description": "Sheet name (active sheet if omitted)",
                    },
                },
            },
        },
        "required": ["shape_type", "x", "y", "width", "height"],
    }
    doc_types = None  # all document types
    tier = "core"
    is_mutation = True

    def execute(self, ctx, **kwargs):
        page, _ = _resolve_page(ctx, **kwargs)
        type_map = {
            "rectangle": "com.sun.star.drawing.RectangleShape",
            "ellipse": "com.sun.star.drawing.EllipseShape",
            "text": "com.sun.star.drawing.TextShape",
            "line": "com.sun.star.drawing.LineShape",
        }
        uno_type = type_map.get(kwargs["shape_type"])
        if not uno_type:
            return {
                "status": "error",
                "message": "Unsupported shape type: %s" % kwargs["shape_type"],
            }
        from com.sun.star.awt import Size, Point
        shape = ctx.doc.createInstance(uno_type)
        page.add(shape)
        shape.setSize(Size(kwargs["width"], kwargs["height"]))
        shape.setPosition(Point(kwargs["x"], kwargs["y"]))
        if kwargs.get("text") and hasattr(shape, "setString"):
            shape.setString(kwargs["text"])
        if kwargs.get("bg_color"):
            color = _parse_color(kwargs["bg_color"])
            if color is not None:
                prop = (
                    "LineColor"
                    if "LineShape" in shape.getShapeType()
                    else "FillColor"
                )
                try:
                    shape.setPropertyValue(prop, color)
                except Exception:
                    pass
        return {
            "status": "ok",
            "message": "Created %s" % kwargs["shape_type"],
            "shape_index": page.getCount() - 1,
        }


class EditShape(ToolBase):
    name = "edit_shape"
    intent = "edit"
    description = (
        "Modify properties of an existing shape. "
        "Works on all document types."
    )
    parameters = {
        "type": "object",
        "properties": {
            "shape_index": {
                "type": "integer",
                "description": "Index of the shape",
            },
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "text": {"type": "string"},
            "bg_color": {"type": "string"},
            "draw": {
                "type": "object",
                "description": "Draw/Impress options",
                "properties": {
                    "page_index": {"type": "integer"},
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc options",
                "properties": {
                    "sheet_name": {"type": "string"},
                },
            },
        },
        "required": ["shape_index"],
    }
    doc_types = None  # all document types
    is_mutation = True

    def execute(self, ctx, **kwargs):
        page, _ = _resolve_page(ctx, **kwargs)
        shape = page.getByIndex(kwargs["shape_index"])
        if "x" in kwargs or "y" in kwargs:
            from com.sun.star.awt import Point
            pos = shape.getPosition()
            shape.setPosition(Point(kwargs.get("x", pos.X), kwargs.get("y", pos.Y)))
        if "width" in kwargs or "height" in kwargs:
            from com.sun.star.awt import Size
            size = shape.getSize()
            shape.setSize(
                Size(kwargs.get("width", size.Width), kwargs.get("height", size.Height))
            )
        if "text" in kwargs and hasattr(shape, "setString"):
            shape.setString(kwargs["text"])
        if "bg_color" in kwargs:
            color = _parse_color(kwargs["bg_color"])
            if color is not None:
                prop = (
                    "LineColor"
                    if "LineShape" in shape.getShapeType()
                    else "FillColor"
                )
                try:
                    shape.setPropertyValue(prop, color)
                except Exception:
                    pass
        return {"status": "ok", "message": "Shape updated"}


class DeleteShape(ToolBase):
    name = "delete_shape"
    intent = "edit"
    description = (
        "Delete a shape by index. "
        "Works on all document types."
    )
    parameters = {
        "type": "object",
        "properties": {
            "shape_index": {"type": "integer"},
            "draw": {
                "type": "object",
                "description": "Draw/Impress options",
                "properties": {
                    "page_index": {"type": "integer"},
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc options",
                "properties": {
                    "sheet_name": {"type": "string"},
                },
            },
        },
        "required": ["shape_index"],
    }
    doc_types = None  # all document types
    is_mutation = True

    def execute(self, ctx, **kwargs):
        page, _ = _resolve_page(ctx, **kwargs)
        shape = page.getByIndex(kwargs["shape_index"])
        page.remove(shape)
        return {"status": "ok", "message": "Shape deleted"}
