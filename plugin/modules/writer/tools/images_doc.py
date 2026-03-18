# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Image management tools — unified across all document types.

Writer uses getGraphicObjects() (named TextGraphicObject collection).
Calc/Draw/Impress use DrawPage shapes (GraphicObjectShape).
Writer-specific tools (set_image_properties, replace_image) remain Writer-only.
"""

import hashlib
import logging
import os
import tempfile

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.images")

# Persistent cache directory for downloaded images.
_IMAGE_CACHE_DIR = os.path.join(tempfile.gettempdir(), "nelson_images")

# Default image width when none specified (mm)
_DEFAULT_WIDTH_MM = 120
# Default max height to avoid portrait photos eating a full page (mm)
_DEFAULT_MAX_HEIGHT_MM = 160


def _read_image_dimensions(path):
    """Read pixel dimensions from image header. Returns (w, h) or (0, 0)."""
    import struct
    try:
        with open(path, "rb") as f:
            header = f.read(32)
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", header[16:24])
        if header[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", header[6:10])
        if header[:2] == b"\xff\xd8":
            return _read_jpeg_dims(path)
    except Exception:
        pass
    return (0, 0)


def _read_jpeg_dims(path):
    """Read JPEG dimensions from SOF marker."""
    import struct
    try:
        with open(path, "rb") as f:
            f.read(2)
            while True:
                marker = f.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    break
                mtype = marker[1]
                if mtype in (0xC0, 0xC1, 0xC2):
                    f.read(2)
                    data = f.read(5)
                    if len(data) >= 5:
                        h, w = struct.unpack(">HH", data[1:5])
                        return (w, h)
                    break
                elif mtype in (0xD9, 0xDA):
                    break
                else:
                    seg_len = struct.unpack(">H", f.read(2))[0]
                    f.seek(seg_len - 2, 1)
    except Exception:
        pass
    return (0, 0)


def _basename_from_url(file_url):
    """Extract filename without extension from a file:// URL."""
    try:
        name = file_url.rsplit("/", 1)[-1]
        name = name.rsplit(".", 1)[0] if "." in name else name
        # URL-decode
        import urllib.parse
        return urllib.parse.unquote(name)
    except Exception:
        return ""


def _fit_dimensions(image_path, width_mm, height_mm, max_height_mm=None):
    """Compute final dimensions preserving aspect ratio.

    Rules:
    - If both given: fit within the box, preserving ratio.
    - If only width: compute height from ratio.
    - If only height: compute width from ratio.
    - If neither: use _DEFAULT_WIDTH_MM and compute height.
    - If image dimensions unreadable: fallback to given or defaults.
    """
    ext = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else ""
    px_w, px_h = _read_image_dimensions(image_path)

    if px_w <= 0 or px_h <= 0:
        # Can't read dimensions — use given or defaults
        return (width_mm or _DEFAULT_WIDTH_MM, height_mm or _DEFAULT_WIDTH_MM)

    ratio = px_w / px_h

    if width_mm and height_mm:
        # Fit within box, preserve ratio
        box_ratio = width_mm / height_mm
        if ratio > box_ratio:
            return (width_mm, round(width_mm / ratio))
        else:
            return (round(height_mm * ratio), height_mm)
    elif width_mm:
        h = round(width_mm / ratio)
        max_h = max_height_mm or _DEFAULT_MAX_HEIGHT_MM
        if h > max_h:
            return (round(max_h * ratio), max_h)
        return (width_mm, h)
    elif height_mm:
        return (round(height_mm * ratio), height_mm)
    else:
        h = round(_DEFAULT_WIDTH_MM / ratio)
        max_h = max_height_mm or _DEFAULT_MAX_HEIGHT_MM
        if h > max_h:
            return (round(max_h * ratio), max_h)
        return (_DEFAULT_WIDTH_MM, h)


# ------------------------------------------------------------------
# ListImages — all doc types
# ------------------------------------------------------------------

