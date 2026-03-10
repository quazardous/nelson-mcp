# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bridge for Draw/Impress documents and drawing layer access."""

import logging

log = logging.getLogger("nelson.draw")


def get_draw_page(ctx, page_index=None, sheet_name=None):
    """Resolve a DrawPage from any document type.

    - Writer: single draw page via ``getDrawPage()``
    - Calc: draw page per sheet via ``sheet.DrawPage``
    - Draw/Impress: pages via ``getDrawPages()``

    Returns (page, doc_type) or raises RuntimeError.
    """
    doc = ctx.doc
    doc_type = ctx.doc_type

    if doc_type == "writer":
        if not hasattr(doc, "getDrawPage"):
            raise RuntimeError("Writer document has no drawing layer.")
        return doc.getDrawPage(), doc_type

    if doc_type == "calc":
        controller = doc.getCurrentController()
        if sheet_name:
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                raise RuntimeError("Sheet not found: %s" % sheet_name)
            sheet = sheets.getByName(sheet_name)
        else:
            sheet = controller.ActiveSheet
        return sheet.DrawPage, doc_type

    # draw / impress
    if not hasattr(doc, "getDrawPages"):
        raise RuntimeError("Document has no draw pages.")
    pages = doc.getDrawPages()
    if page_index is not None:
        if page_index < 0 or page_index >= pages.getCount():
            raise RuntimeError("Page index %d out of range." % page_index)
        return pages.getByIndex(page_index), doc_type

    controller = doc.getCurrentController()
    if hasattr(controller, "getCurrentPage"):
        return controller.getCurrentPage(), doc_type
    if pages.getCount() > 0:
        return pages.getByIndex(0), doc_type
    raise RuntimeError("No pages in document.")


class DrawBridge:
    def __init__(self, doc):
        self.doc = doc
        if not hasattr(doc, "getDrawPages"):
            raise RuntimeError("Not a Draw/Impress document.")

    def get_pages(self):
        return self.doc.getDrawPages()

    def get_active_page(self):
        controller = self.doc.getCurrentController()
        if hasattr(controller, "getCurrentPage"):
            return controller.getCurrentPage()
        pages = self.get_pages()
        if pages.getCount() > 0:
            return pages.getByIndex(0)
        return None

    def create_shape(self, shape_type, x, y, width, height, page=None):
        if page is None:
            page = self.get_active_page()
        shape = self.doc.createInstance(shape_type)
        page.add(shape)
        from com.sun.star.awt import Size, Point
        shape.setSize(Size(width, height))
        shape.setPosition(Point(x, y))
        return shape

    def create_slide(self, index=None):
        pages = self.get_pages()
        if index is None:
            index = pages.getCount()
        return pages.insertNewByIndex(index)

    def delete_slide(self, index):
        pages = self.get_pages()
        page = pages.getByIndex(index)
        pages.remove(page)
