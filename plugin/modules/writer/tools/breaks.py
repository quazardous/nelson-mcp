# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Page and column breaks for Writer."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")

_BREAKS = {
    "page": "PAGE_BEFORE",
    "column": "COLUMN_BEFORE",
    "none": "NONE",
}


class InsertBreak(ToolBase):
    """Start a paragraph on a new page or column."""

    name = "text_insert_break"
    intent = "edit"
    description = (
        "Start a paragraph on a new page (type='page') or column "
        "(type='column'); type='none' removes the break. The break is a "
        "property of the paragraph, as Writer stores it: no empty "
        "paragraph is added."
    )
    parameters = {
        "type": "object",
        "properties": {
            "paragraph_index": {
                "type": "integer",
                "description": "0-based index of the paragraph that starts "
                               "the new page or column.",
            },
            "locator": {
                "type": "string",
                "description": (
                    "Locator instead of paragraph_index: 'paragraph:N', "
                    "'heading_text:Title', etc."),
            },
            "type": {
                "type": "string",
                "enum": ["page", "column", "none"],
                "description": "Kind of break (default: page).",
            },
        },
        "required": [],
    }
    doc_types = ["writer"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        import uno

        doc_svc = ctx.services.document
        index = kwargs.get("paragraph_index")
        locator = kwargs.get("locator")
        if locator is not None:
            index = doc_svc.resolve_locator(ctx.doc, locator).get("para_index")
        if not isinstance(index, int):
            return {"status": "error",
                    "error": "Provide paragraph_index or locator."}
        kind = kwargs.get("type") or "page"
        if kind not in _BREAKS:
            return {"status": "error",
                    "error": "type must be page, column or none."}

        para, count = doc_svc.find_paragraph_element(ctx.doc, index)
        if para is None:
            return {"status": "error",
                    "error": "No paragraph %d (document has %d)."
                             % (index, count)}
        if not para.supportsService("com.sun.star.text.Paragraph"):
            return {"status": "error",
                    "error": "Element %d is not a paragraph (a table?)."
                             % index}
        para.setPropertyValue(
            "BreakType", uno.Enum("com.sun.star.style.BreakType",
                                  _BREAKS[kind]))
        return {"status": "ok", "paragraph_index": index, "type": kind,
                "text": para.getString()[:80]}