class ListImages(ToolBase):
    """List all images/graphic objects in the document."""

    name = "list_images"
    intent = "media"
    description = (
        "List all images/graphic objects in the document with name, "
        "dimensions, title, and description. "
        "For Calc, lists images on a sheet's drawing layer. "
        "For Draw/Impress, lists images on a page."
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
        from plugin.framework.graphic_query import (
            list_images_writer, list_images_drawpage,
        )
        doc = ctx.doc

        if ctx.doc_type == "writer":
            doc_svc = ctx.services.document
            images = list_images_writer(doc, doc_svc=doc_svc)
        else:
            from plugin.modules.draw.bridge import get_draw_page
            page, _ = get_draw_page(
                ctx,
                page_index=kwargs.get("page_index"),
                sheet_name=kwargs.get("sheet_name"),
            )
            page_label = kwargs.get("sheet_name") or kwargs.get("page_index")
            images = list_images_drawpage(page, page_label=page_label)

        return {"status": "ok", "images": images, "count": len(images)}


# ------------------------------------------------------------------
# GetImageInfo — all doc types
# ------------------------------------------------------------------

class GetImageInfo(ToolBase):
    """Get detailed info about a specific image."""

    name = "get_image_info"
    intent = "media"
    description = (
        "Get detailed info about a specific image: URL, dimensions, "
        "title, description. "
        "In Writer, looks up by image_name and returns anchor type, orientation, paragraph index. "
        "In Calc/Draw/Impress, looks up by image_name or shape_index and returns position (x, y)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_name": {
                "type": "string",
                "description": "Name of the image (from list_images). Required for Writer.",
            },
            "shape_index": {
                "type": "integer",
                "description": "Shape index on the page (from list_images). For Calc/Draw/Impress only.",
            },
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
        image_name = kwargs.get("image_name", "")
        shape_index = kwargs.get("shape_index")

        doc = ctx.doc

        if ctx.doc_type == "writer":
            if not image_name:
                return {"status": "error", "message": "image_name is required for Writer."}
            return self._writer_info(ctx, image_name)

        if not image_name and shape_index is None:
            return {"status": "error", "message": "image_name or shape_index is required."}

        # Calc / Draw / Impress — find shape on draw page
        from plugin.modules.draw.bridge import get_draw_page
        from plugin.framework.graphic_query import find_image_on_page, _shape_info
        page, _ = get_draw_page(
            ctx,
            page_index=kwargs.get("page_index"),
            sheet_name=kwargs.get("sheet_name"),
        )
        shape, idx = find_image_on_page(
            page, image_name=image_name or None, shape_index=shape_index,
        )
        if shape is None:
            return {"status": "error", "message": "Image not found."}
        info = _shape_info(shape, index=idx)
        info["status"] = "ok"
        return info

    def _writer_info(self, ctx, image_name):
        """Writer-specific detailed image info."""
        doc = ctx.doc
        graphics = doc.getGraphicObjects()
        if not graphics.hasByName(image_name):
            available = list(graphics.getElementNames())
            return {
                "status": "error",
                "message": "Image '%s' not found." % image_name,
                "available": available,
            }

        graphic = graphics.getByName(image_name)
        size = graphic.getPropertyValue("Size")

        graphic_url = ""
        try:
            graphic_url = graphic.getPropertyValue("GraphicURL")
        except Exception:
            pass

        anchor_type = None
        try:
            anchor_type = int(graphic.getPropertyValue("AnchorType").value)
        except Exception:
            try:
                anchor_type = int(graphic.getPropertyValue("AnchorType"))
            except Exception:
                pass

        hori_orient = None
        vert_orient = None
        try:
            hori_orient = int(graphic.getPropertyValue("HoriOrient"))
        except Exception:
            pass
        try:
            vert_orient = int(graphic.getPropertyValue("VertOrient"))
        except Exception:
            pass

        title = ""
        description = ""
        try:
            title = graphic.getPropertyValue("Title")
        except Exception:
            pass
        try:
            description = graphic.getPropertyValue("Description")
        except Exception:
            pass

        paragraph_index = -1
        try:
            anchor = graphic.getAnchor()
            doc_svc = ctx.services.document
            para_ranges = doc_svc.get_paragraph_ranges(doc)
            text_obj = doc.getText()
            paragraph_index = doc_svc.find_paragraph_for_range(
                anchor, para_ranges, text_obj
            )
        except Exception:
            pass

        return {
            "status": "ok",
            "image_name": image_name,
            "graphic_url": graphic_url,
            "width_mm": size.Width / 100.0,
            "height_mm": size.Height / 100.0,
            "width_100mm": size.Width,
            "height_100mm": size.Height,
            "anchor_type": anchor_type,
            "hori_orient": hori_orient,
            "vert_orient": vert_orient,
            "title": title,
            "description": description,
            "paragraph_index": paragraph_index,
        }


# ------------------------------------------------------------------
# SetImageProperties — Writer-only
# ------------------------------------------------------------------

class SetImageProperties(ToolBase):
    """Resize, reposition, crop, or update caption/alt-text for an image."""

    name = "set_image_properties"
    intent = "media"
    description = (
        "Resize, reposition, crop, or update caption/alt-text for a Writer image. "
        "Writer-only: uses anchor types, orientation, and frame properties."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_name": {
                "type": "string",
                "description": "Name of the image (from list_images).",
            },
            "width_mm": {
                "type": "number",
                "description": "New width in millimetres.",
            },
            "height_mm": {
                "type": "number",
                "description": "New height in millimetres.",
            },
            "title": {
                "type": "string",
                "description": "Image title (tooltip text).",
            },
            "description": {
                "type": "string",
                "description": "Image alternative text (alt-text).",
            },
            "anchor_type": {
                "type": "integer",
                "description": (
                    "Anchor type: 0=AT_PARAGRAPH, 1=AS_CHARACTER, "
                    "2=AT_PAGE, 3=AT_FRAME, 4=AT_CHARACTER."
                ),
            },
            "hori_orient": {
                "type": "integer",
                "description": "Horizontal orientation constant.",
            },
            "vert_orient": {
                "type": "integer",
                "description": "Vertical orientation constant.",
            },
        },
        "required": ["image_name"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        image_name = kwargs.get("image_name", "")
        if not image_name:
            return {"status": "error", "message": "image_name is required."}

        doc = ctx.doc
        graphics = doc.getGraphicObjects()
        if not graphics.hasByName(image_name):
            return {
                "status": "error",
                "message": "Image '%s' not found." % image_name,
            }

        graphic = graphics.getByName(image_name)
        updated = []

        width_mm = kwargs.get("width_mm")
        height_mm = kwargs.get("height_mm")
        if width_mm is not None or height_mm is not None:
            from com.sun.star.awt import Size
            current = graphic.getPropertyValue("Size")
            new_size = Size()
            new_size.Width = int(width_mm * 100) if width_mm is not None else current.Width
            new_size.Height = int(height_mm * 100) if height_mm is not None else current.Height
            graphic.setPropertyValue("Size", new_size)
            updated.append("size")

        title = kwargs.get("title")
        if title is not None:
            graphic.setPropertyValue("Title", title)
            updated.append("title")

        description = kwargs.get("description")
        if description is not None:
            graphic.setPropertyValue("Description", description)
            updated.append("description")

        anchor_type = kwargs.get("anchor_type")
        if anchor_type is not None:
            from com.sun.star.text.TextContentAnchorType import (
                AT_PARAGRAPH, AS_CHARACTER, AT_PAGE, AT_FRAME, AT_CHARACTER,
            )
            anchor_map = {
                0: AT_PARAGRAPH,
                1: AS_CHARACTER,
                2: AT_PAGE,
                3: AT_FRAME,
                4: AT_CHARACTER,
            }
            if anchor_type in anchor_map:
                graphic.setPropertyValue("AnchorType", anchor_map[anchor_type])
                updated.append("anchor_type")

        hori_orient = kwargs.get("hori_orient")
        if hori_orient is not None:
            graphic.setPropertyValue("HoriOrient", hori_orient)
            updated.append("hori_orient")

        vert_orient = kwargs.get("vert_orient")
        if vert_orient is not None:
            graphic.setPropertyValue("VertOrient", vert_orient)
            updated.append("vert_orient")

        return {
            "status": "ok",
            "image_name": image_name,
            "updated": updated,
        }


# ------------------------------------------------------------------
# DownloadImage — all doc types
# ------------------------------------------------------------------

class DownloadImage(ToolBase):
    """Download an image from URL to local cache."""

    name = "download_image"
    intent = "media"
    description = (
        "Download an image from URL to local cache. Returns local path "
        "for insert_image/replace_image."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL of the image to download.",
            },
            "verify_ssl": {
                "type": "boolean",
                "description": "Verify SSL certificates (default: false).",
            },
            "force": {
                "type": "boolean",
                "description": "Force re-download even if cached (default: false).",
            },
        },
        "required": ["url"],
    }
    doc_types = None  # no UNO dependency, works for all types

    def execute(self, ctx, **kwargs):
        url = kwargs.get("url", "")
        if not url:
            return {"status": "error", "message": "url is required."}

        verify_ssl = kwargs.get("verify_ssl", False)
        force = kwargs.get("force", False)

        try:
            local_path = _download_image_to_cache(url, verify_ssl=verify_ssl, force=force)
            return {
                "status": "ok",
                "local_path": local_path,
                "url": url,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ------------------------------------------------------------------
# InsertImage — all doc types
# ------------------------------------------------------------------

class InsertImage(ToolBase):
    """Insert an image from local path or URL into any document type."""

    name = "insert_image"
    intent = "media"
    description = (
        "Insert an image from local path or URL into the document. "
        "URLs are auto-downloaded first. "
        "In Writer, inserts as a text graphic object at a locator or paragraph. "
        "In Calc, inserts on the active sheet's drawing layer. "
        "In Draw/Impress, inserts centered on the current or specified page."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Local file path or URL of the image to insert.",
            },
            "width_mm": {
                "type": "integer",
                "description": "Width in millimetres (default: 120). Aspect ratio is always preserved.",
            },
            "height_mm": {
                "type": "integer",
                "description": "Height in millimetres. Aspect ratio is always preserved.",
            },
            "max_height_mm": {
                "type": "integer",
                "description": (
                    "Maximum height in mm for portrait images (default: 160). "
                    "Prevents tall images from filling an entire page."
                ),
            },
            "caption": {
                "type": "boolean",
                "description": (
                    "Add a caption below the image (default: true in Writer). "
                    "Caption text = description > title > filename."
                ),
            },
            "title": {
                "type": "string",
                "description": "Image title (tooltip text).",
            },
            "description": {
                "type": "string",
                "description": "Image alt-text / description.",
            },
            "writer": {
                "type": "object",
                "description": "Writer-specific insertion options",
                "properties": {
                    "locator": {
                        "type": "string",
                        "description": (
                            "Unified locator for insertion point "
                            "(e.g. 'bookmark:NAME', 'heading_text:Title')."
                        ),
                    },
                    "paragraph_index": {
                        "type": "integer",
                        "description": "Paragraph index for insertion point.",
                    },
                },
            },
            "draw": {
                "type": "object",
                "description": "Draw/Impress-specific options",
                "properties": {
                    "page_index": {
                        "type": "integer",
                        "description": "0-based page index (active page if omitted).",
                    },
                    "x": {
                        "type": "integer",
                        "description": "X position in 1/100 mm (centered if omitted).",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y position in 1/100 mm (centered if omitted).",
                    },
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc-specific options",
                "properties": {
                    "sheet_name": {
                        "type": "string",
                        "description": "Sheet name (active sheet if omitted).",
                    },
                },
            },
        },
        "required": ["image_path"],
    }
    doc_types = None  # all document types
    is_mutation = True

    def execute(self, ctx, **kwargs):
        import uno

        image_path = kwargs.get("image_path", "")
        if not image_path:
            return {"status": "error", "message": "image_path is required."}

        width_mm = kwargs.get("width_mm")
        height_mm = kwargs.get("height_mm")
        title = kwargs.get("title", "")
        description = kwargs.get("description", "")

        # Auto-download URLs
        if image_path.startswith("http://") or image_path.startswith("https://"):
            try:
                image_path = _download_image_to_cache(image_path)
            except Exception as e:
                return {"status": "error", "message": "Download failed: %s" % e}

        if not os.path.isfile(image_path):
            return {"status": "error", "message": "File not found: %s" % image_path}

        # Preserve aspect ratio
        max_height_mm = kwargs.get("max_height_mm")
        width_mm, height_mm = _fit_dimensions(
            image_path, width_mm, height_mm, max_height_mm)

        file_url = uno.systemPathToFileUrl(os.path.abspath(image_path))
        width_units = int(width_mm) * 100
        height_units = int(height_mm) * 100

        doc = ctx.doc
        # Remove shared params already extracted — avoid double-passing
        extra = {k: v for k, v in kwargs.items()
                 if k not in ("image_path", "width_mm", "height_mm", "title", "description")}

        if ctx.doc_type == "writer":
            return self._insert_writer(ctx, file_url, width_units, height_units,
                                       title, description, **extra)

        # Calc / Draw / Impress — shape on DrawPage
        try:
            return self._insert_drawpage(ctx, file_url, width_units, height_units,
                                         title, description, **extra)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _insert_writer(self, ctx, file_url, width, height, title, desc, **kwargs):
        """Insert image in Writer inside a TextFrame with caption.

        The TextFrame wraps the image + an optional caption line below.
        This matches Writer's native "Insert > Caption" behaviour.
        Pass caption=False for a standalone image without frame.
        """
        from com.sun.star.awt import Size
        doc = ctx.doc
        doc_text = doc.getText()
        doc_svc = ctx.services.document

        # Resolve insertion point
        locator = kwargs.get("locator")
        paragraph_index = kwargs.get("paragraph_index")
        if locator is not None and paragraph_index is None:
            resolved = doc_svc.resolve_locator(doc, locator)
            paragraph_index = resolved.get("para_index")

        if paragraph_index is not None:
            target, _ = doc_svc.find_paragraph_element(doc, paragraph_index)
            if target is None:
                return {
                    "status": "error",
                    "message": "Paragraph %d not found." % paragraph_index,
                }
            cursor = doc_text.createTextCursorByRange(target.getEnd())
        else:
            cursor = doc_text.createTextCursor()
            cursor.gotoEnd(False)

        add_caption = kwargs.get("caption", True)
        caption_text = desc or title or _basename_from_url(file_url)

        if add_caption and caption_text:
            result = self._insert_with_frame(
                doc, doc_text, cursor, file_url, width, height,
                title, desc, caption_text)
        else:
            result = self._insert_standalone(
                doc, doc_text, cursor, file_url, width, height,
                title, desc)
        if paragraph_index is not None:
            result["paragraph_index"] = paragraph_index
        return result

    def _insert_with_frame(self, doc, doc_text, cursor,
                           file_url, width, height,
                           title, desc, caption_text):
        """Insert image inside a TextFrame with caption below.

        Follows the same pattern as mcp-libre: frame size = image size,
        frame auto-grows to fit caption text.
        """
        from com.sun.star.awt import Size

        frame = doc.createInstance("com.sun.star.text.TextFrame")
        frame.setPropertyValue("Size", Size(width, height))
        frame.setPropertyValue("AnchorType", 4)   # AT_CHARACTER
        frame.setPropertyValue("HoriOrient", 0)    # NONE
        frame.setPropertyValue("VertOrient", 0)    # NONE
        frame.setPropertyValue("SizeType", 2)      # FIX
        frame.setPropertyValue("WidthType", 1)     # FIX

        # Margins matching reference (top=0, left=0, right/bottom ~5mm)
        frame.setPropertyValue("TopMargin", 0)
        frame.setPropertyValue("BottomMargin", 499)
        frame.setPropertyValue("LeftMargin", 0)
        frame.setPropertyValue("RightMargin", 499)

        # Zero borders and padding
        from com.sun.star.table import BorderLine2
        empty_border = BorderLine2()
        for side in ("TopBorder", "BottomBorder", "LeftBorder", "RightBorder"):
            try:
                frame.setPropertyValue(side, empty_border)
            except Exception:
                pass
        for dist in ("TopBorderDistance", "BottomBorderDistance",
                     "LeftBorderDistance", "RightBorderDistance",
                     "BorderDistance"):
            try:
                frame.setPropertyValue(dist, 0)
            except Exception:
                pass

        doc_text.insertTextContent(cursor, frame, False)

        # Insert image inside the frame (AS_CHARACTER avoids empty line)
        graphic = doc.createInstance("com.sun.star.text.TextGraphicObject")
        graphic.setPropertyValue("GraphicURL", file_url)
        graphic.setPropertyValue("Size", Size(width, height))
        graphic.setPropertyValue("AnchorType", 1)  # AS_CHARACTER
        if title:
            graphic.setPropertyValue("Title", title)
        if desc:
            graphic.setPropertyValue("Description", desc)

        frame_text = frame.getText()
        frame_cursor = frame_text.createTextCursor()
        # Minimize the initial empty paragraph (CharHeight 1)
        # so it doesn't create visible space above the image
        frame_cursor.setPropertyValue("CharHeight", 1)
        frame_text.insertTextContent(frame_cursor, graphic, False)

        # Add caption after the image
        cap_cursor = frame_text.createTextCursorByRange(frame_text.getEnd())
        frame_text.insertControlCharacter(cap_cursor, 0, False)
        cap_cursor = frame_text.createTextCursorByRange(frame_text.getEnd())
        cap_cursor.setPropertyValue("CharHeight", 10)
        frame_text.insertString(cap_cursor, caption_text, False)

        return {
            "status": "ok",
            "frame_name": frame.getName(),
            "image_name": graphic.getName(),
            "width_mm": width // 100,
            "height_mm": height // 100,
            "caption": caption_text,
        }

    def _insert_standalone(self, doc, doc_text, cursor,
                           file_url, width, height, title, desc):
        """Insert a standalone image without frame."""
        from com.sun.star.awt import Size

        graphic = doc.createInstance("com.sun.star.text.TextGraphicObject")
        graphic.setPropertyValue("GraphicURL", file_url)
        graphic.setPropertyValue("Size", Size(width, height))
        graphic.setPropertyValue("AnchorType", 4)  # AT_CHARACTER
        if title:
            graphic.setPropertyValue("Title", title)
        if desc:
            graphic.setPropertyValue("Description", desc)

        doc_text.insertTextContent(cursor, graphic, False)

        return {
            "status": "ok",
            "image_name": graphic.getName(),
            "width_mm": width // 100,
            "height_mm": height // 100,
        }

    def _insert_drawpage(self, ctx, file_url, width, height, title, desc, **kwargs):
        """Insert image as shape on DrawPage (Calc/Draw/Impress)."""
        from com.sun.star.awt import Size, Point
        from plugin.modules.draw.bridge import get_draw_page

        page, _ = get_draw_page(
            ctx,
            page_index=kwargs.get("page_index"),
            sheet_name=kwargs.get("sheet_name"),
        )
        doc = ctx.doc

        image = doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
        image.GraphicURL = file_url
        page.add(image)
        image.setSize(Size(width, height))

        # Position: explicit or centered
        x = kwargs.get("x")
        y = kwargs.get("y")
        if x is not None and y is not None:
            image.setPosition(Point(x, y))
        elif ctx.doc_type != "calc":
            # Center on page for Draw/Impress
            try:
                image.setPosition(Point(
                    (page.Width - width) // 2,
                    (page.Height - height) // 2,
                ))
            except Exception:
                pass

        if title:
            image.Title = title
        if desc:
            image.Description = desc

        return {
            "status": "ok",
            "image_name": image.Name,
            "width_mm": width // 100,
            "height_mm": height // 100,
        }


