# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cross-document hyperlink tools.

Writer: inserts via HyperLinkURL on text range, scans text portions.
Calc: uses TextField.URL on cells.
Draw/Impress: not supported (shapes have their own URL interaction).
"""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.doc")


class ListHyperlinks(ToolBase):
    """List all hyperlinks in the document."""

    name = "link_list"
    aliases = ["list_hyperlinks"]
    intent = "navigate"
    description = (
        "List all hyperlinks in the document. "
        "In Writer, scans text fields and text portions for URLs. "
        "In Calc, scans cells in the used area for HyperLinkURL."
    )
    parameters = {
        "type": "object",
        "properties": {
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
    doc_types = ["writer", "calc"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        if ctx.doc_type == "writer":
            return self._list_writer(ctx)
        return self._list_calc(ctx, kwargs.get("sheet_name"))

    def _list_writer(self, ctx):
        """List hyperlinks in Writer via text field enumeration."""
        doc = ctx.doc
        links = []
        try:
            fields = doc.getTextFields()
            enum = fields.createEnumeration()
            idx = 0
            while enum.hasMoreElements():
                field = enum.nextElement()
                try:
                    if field.supportsService("com.sun.star.text.TextField.URL"):
                        url = field.getPropertyValue("URL")
                        rep = field.getPropertyValue("Representation")
                        if url:
                            links.append({
                                "index": idx,
                                "url": url,
                                "text": rep or url,
                                "type": "field",
                            })
                            idx += 1
                except Exception:
                    pass
        except Exception:
            pass

        # Also scan text portions for inline HyperLinkURL
        try:
            text = doc.getText()
            enum = text.createEnumeration()
            while enum.hasMoreElements():
                para = enum.nextElement()
                if not hasattr(para, "createEnumeration"):
                    continue
                portions = para.createEnumeration()
                while portions.hasMoreElements():
                    portion = portions.nextElement()
                    try:
                        url = portion.getPropertyValue("HyperLinkURL")
                        if url:
                            name = portion.getPropertyValue("HyperLinkName")
                            txt = portion.getString()
                            links.append({
                                "index": idx,
                                "url": url,
                                "text": txt or name or url,
                                "type": "inline",
                            })
                            idx += 1
                    except Exception:
                        pass
        except Exception:
            pass

        return {"status": "ok", "hyperlinks": links, "count": len(links)}

    def _list_calc(self, ctx, sheet_name=None):
        """List hyperlinks in Calc cells."""
        doc = ctx.doc
        if sheet_name:
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                return {"status": "error", "message": "Sheet not found: %s" % sheet_name}
            sheet = sheets.getByName(sheet_name)
        else:
            sheet = doc.getCurrentController().getActiveSheet()

        links = []
        try:
            cursor = sheet.createCursor()
            cursor.gotoStartOfUsedArea(False)
            cursor.gotoEndOfUsedArea(True)
            ra = cursor.getRangeAddress()

            from plugin.modules.calc.address_utils import index_to_column
            idx = 0
            for r in range(ra.StartRow, ra.EndRow + 1):
                for c in range(ra.StartColumn, ra.EndColumn + 1):
                    cell = sheet.getCellByPosition(c, r)
                    try:
                        tf = cell.getTextFields()
                        if tf and tf.getCount() > 0:
                            for fi in range(tf.getCount()):
                                field = tf.getByIndex(fi)
                                url = field.getPropertyValue("URL")
                                if url:
                                    cell_ref = "%s%d" % (index_to_column(c), r + 1)
                                    links.append({
                                        "index": idx,
                                        "cell": cell_ref,
                                        "url": url,
                                        "text": cell.getString(),
                                    })
                                    idx += 1
                    except Exception:
                        pass
        except Exception as e:
            log.debug("link_list calc: %s", e)

        return {
            "status": "ok",
            "sheet": sheet.getName(),
            "hyperlinks": links,
            "count": len(links),
        }


class InsertHyperlink(ToolBase):
    """Insert a hyperlink into the document."""

    name = "link_insert"
    aliases = ["insert_hyperlink"]
    intent = "edit"
    description = (
        "Insert a hyperlink into the document. "
        "In Writer, inserts a URL text field at the cursor or paragraph position. "
        "In Calc, sets the hyperlink on a cell."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to link to.",
            },
            "text": {
                "type": "string",
                "description": "Display text for the link (defaults to URL).",
            },
            "writer": {
                "type": "object",
                "description": "Writer-specific options",
                "properties": {
                    "paragraph_index": {
                        "type": "integer",
                        "description": "Insert at end of this paragraph.",
                    },
                    "locator": {
                        "type": "string",
                        "description": "Unified locator for insertion point.",
                    },
                },
            },
            "calc": {
                "type": "object",
                "description": "Calc-specific options",
                "properties": {
                    "cell": {
                        "type": "string",
                        "description": "Cell reference (e.g. 'A1').",
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Sheet name (active sheet if omitted).",
                    },
                },
            },
        },
        "required": ["url"],
    }
    doc_types = ["writer", "calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        url = kwargs.get("url", "")
        if not url:
            return {"status": "error", "message": "url is required."}
        text = kwargs.get("text", url)
        extra = {k: v for k, v in kwargs.items() if k not in ("url", "text")}

        if ctx.doc_type == "writer":
            return self._insert_writer(ctx, url, text, **extra)
        return self._insert_calc(ctx, url, text, **extra)

    def _insert_writer(self, ctx, url, text, **kwargs):
        """Insert hyperlink in Writer via HyperLinkURL on a text range."""
        doc = ctx.doc
        doc_svc = ctx.services.document

        try:
            doc_text = doc.getText()
            locator = kwargs.get("locator")
            paragraph_index = kwargs.get("paragraph_index")

            if locator is not None and paragraph_index is None:
                resolved = doc_svc.resolve_locator(doc, locator)
                paragraph_index = resolved.get("para_index")

            if paragraph_index is not None:
                target, _ = doc_svc.find_paragraph_element(doc, paragraph_index)
                if target is None:
                    return {"status": "error", "message": "Paragraph not found."}
                cursor = doc_text.createTextCursorByRange(target.getEnd())
            else:
                cursor = doc_text.createTextCursor()
                cursor.gotoEnd(False)

            # Insert display text then apply hyperlink properties
            doc_text.insertString(cursor, text, False)
            # Move cursor back over the inserted text
            cursor.goLeft(len(text), True)
            cursor.setPropertyValue("HyperLinkURL", url)
            cursor.setPropertyValue("HyperLinkName", text)
            cursor.setPropertyValue("HyperLinkTarget", "")

            return {"status": "ok", "url": url, "text": text}
        except Exception as e:
            log.exception("link_insert writer failed")
            return {"status": "error", "error": str(e)}

    def _insert_calc(self, ctx, url, text, **kwargs):
        """Set hyperlink on a Calc cell."""
        doc = ctx.doc
        cell_ref = kwargs.get("cell", "A1")
        sheet_name = kwargs.get("sheet_name")

        try:
            if sheet_name:
                sheets = doc.getSheets()
                sheet = sheets.getByName(sheet_name)
            else:
                sheet = doc.getCurrentController().getActiveSheet()

            cell = sheet.getCellRangeByName(cell_ref)

            # Set display text
            cell.setString(text)

            # Insert URL field into cell
            cell_text = cell.getText()
            cursor = cell_text.createTextCursor()
            cursor.gotoStart(False)
            cursor.gotoEnd(True)

            field = doc.createInstance("com.sun.star.text.TextField.URL")
            field.setPropertyValue("URL", url)
            field.setPropertyValue("Representation", text)
            cell_text.insertTextContent(cursor, field, True)

            return {"status": "ok", "cell": cell_ref, "url": url, "text": text}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class RemoveHyperlink(ToolBase):
    """Remove a hyperlink from the document."""

    name = "link_remove"
    aliases = ["remove_hyperlink"]
    intent = "edit"
    description = (
        "Remove a hyperlink by index (from link_list). "
        "In Writer, clears HyperLinkURL on the text portion. "
        "In Calc, removes the URL text field from the cell. "
        "The display text is preserved."
    )
    parameters = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Hyperlink index (from link_list).",
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
        "required": ["index"],
    }
    doc_types = ["writer", "calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        target_index = kwargs["index"]
        if ctx.doc_type == "writer":
            return self._remove_writer(ctx, target_index)
        return self._remove_calc(ctx, target_index, kwargs.get("sheet_name"))

    def _remove_writer(self, ctx, target_index):
        """Remove a hyperlink in Writer by clearing HyperLinkURL."""
        doc = ctx.doc
        idx = 0

        # Scan text fields first
        try:
            fields = doc.getTextFields()
            enum = fields.createEnumeration()
            while enum.hasMoreElements():
                field = enum.nextElement()
                try:
                    if field.supportsService("com.sun.star.text.TextField.URL"):
                        url = field.getPropertyValue("URL")
                        if url:
                            if idx == target_index:
                                # Remove the text field, replace with plain text
                                anchor = field.getAnchor()
                                text_content = anchor.getString()
                                doc.getText().removeTextContent(field)
                                return {
                                    "status": "ok",
                                    "removed_index": target_index,
                                    "type": "field",
                                    "preserved_text": text_content,
                                }
                            idx += 1
                except Exception:
                    pass
        except Exception:
            pass

        # Scan inline hyperlinks
        try:
            text = doc.getText()
            enum = text.createEnumeration()
            while enum.hasMoreElements():
                para = enum.nextElement()
                if not hasattr(para, "createEnumeration"):
                    continue
                portions = para.createEnumeration()
                while portions.hasMoreElements():
                    portion = portions.nextElement()
                    try:
                        url = portion.getPropertyValue("HyperLinkURL")
                        if url:
                            if idx == target_index:
                                portion.setPropertyValue("HyperLinkURL", "")
                                portion.setPropertyValue("HyperLinkName", "")
                                portion.setPropertyValue("HyperLinkTarget", "")
                                return {
                                    "status": "ok",
                                    "removed_index": target_index,
                                    "type": "inline",
                                    "preserved_text": portion.getString(),
                                }
                            idx += 1
                    except Exception:
                        pass
        except Exception:
            pass

        return {"status": "error", "message": "Hyperlink index %d not found." % target_index}

    def _remove_calc(self, ctx, target_index, sheet_name=None):
        """Remove a hyperlink in Calc by clearing the URL field."""
        doc = ctx.doc
        if sheet_name:
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                return {"status": "error", "message": "Sheet not found: %s" % sheet_name}
            sheet = sheets.getByName(sheet_name)
        else:
            sheet = doc.getCurrentController().getActiveSheet()

        try:
            cursor = sheet.createCursor()
            cursor.gotoStartOfUsedArea(False)
            cursor.gotoEndOfUsedArea(True)
            ra = cursor.getRangeAddress()

            from plugin.modules.calc.address_utils import index_to_column
            idx = 0
            for r in range(ra.StartRow, ra.EndRow + 1):
                for c in range(ra.StartColumn, ra.EndColumn + 1):
                    cell = sheet.getCellByPosition(c, r)
                    try:
                        tf = cell.getTextFields()
                        if tf and tf.getCount() > 0:
                            for fi in range(tf.getCount()):
                                field = tf.getByIndex(fi)
                                url = field.getPropertyValue("URL")
                                if url:
                                    if idx == target_index:
                                        # Keep the display text, remove the field
                                        display = cell.getString()
                                        cell_text = cell.getText()
                                        cell_text.removeTextContent(field)
                                        cell.setString(display)
                                        cell_ref = "%s%d" % (index_to_column(c), r + 1)
                                        return {
                                            "status": "ok",
                                            "removed_index": target_index,
                                            "cell": cell_ref,
                                            "preserved_text": display,
                                        }
                                    idx += 1
                    except Exception:
                        pass
        except Exception as e:
            log.debug("link_remove calc: %s", e)

        return {"status": "error", "message": "Hyperlink index %d not found." % target_index}


class EditHyperlink(ToolBase):
    """Edit an existing hyperlink."""

    name = "link_edit"
    aliases = ["edit_hyperlink"]
    intent = "edit"
    description = (
        "Edit an existing hyperlink by index (from link_list). "
        "Can change the URL and/or display text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Hyperlink index (from link_list).",
            },
            "url": {
                "type": "string",
                "description": "New URL (unchanged if omitted).",
            },
            "text": {
                "type": "string",
                "description": "New display text (unchanged if omitted).",
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
        "required": ["index"],
    }
    doc_types = ["writer", "calc"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        target_index = kwargs["index"]
        new_url = kwargs.get("url")
        new_text = kwargs.get("text")
        if new_url is None and new_text is None:
            return {"status": "error", "message": "Specify url and/or text to change."}

        if ctx.doc_type == "writer":
            return self._edit_writer(ctx, target_index, new_url, new_text)
        return self._edit_calc(ctx, target_index, new_url, new_text,
                               kwargs.get("sheet_name"))

    def _edit_writer(self, ctx, target_index, new_url, new_text):
        """Edit a hyperlink in Writer."""
        doc = ctx.doc
        idx = 0

        # Scan text fields
        try:
            fields = doc.getTextFields()
            enum = fields.createEnumeration()
            while enum.hasMoreElements():
                field = enum.nextElement()
                try:
                    if field.supportsService("com.sun.star.text.TextField.URL"):
                        url = field.getPropertyValue("URL")
                        if url:
                            if idx == target_index:
                                if new_url is not None:
                                    field.setPropertyValue("URL", new_url)
                                if new_text is not None:
                                    field.setPropertyValue("Representation", new_text)
                                return {
                                    "status": "ok",
                                    "index": target_index,
                                    "type": "field",
                                    "url": new_url or url,
                                    "text": new_text or field.getPropertyValue("Representation"),
                                }
                            idx += 1
                except Exception:
                    pass
        except Exception:
            pass

        # Scan inline hyperlinks
        try:
            text = doc.getText()
            enum = text.createEnumeration()
            while enum.hasMoreElements():
                para = enum.nextElement()
                if not hasattr(para, "createEnumeration"):
                    continue
                portions = para.createEnumeration()
                while portions.hasMoreElements():
                    portion = portions.nextElement()
                    try:
                        url = portion.getPropertyValue("HyperLinkURL")
                        if url:
                            if idx == target_index:
                                if new_url is not None:
                                    portion.setPropertyValue("HyperLinkURL", new_url)
                                if new_text is not None:
                                    # For inline links, we need to change the text content
                                    portion.setString(new_text)
                                    portion.setPropertyValue("HyperLinkName", new_text)
                                return {
                                    "status": "ok",
                                    "index": target_index,
                                    "type": "inline",
                                    "url": new_url or url,
                                    "text": new_text or portion.getString(),
                                }
                            idx += 1
                    except Exception:
                        pass
        except Exception:
            pass

        return {"status": "error", "message": "Hyperlink index %d not found." % target_index}

    def _edit_calc(self, ctx, target_index, new_url, new_text, sheet_name=None):
        """Edit a hyperlink in Calc."""
        doc = ctx.doc
        if sheet_name:
            sheets = doc.getSheets()
            if not sheets.hasByName(sheet_name):
                return {"status": "error", "message": "Sheet not found: %s" % sheet_name}
            sheet = sheets.getByName(sheet_name)
        else:
            sheet = doc.getCurrentController().getActiveSheet()

        try:
            cursor = sheet.createCursor()
            cursor.gotoStartOfUsedArea(False)
            cursor.gotoEndOfUsedArea(True)
            ra = cursor.getRangeAddress()

            from plugin.modules.calc.address_utils import index_to_column
            idx = 0
            for r in range(ra.StartRow, ra.EndRow + 1):
                for c in range(ra.StartColumn, ra.EndColumn + 1):
                    cell = sheet.getCellByPosition(c, r)
                    try:
                        tf = cell.getTextFields()
                        if tf and tf.getCount() > 0:
                            for fi in range(tf.getCount()):
                                field = tf.getByIndex(fi)
                                url = field.getPropertyValue("URL")
                                if url:
                                    if idx == target_index:
                                        if new_url is not None:
                                            field.setPropertyValue("URL", new_url)
                                        if new_text is not None:
                                            field.setPropertyValue("Representation", new_text)
                                            cell.setString(new_text)
                                            # Re-insert field after text change
                                            cell_text = cell.getText()
                                            cur = cell_text.createTextCursor()
                                            cur.gotoStart(False)
                                            cur.gotoEnd(True)
                                            new_field = doc.createInstance(
                                                "com.sun.star.text.TextField.URL"
                                            )
                                            new_field.setPropertyValue(
                                                "URL", new_url or url
                                            )
                                            new_field.setPropertyValue(
                                                "Representation", new_text
                                            )
                                            cell_text.insertTextContent(
                                                cur, new_field, True
                                            )
                                        cell_ref = "%s%d" % (index_to_column(c), r + 1)
                                        return {
                                            "status": "ok",
                                            "index": target_index,
                                            "cell": cell_ref,
                                            "url": new_url or url,
                                            "text": new_text or cell.getString(),
                                        }
                                    idx += 1
                    except Exception:
                        pass
        except Exception as e:
            log.debug("link_edit calc: %s", e)

        return {"status": "error", "message": "Hyperlink index %d not found." % target_index}
