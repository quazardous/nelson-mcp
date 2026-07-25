# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Structural tools: section_list, nav_goto_page, nav_page_objects, refresh_indexes,
section_read, bookmark_resolve, update_fields, nav_resolve."""

from plugin.framework.tool_base import ToolBase


class ListSections(ToolBase):
    name = "section_list"
    aliases = ["list_sections"]
    intent = "navigate"
    description = "List all named sections in the document."
    parameters = {"type": "object", "properties": {}, "required": []}
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        if not hasattr(doc, "getTextSections"):
            return {"status": "ok", "sections": [], "count": 0}
        try:
            supplier = doc.getTextSections()
            names = supplier.getElementNames()
            sections = []
            for name in names:
                section = supplier.getByName(name)
                sections.append({
                    "name": name,
                    "is_visible": getattr(section, "IsVisible", True),
                    "is_protected": getattr(section, "IsProtected", False),
                })
            return {"status": "ok", "sections": sections, "count": len(sections)}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class GotoPage(ToolBase):
    name = "nav_goto_page"
    aliases = ["goto_page"]
    intent = "navigate"
    description = (
        "Navigate the view cursor to a specific page. By default also returns the "
        "page topology (images, tables, text frames on that page) so a follow-up "
        "nav_page_objects call is not needed. Pass topology=false to skip it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "Page number to navigate to"},
            "topology": {
                "type": "boolean",
                "description": (
                    "Return the objects on the page (images, tables, frames). "
                    "Default: true."
                ),
            },
        },
        "required": ["page"],
    }
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        try:
            doc = ctx.doc
            controller = doc.getCurrentController()
            vc = controller.getViewCursor()
            page = kwargs["page"]
            vc.jumpToPage(page)
            actual_page = vc.getPage()

            if not kwargs.get("topology", True):
                return {"status": "ok", "page": actual_page}

            doc.lockControllers()
            try:
                objects = _scan_page_objects(doc, vc, actual_page)
            finally:
                doc.unlockControllers()
            # Leave the cursor on the requested page (scanning moved it around).
            vc.jumpToPage(actual_page)
            return {"status": "ok", "page": actual_page, **objects}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class GetPageObjects(ToolBase):
    name = "nav_page_objects"
    aliases = ["get_page_objects"]
    intent = "navigate"
    description = (
        "Get images, tables, and frames on a specific page. "
        "Provide page number, locator, or paragraph_index."
    )
    parameters = {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "Page number"},
            "locator": {"type": "string", "description": "Locator to determine page"},
            "paragraph_index": {"type": "integer", "description": "Paragraph index to determine page"},
        },
        "required": [],
    }
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        doc_svc = ctx.services.document
        page = kwargs.get("page")

        if page is None:
            locator = kwargs.get("locator")
            para_idx = kwargs.get("paragraph_index")
            if locator:
                try:
                    resolved = doc_svc.resolve_locator(doc, locator)
                    para_idx = resolved.get("para_index", 0)
                except ValueError as e:
                    return {"status": "error", "error": str(e)}
            if para_idx is not None:
                page = doc_svc.get_page_for_paragraph(doc, para_idx)
            else:
                try:
                    page = doc.getCurrentController().getViewCursor().getPage()
                except Exception:
                    page = 1

        try:
            controller = doc.getCurrentController()
            vc = controller.getViewCursor()
            saved = doc.getText().createTextCursorByRange(vc.getStart())
            saved_page = vc.getPage()
            doc.lockControllers()
            try:
                objects = _scan_page_objects(doc, vc, page)
            finally:
                doc.unlockControllers()
            # Restore AFTER unlock so viewport actually scrolls back
            vc.jumpToPage(saved_page)
            vc.gotoRange(saved, False)
            return {"status": "ok", "page": page, **objects}
        except Exception as e:
            return {"status": "error", "error": str(e)}


def _scan_page_objects(doc, vc, page):
    """Scan a page for images, tables and text frames. Moves the view cursor."""
    images = []
    if hasattr(doc, "getGraphicObjects"):
        for name in doc.getGraphicObjects().getElementNames():
            try:
                g = doc.getGraphicObjects().getByName(name)
                vc.gotoRange(g.getAnchor(), False)
                if vc.getPage() == page:
                    size = g.getPropertyValue("Size")
                    images.append({
                        "name": name,
                        "width_mm": size.Width // 100,
                        "height_mm": size.Height // 100,
                        "title": g.getPropertyValue("Title"),
                    })
            except Exception:
                pass

    tables = []
    if hasattr(doc, "getTextTables"):
        for name in doc.getTextTables().getElementNames():
            try:
                t = doc.getTextTables().getByName(name)
                vc.gotoRange(t.getAnchor(), False)
                if vc.getPage() == page:
                    tables.append({
                        "name": name,
                        "rows": t.getRows().getCount(),
                        "cols": t.getColumns().getCount(),
                    })
            except Exception:
                pass

    frames = []
    if hasattr(doc, "getTextFrames"):
        for fname in doc.getTextFrames().getElementNames():
            try:
                fr = doc.getTextFrames().getByName(fname)
                vc.gotoRange(fr.getAnchor(), False)
                if vc.getPage() == page:
                    size = fr.getPropertyValue("Size")
                    frames.append({
                        "name": fname,
                        "width_mm": size.Width // 100,
                        "height_mm": size.Height // 100,
                    })
            except Exception:
                pass

    return {"images": images, "tables": tables, "frames": frames}


class RefreshIndexes(ToolBase):
    name = "refresh_indexes"
    intent = "navigate"
    description = "Refresh all document indexes (TOC, bibliography, etc.)."
    parameters = {"type": "object", "properties": {}, "required": []}
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        if not hasattr(doc, "getDocumentIndexes"):
            return {"status": "error", "error": "Document does not support indexes"}
        try:
            indexes = doc.getDocumentIndexes()
            count = indexes.getCount()
            refreshed = []
            for i in range(count):
                idx = indexes.getByIndex(i)
                idx.update()
                name = idx.getName() if hasattr(idx, "getName") else "index_%d" % i
                refreshed.append(name)
            return {"status": "ok", "refreshed": refreshed, "count": count}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class ReadSection(ToolBase):
    """Read the content of a named text section."""

    name = "section_read"
    aliases = ["read_section"]
    intent = "navigate"
    description = (
        "Read the text content of a named section. "
        "Returns the full text within the section boundaries."
    )
    parameters = {
        "type": "object",
        "properties": {
            "section_name": {
                "type": "string",
                "description": "Name of the section to read.",
            },
        },
        "required": ["section_name"],
    }
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        section_name = kwargs.get("section_name", "")
        if not section_name:
            return {"status": "error", "message": "section_name is required."}

        doc = ctx.doc
        if not hasattr(doc, "getTextSections"):
            return {"status": "error", "message": "Document does not support sections."}

        try:
            sections = doc.getTextSections()
            if not sections.hasByName(section_name):
                available = list(sections.getElementNames())
                return {
                    "status": "error",
                    "message": "Section '%s' not found." % section_name,
                    "available": available,
                }

            section = sections.getByName(section_name)
            anchor = section.getAnchor()

            # Extract paragraphs within the section
            enum = anchor.createEnumeration()
            paragraphs = []
            while enum.hasMoreElements():
                para = enum.nextElement()
                if para.supportsService("com.sun.star.text.Paragraph"):
                    paragraphs.append(para.getString())
                else:
                    paragraphs.append("[Table]")

            content = "\n".join(paragraphs)
            return {
                "status": "ok",
                "section_name": section_name,
                "paragraphs": paragraphs,
                "content": content,
                "length": len(content),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


class ResolveBookmark(ToolBase):
    """Resolve a bookmark to its paragraph index and heading text."""

    name = "bookmark_resolve"
    aliases = ["resolve_bookmark"]
    intent = "navigate"
    description = (
        "Resolve a bookmark to its current paragraph index and text. "
        "Most tools accept 'bookmark:NAME' as locator directly -- use "
        "bookmark_resolve only when you need the raw paragraph index."
    )
    parameters = {
        "type": "object",
        "properties": {
            "bookmark_name": {
                "type": "string",
                "description": "Bookmark name (e.g. _mcp_a1b2c3d4).",
            },
        },
        "required": ["bookmark_name"],
    }
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        bookmark_name = kwargs.get("bookmark_name", "")
        if not bookmark_name:
            return {"status": "error", "message": "bookmark_name is required."}

        doc = ctx.doc
        if not hasattr(doc, "getBookmarks"):
            return {"status": "error", "message": "Document does not support bookmarks."}

        try:
            bookmarks = doc.getBookmarks()
            if not bookmarks.hasByName(bookmark_name):
                hint = "Bookmark '%s' not found." % bookmark_name
                if bookmark_name.startswith("_mcp_"):
                    hint += (
                        " It may have been deleted or the document changed. "
                        "Use heading_text:<text> locator for resilient "
                        "heading addressing, or call nav_tree "
                        "to refresh bookmarks."
                    )
                    existing = [
                        n for n in bookmarks.getElementNames()
                        if n.startswith("_mcp_")
                    ]
                    if existing:
                        hint += " Existing bookmarks: %s" % ", ".join(existing[:10])
                return {"status": "error", "message": hint}

            bm = bookmarks.getByName(bookmark_name)
            anchor = bm.getAnchor()

            # Find paragraph index
            doc_svc = ctx.services.document
            para_ranges = doc_svc.get_paragraph_ranges(doc)
            text_obj = doc.getText()
            para_idx = doc_svc.find_paragraph_for_range(
                anchor, para_ranges, text_obj
            )

            result = {
                "status": "ok",
                "bookmark": bookmark_name,
                "paragraph_index": para_idx,
            }

            # Get heading text if available
            if 0 <= para_idx < len(para_ranges):
                element = para_ranges[para_idx]
                if element.supportsService("com.sun.star.text.Paragraph"):
                    try:
                        result["text"] = element.getString()
                        result["outline_level"] = element.getPropertyValue(
                            "OutlineLevel"
                        )
                    except Exception:
                        pass

            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}


class ResolveLocator(ToolBase):
    """Resolve any locator to its canonical form with metadata."""

    name = "nav_resolve"
    aliases = ["resolve_locator"]
    intent = "navigate"
    description = (
        "Resolve any locator string to its current paragraph position "
        "with confidence, canonical bookmark, heading context, and "
        "alternatives (for ambiguous matches). Use this to anchor a "
        "position before editing, or to validate a locator. "
        "Supported locator types: paragraph:<N>, bookmark:<name>, "
        "heading:<level.index>, heading_text:<text>, page:<N>, "
        "section:<name>, regex:/<pattern>/, cursor:, first:, last:."
    )
    parameters = {
        "type": "object",
        "properties": {
            "locator": {
                "type": "string",
                "description": (
                    "Locator string, e.g. 'heading_text:Introduction', "
                    "'bookmark:_mcp_a1b2c3d4', 'paragraph:42'."
                ),
            },
        },
        "required": ["locator"],
    }
    doc_types = ["writer"]

    def execute(self, ctx, **kwargs):
        locator = kwargs.get("locator", "")
        if not locator:
            return {"status": "error", "message": "locator is required."}

        doc = ctx.doc
        doc_svc = ctx.services.document

        try:
            result = doc_svc.resolve_locator(doc, locator)
            result["status"] = "ok"

            # Add page number if we have a paragraph index
            pi = result.get("para_index")
            if pi is not None:
                try:
                    page = doc_svc.get_page_for_paragraph(doc, pi)
                    if page:
                        result["page"] = page
                except Exception:
                    pass

            return result
        except ValueError as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class UpdateFields(ToolBase):
    """Refresh all text fields in the document."""

    name = "update_fields"
    intent = "navigate"
    description = (
        "Refresh all text fields (dates, page numbers, cross-references). "
        "Call after changes that affect computed fields."
    )
    parameters = {"type": "object", "properties": {}, "required": []}
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        if not hasattr(doc, "getTextFields"):
            return {
                "status": "error",
                "message": "Document does not support text fields.",
            }
        try:
            fields = doc.getTextFields()
            fields.refresh()

            # Count the fields
            enum = fields.createEnumeration()
            count = 0
            while enum.hasMoreElements():
                enum.nextElement()
                count += 1

            return {"status": "ok", "fields_refreshed": count}
        except Exception as e:
            return {"status": "error", "error": str(e)}
