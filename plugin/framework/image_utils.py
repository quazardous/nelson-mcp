# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Image insertion and gallery management for all document types.

This is a stateless library — no services or context needed beyond
the UNO document model and component context.
"""

import os
import shutil
import logging
from pathlib import Path

log = logging.getLogger("nelson.image_utils")

GALLERY_NAME = "nelson_images"


def get_doc_type(model):
    """Return 'writer', 'calc', 'draw', or 'impress' for a document model."""
    TYPE_MAP = {
        "calc": "com.sun.star.sheet.SpreadsheetDocument",
        "draw": "com.sun.star.drawing.DrawingDocument",
        "impress": "com.sun.star.presentation.PresentationDocument",
        "web": "com.sun.star.text.WebDocument",
        "writer": "com.sun.star.text.TextDocument",
    }
    for k, v in TYPE_MAP.items():
        if model.supportsService(v):
            return k
    return "writer"


def insert_image(ctx, model, img_path, width_px, height_px,
                 title="", description="", add_to_gallery=True, add_frame=False):
    """Insert an image into any document type.

    ctx: UNO component context.
    model: document model (XModel).
    width_px, height_px: Size in pixels.
    """
    import uno
    from com.sun.star.text.TextContentAnchorType import AS_CHARACTER, AT_FRAME
    from com.sun.star.awt import Size, Point

    doc_type = get_doc_type(model)

    # 1 inch = 2540 units (1/100th mm). At 96 DPI: 1px ≈ 26.46 units.
    width_units = int(width_px * 26.46)
    height_units = int(height_px * 26.46)

    if doc_type in ("writer", "web"):
        image = model.createInstance("com.sun.star.text.GraphicObject")
        image.GraphicURL = uno.systemPathToFileUrl(img_path)
        image.AnchorType = AS_CHARACTER
        image.Width = width_units
        image.Height = height_units
        image.Title = title
        image.Description = description

        view_cursor = model.CurrentController.ViewCursor

        if add_frame:
            _insert_frame(model, view_cursor, image, width_units, height_units, title)
        else:
            try:
                model.Text.insertTextContent(view_cursor, image, False)
            except Exception:
                view_cursor.jumpToStartOfPage()
                model.Text.insertTextContent(view_cursor, image, False)
    else:
        image = model.createInstance("com.sun.star.drawing.GraphicObjectShape")
        image.GraphicURL = uno.systemPathToFileUrl(img_path)

        ctrllr = model.CurrentController
        if doc_type == "calc":
            draw_page = ctrllr.ActiveSheet.DrawPage
        else:
            draw_page = ctrllr.CurrentPage

        draw_page.add(image)
        image.setSize(Size(width_units, height_units))
        image.Title = title
        image.Description = description

        if doc_type != "calc":
            pos = Point(
                (draw_page.Width - width_units) // 2,
                (draw_page.Height - height_units) // 2
            )
            image.setPosition(pos)

    if add_to_gallery:
        add_image_to_gallery(ctx, img_path, "%s\n\n%s" % (title, description))


def _insert_frame(model, cursor, image, width, height, title):
    """Insert an image inside a text frame."""
    from com.sun.star.text.TextContentAnchorType import AT_FRAME
    from com.sun.star.awt import Size

    text_frame = model.createInstance("com.sun.star.text.TextFrame")
    frame_size = Size()
    frame_size.Height = height + 150
    frame_size.Width = width + 150
    text_frame.setSize(frame_size)
    text_frame.setPropertyValue("AnchorType", AT_FRAME)

    try:
        model.getText().insertTextContent(cursor, text_frame, False)
    except Exception:
        cursor.jumpToStartOfPage()
        model.getText().insertTextContent(cursor, text_frame, False)

    frame_text = text_frame.getText()
    frame_cursor = frame_text.createTextCursor()
    text_frame.insertTextContent(frame_cursor, image, False)
    if title:
        frame_text.insertString(frame_cursor, "\n" + title, False)


def replace_image_in_place(ctx, model, img_path, width_px, height_px,
                           title="", description="", add_to_gallery=True):
    """Replace the currently selected image with a new one.

    Returns True if replacement succeeded, False if no image is selected.
    """
    import uno
    from com.sun.star.text.TextContentAnchorType import AS_CHARACTER
    from com.sun.star.awt import Size

    obj, doc_type = _get_selected_graphic_object(model)
    if obj is None:
        return False

    width_units = int(width_px * 26.46)
    height_units = int(height_px * 26.46)

    try:
        if doc_type in ("writer", "web"):
            anchor = obj.getAnchor()
            if anchor is None:
                return False
            new_image = model.createInstance("com.sun.star.text.GraphicObject")
            new_image.GraphicURL = uno.systemPathToFileUrl(img_path)
            new_image.AnchorType = AS_CHARACTER
            new_image.Width = width_units
            new_image.Height = height_units
            new_image.Title = title
            new_image.Description = description
            model.getText().insertTextContent(anchor, new_image, False)
            model.getText().removeTextContent(obj)
        else:
            ctrllr = model.CurrentController
            draw_page = (ctrllr.ActiveSheet.DrawPage
                         if doc_type == "calc" else ctrllr.CurrentPage)
            pos = obj.getPosition()
            new_image = model.createInstance(
                "com.sun.star.drawing.GraphicObjectShape"
            )
            new_image.GraphicURL = uno.systemPathToFileUrl(img_path)
            new_image.setPosition(pos)
            new_image.setSize(Size(width_units, height_units))
            new_image.Title = title
            new_image.Description = description
            draw_page.add(new_image)
            draw_page.remove(obj)

        if add_to_gallery:
            add_image_to_gallery(ctx, img_path, "%s\n\n%s" % (title, description))
        return True
    except Exception:
        log.debug("replace_image_in_place failed", exc_info=True)
        return False


def get_selected_image_base64(model, ctx=None):
    """Return the base64-encoded PNG data of the selected image, or None."""
    try:
        import base64
        import tempfile
        import uno
        from com.sun.star.beans import PropertyValue

        selection = model.CurrentController.Selection
        if not selection:
            return None
        if hasattr(selection, "getCount") and selection.getCount() > 0:
            obj = selection.getByIndex(0)
        else:
            obj = selection

        graphic = None
        if hasattr(obj, "Graphic"):
            graphic = obj.Graphic
        elif hasattr(obj, "getPropertyValue"):
            try:
                graphic = obj.getPropertyValue("Graphic")
            except Exception:
                return None
        if graphic is None:
            return None

        if ctx is None:
            ctx = uno.getComponentContext()
        gp = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.graphic.GraphicProvider", ctx
        )
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp_url = uno.systemPathToFileUrl(tmp.name)
            props = (
                PropertyValue(Name="URL", Value=tmp_url),
                PropertyValue(Name="MimeType", Value="image/png"),
            )
            gp.storeGraphic(graphic, props)
            with open(tmp.name, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        log.debug("get_selected_image_base64 failed", exc_info=True)
        return None


def add_image_to_gallery(ctx, img_path, title):
    """Copy image to LO gallery and register it."""
    try:
        import uno
        psettings = ctx.getValueByName(
            "/singletons/com.sun.star.util.thePathSettings"
        )
        gallery_dir = (
            Path(uno.fileUrlToSystemPath(psettings.Storage_writable))
            / GALLERY_NAME
        )
        os.makedirs(gallery_dir, exist_ok=True)

        filename = os.path.basename(img_path)
        target_path = gallery_dir / filename
        shutil.copy2(img_path, target_path)

        themes = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.gallery.GalleryThemeProvider", ctx
        )
        if themes.hasByName(GALLERY_NAME):
            theme = themes.getByName(GALLERY_NAME)
        else:
            theme = themes.insertNewByName(GALLERY_NAME)

        theme.insertURLByIndex(
            uno.systemPathToFileUrl(str(target_path)), -1
        )
        theme.update()
    except Exception:
        log.debug("add_image_to_gallery failed", exc_info=True)


def _get_selected_graphic_object(model):
    """Return (graphic_object, doc_type) or (None, None)."""
    try:
        selection = model.CurrentController.Selection
        if not selection:
            return None, None
        if hasattr(selection, "getCount") and selection.getCount() != 1:
            return None, None
        obj = (selection.getByIndex(0) if hasattr(selection, "getByIndex")
               else selection)
        if not (hasattr(obj, "Graphic") or
                (hasattr(obj, "getPropertyValue") and
                 obj.getPropertyValue("Graphic"))):
            return None, None
        return obj, get_doc_type(model)
    except Exception:
        return None, None
