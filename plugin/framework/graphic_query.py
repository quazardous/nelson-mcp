# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cross-document image/graphic query helpers.

Writer uses getGraphicObjects() (named collection of TextGraphicObject).
Calc/Draw/Impress iterate DrawPage shapes filtering GraphicObjectShape.
"""

import logging

log = logging.getLogger("nelson.graphic_query")

_GRAPHIC_SERVICE = "com.sun.star.drawing.GraphicObjectShape"


def _is_graphic_shape(shape):
    """Check if a shape is a graphic (image) object."""
    try:
        return shape.supportsService(_GRAPHIC_SERVICE)
    except Exception:
        return False


def _shape_info(shape, index=None):
    """Extract common info from a DrawPage graphic shape."""
    info = {}
    if index is not None:
        info["shape_index"] = index
    try:
        info["name"] = shape.Name
    except Exception:
        info["name"] = ""
    try:
        size = shape.getSize()
        info["width_mm"] = size.Width / 100.0
        info["height_mm"] = size.Height / 100.0
        info["width_100mm"] = size.Width
        info["height_100mm"] = size.Height
    except Exception:
        pass
    try:
        pos = shape.getPosition()
        info["x"] = pos.X
        info["y"] = pos.Y
    except Exception:
        pass
    for prop in ("Title", "Description"):
        try:
            info[prop.lower()] = shape.getPropertyValue(prop)
        except Exception:
            info[prop.lower()] = ""
    try:
        url = shape.getPropertyValue("GraphicURL")
        info["graphic_url"] = url if isinstance(url, str) else ""
    except Exception:
        info["graphic_url"] = ""
    return info


def list_images_writer(doc, doc_svc=None):
    """List images in a Writer document via getGraphicObjects()."""
    if not hasattr(doc, "getGraphicObjects"):
        return []
    graphics = doc.getGraphicObjects()
    para_ranges = None
    text_obj = None
    if doc_svc:
        try:
            para_ranges = doc_svc.get_paragraph_ranges(doc)
            text_obj = doc.getText()
        except Exception:
            pass

    images = []
    for name in graphics.getElementNames():
        try:
            graphic = graphics.getByName(name)
            size = graphic.getPropertyValue("Size")
            entry = {
                "name": name,
                "width_mm": size.Width / 100.0,
                "height_mm": size.Height / 100.0,
                "width_100mm": size.Width,
                "height_100mm": size.Height,
            }
            for prop in ("Title", "Description"):
                try:
                    entry[prop.lower()] = graphic.getPropertyValue(prop)
                except Exception:
                    entry[prop.lower()] = ""

            # Paragraph index
            if para_ranges and text_obj:
                try:
                    anchor = graphic.getAnchor()
                    entry["paragraph_index"] = doc_svc.find_paragraph_for_range(
                        anchor, para_ranges, text_obj
                    )
                except Exception:
                    entry["paragraph_index"] = -1

            # Page number
            try:
                anchor = graphic.getAnchor()
                vc = doc.getCurrentController().getViewCursor()
                vc.gotoRange(anchor.getStart(), False)
                entry["page"] = vc.getPage()
            except Exception:
                pass

            images.append(entry)
        except Exception as e:
            log.debug("list_images_writer: skip '%s': %s", name, e)
    return images


def list_images_drawpage(page, page_label=None):
    """List graphic shapes on a single DrawPage."""
    images = []
    for i in range(page.getCount()):
        shape = page.getByIndex(i)
        if not _is_graphic_shape(shape):
            continue
        info = _shape_info(shape, index=i)
        if page_label is not None:
            info["page"] = page_label
        images.append(info)
    return images


def get_image_writer(doc, image_name):
    """Get a Writer graphic object by name, or None."""
    if not hasattr(doc, "getGraphicObjects"):
        return None
    graphics = doc.getGraphicObjects()
    if not graphics.hasByName(image_name):
        return None
    return graphics.getByName(image_name)


def find_image_on_page(page, image_name=None, shape_index=None):
    """Find a graphic shape on a DrawPage by name or shape_index.

    Returns (shape, index) or (None, -1).
    """
    if shape_index is not None:
        if 0 <= shape_index < page.getCount():
            shape = page.getByIndex(shape_index)
            if _is_graphic_shape(shape):
                return shape, shape_index
        return None, -1

    if image_name:
        for i in range(page.getCount()):
            shape = page.getByIndex(i)
            if not _is_graphic_shape(shape):
                continue
            try:
                if shape.Name == image_name:
                    return shape, i
            except Exception:
                pass
    return None, -1


def delete_image_drawpage(page, image_name=None, shape_index=None):
    """Delete a graphic shape from a DrawPage by name or index. Returns True on success."""
    shape, _ = find_image_on_page(page, image_name=image_name, shape_index=shape_index)
    if shape is None:
        return False
    page.remove(shape)
    return True
