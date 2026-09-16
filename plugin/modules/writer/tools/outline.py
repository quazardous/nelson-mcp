# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer outline / heading navigation tools."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")


class GetDocumentOutline(ToolBase):
    """Return the heading tree (outline) of a Writer document."""

    name = "nav_outline"
    aliases = ["get_document_outline"]
    description = (
        "Returns the document outline (headings hierarchy). Each heading "
        "has a 'path' (e.g. '2.4') to pass to nav_heading_content, and a "
        "'para_index' for the text_* tools."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_depth": {
                "type": "integer",
                "description": "Maximum heading depth to return (default: all).",
            },
        },
        "required": [],
    }
    doc_types = ["writer"]
    tier = "core"
    is_mutation = False

    def execute(self, ctx, **kwargs):
        doc_svc = ctx.services.document
        tree = doc_svc.build_heading_tree(ctx.doc)
        max_depth = kwargs.get("max_depth")
        if max_depth is not None:
            tree = [_prune_tree(node, max_depth) for node in tree]
        return {"status": "ok", "outline": tree}


_PATH_FORMAT = (
    "heading_path is the 'path' of a heading in nav_outline: dot-separated "
    "1-based positions such as '2' or '2.4', or the exact title of a "
    "heading that appears once.")


class GetHeadingContent(ToolBase):
    """Return content under a heading identified by its path."""

    name = "nav_heading_content"
    aliases = ["get_heading_content"]
    intent = "navigate"
    description = (
        "Returns content under a heading. Identify it by the 'path' "
        "nav_outline gives (e.g. '2.4' for the fourth child of the second "
        "heading) or by its exact title when that title is unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "heading_path": {
                "type": "string",
                "description": (
                    "The heading's 'path' from nav_outline (e.g. '1', "
                    "'2.3'), or its exact title if unique."),
            },
            "max_paragraphs": {
                "type": "integer",
                "description": "Maximum paragraphs to return (default: 50).",
            },
        },
        "required": ["heading_path"],
    }
    doc_types = ["writer"]
    is_mutation = False

    def execute(self, ctx, **kwargs):
        heading_path = kwargs["heading_path"]
        max_paragraphs = kwargs.get("max_paragraphs", 50)
        doc_svc = ctx.services.document

        tree = doc_svc.build_heading_tree(ctx.doc)
        node, error = _find_heading(tree, heading_path)
        if node is None:
            return {"status": "error", "message": error,
                    "hint": _PATH_FORMAT}

        # Read paragraphs under that heading, starting from its own index —
        # never by looking its title up again, which picks the first of two
        # headings that share a title.
        para_ranges = doc_svc.get_paragraph_ranges(ctx.doc)
        heading_level = node.get("level", 1)
        start_idx = node.get("para_index")
        if start_idx is None or start_idx >= len(para_ranges):
            return {
                "status": "error",
                "message": "Could not locate heading in paragraphs.",
            }

        # Collect body paragraphs until the next heading of equal or
        # higher level (or end of document).
        paragraphs = []
        for i in range(start_idx + 1, len(para_ranges)):
            if len(paragraphs) >= max_paragraphs:
                break
            p = para_ranges[i]
            if not hasattr(p, "getString"):
                continue
            try:
                level = p.getPropertyValue("OutlineLevel")
            except Exception:
                level = 0
            if level > 0 and level <= heading_level:
                break
            paragraphs.append(p.getString())

        return {
            "status": "ok",
            "heading_path": node.get("path"),
            "heading_title": node.get("title", ""),
            "para_index": start_idx,
            "paragraphs": paragraphs,
            "sub_headings": node.get("children", []),
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _prune_tree(node, max_depth, current_depth=1):
    """Remove children deeper than *max_depth*."""
    pruned = dict(node)
    if current_depth >= max_depth:
        pruned["children"] = []
    else:
        pruned["children"] = [
            _prune_tree(c, max_depth, current_depth + 1)
            for c in node.get("children", [])
        ]
    return pruned


def _parse_path(path_str):
    """Parse ``'1.2.3'`` into ``[1, 2, 3]`` (1-based). Returns None on error."""
    try:
        parts = [int(p) for p in path_str.strip().split(".")]
        if all(p >= 1 for p in parts):
            return parts
    except (ValueError, AttributeError):
        pass
    return None


def _walk_tree(tree, parts):
    """Walk a nested heading tree by 1-based indices.

    *tree* is a list of top-level heading dicts, each with a
    ``'children'`` list.
    """
    nodes = tree
    node = None
    for idx in parts:
        if idx < 1 or idx > len(nodes):
            return None
        node = nodes[idx - 1]
        nodes = node.get("children", [])
    return node


def _flatten(tree):
    for node in tree:
        yield node
        yield from _flatten(node.get("children", []))


def _find_heading(tree, heading_path):
    """Return (node, None) or (None, error message).

    A dotted path is walked; anything else is taken as an exact title,
    accepted only when a single heading carries it.
    """
    parts = _parse_path(heading_path)
    if parts is not None:
        node = _walk_tree(tree, parts)
        if node is None:
            return None, "No heading at path '%s'." % heading_path
        return node, None
    title = (heading_path or "").strip()
    matches = [n for n in _flatten(tree) if n.get("title") == title]
    if len(matches) == 1:
        return matches[0], None
    if matches:
        return None, ("%d headings are titled '%s', at paths %s — pass "
                      "one of those paths." % (
                          len(matches), title,
                          ", ".join(n["path"] for n in matches)))
    return None, "Invalid heading path: '%s'." % heading_path