# ------------------------------------------------------------------
# DeleteImage — all doc types
# ------------------------------------------------------------------

class DeleteImage(ToolBase):
    """Delete an image from the document."""

    name = "delete_image"
    intent = "media"
    description = (
        "Delete an image from the document. "
        "In Writer, removes by image_name. "
        "In Calc/Draw/Impress, removes by image_name or shape_index."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_name": {
                "type": "string",
                "description": "Name of the image to delete. Required for Writer.",
            },
            "shape_index": {
                "type": "integer",
                "description": "Shape index on the page (from list_images). For Calc/Draw/Impress only.",
            },
            "draw": {
                "type": "object",
                "description": "Draw/Impress options",
                "properties": {
                    "page_index": {
                        "type": "integer",
                        "description": "0-based page index (active page if omitted).",
                    },
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc options",
                "properties": {
                    "sheet_name": {
                        "type": "string",
                        "description": "Sheet name (active sheet if omitted).",
                    },
                },
            },
        },
        "required": [],
    }
    doc_types = None  # all document types
    is_mutation = True

    def execute(self, ctx, **kwargs):
        image_name = kwargs.get("image_name", "")
        shape_index = kwargs.get("shape_index")

        if ctx.doc_type == "writer":
            if not image_name:
                return {"status": "error", "message": "image_name is required for Writer."}
            return self._delete_writer(ctx, image_name)

        if not image_name and shape_index is None:
            return {"status": "error", "message": "image_name or shape_index is required."}

        # Calc / Draw / Impress
        from plugin.modules.draw.bridge import get_draw_page
        from plugin.framework.graphic_query import delete_image_drawpage
        page, _ = get_draw_page(
            ctx,
            page_index=kwargs.get("page_index"),
            sheet_name=kwargs.get("sheet_name"),
        )
        if delete_image_drawpage(page, image_name=image_name or None, shape_index=shape_index):
            return {"status": "ok", "deleted": image_name or ("shape_index:%d" % shape_index)}
        return {"status": "error", "message": "Image not found."}

    def _delete_writer(self, ctx, image_name):
        """Delete image in Writer via removeTextContent()."""
        doc = ctx.doc
        graphics = doc.getGraphicObjects()
        if not graphics.hasByName(image_name):
            available = list(graphics.getElementNames())
            return {
                "status": "error",
                "message": "Image '%s' not found." % image_name,
                "available": available,
            }
        graphic = graphics.getByName(image_name)
        try:
            anchor = graphic.getAnchor()
            text = anchor.getText()
            text.removeTextContent(graphic)
        except Exception as e:
            return {"status": "error", "message": "Failed to delete: %s" % e}
        return {"status": "ok", "deleted": image_name}


# ------------------------------------------------------------------
# ReplaceImage — Writer-only
# ------------------------------------------------------------------

class ReplaceImage(ToolBase):
    """Replace an image's source file keeping position and frame."""

    name = "replace_image"
    intent = "media"
    description = (
        "Replace a Writer image's source file keeping position and frame. "
        "Writer-only: preserves TextFrame anchor position."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_name": {
                "type": "string",
                "description": "Name of the image to replace (from list_images).",
            },
            "new_image_path": {
                "type": "string",
                "description": "Local file path or URL of the replacement image.",
            },
            "width_mm": {
                "type": "number",
                "description": "Optionally update width in millimetres.",
            },
            "height_mm": {
                "type": "number",
                "description": "Optionally update height in millimetres.",
            },
        },
        "required": ["image_name", "new_image_path"],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        import uno

        image_name = kwargs.get("image_name", "")
        new_image_path = kwargs.get("new_image_path", "")
        if not image_name:
            return {"status": "error", "message": "image_name is required."}
        if not new_image_path:
            return {"status": "error", "message": "new_image_path is required."}

        doc = ctx.doc
        graphics = doc.getGraphicObjects()
        if not graphics.hasByName(image_name):
            available = list(graphics.getElementNames())
            return {
                "status": "error",
                "message": "Image '%s' not found." % image_name,
                "available": available,
            }

        # Auto-download URLs
        if new_image_path.startswith("http://") or new_image_path.startswith("https://"):
            try:
                new_image_path = _download_image_to_cache(new_image_path)
            except Exception as e:
                return {"status": "error", "message": "Download failed: %s" % e}

        if not os.path.isfile(new_image_path):
            return {
                "status": "error",
                "message": "File not found: %s" % new_image_path,
            }

        file_url = uno.systemPathToFileUrl(os.path.abspath(new_image_path))

        graphic = graphics.getByName(image_name)

        try:
            graphic.setPropertyValue("GraphicURL", file_url)

            width_mm = kwargs.get("width_mm")
            height_mm = kwargs.get("height_mm")
            if width_mm is not None or height_mm is not None:
                from com.sun.star.awt import Size
                current = graphic.getPropertyValue("Size")
                new_size = Size()
                new_size.Width = int(width_mm * 100) if width_mm is not None else current.Width
                new_size.Height = int(height_mm * 100) if height_mm is not None else current.Height
                graphic.setPropertyValue("Size", new_size)

            return {
                "status": "ok",
                "image_name": image_name,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _download_image_to_cache(url, verify_ssl=False, force=False):
    """Download an image URL to the local cache directory.

    Returns the local file path. Uses a URL-based hash for caching.
    """
    import urllib.request
    import ssl

    os.makedirs(_IMAGE_CACHE_DIR, exist_ok=True)

    # Derive a stable filename from the URL
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    # Try to preserve the file extension
    ext = ""
    url_path = url.split("?")[0]
    if "." in url_path.split("/")[-1]:
        ext = "." + url_path.split("/")[-1].rsplit(".", 1)[-1]
        ext = ext[:6].lower()
        if not ext.replace(".", "").isalnum():
            ext = ""
    if not ext:
        ext = ".png"

    local_path = os.path.join(_IMAGE_CACHE_DIR, url_hash + ext)

    if not force and os.path.isfile(local_path):
        log.debug("download_image: cache hit %s -> %s", url, local_path)
        return local_path

    log.info("download_image: downloading %s -> %s", url, local_path)

    if verify_ssl:
        context = None
    else:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    request = urllib.request.Request(url)
    request.add_header("User-Agent", "Nelson/1.0")

    with urllib.request.urlopen(request, context=context) as response:
        data = response.read()

    with open(local_path, "wb") as f:
        f.write(data)

    return local_path
