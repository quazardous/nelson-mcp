# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writer search tools: text_search, text_replace."""

import logging

from plugin.framework.tool_base import ToolBase

log = logging.getLogger("nelson.writer")


class SearchInDocument(ToolBase):
    """Search for text in a document body and text frames."""

    name = "text_search"
    aliases = ["search_in_document"]
    description = (
        "Search for text in the document. Searches the body AND text frames "
        "(captions, sidebars), so images/legends placed in frames are findable. "
        "Two body backends: 'direct' (exact literal/regex, always fresh) or "
        "'index' (stemmed/fuzzy word matching with AND/OR/NOT/NEAR, faster on "
        "large docs, no regex). The default backend is configurable in Options "
        "and can be overridden per call. Text frames are always searched directly. "
        "Returns matches with surrounding context and each body match's "
        "paragraph style, so a heading can be told from a table-of-contents "
        "entry with the same text; filter with style / exclude_style."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search string or regex pattern.",
            },
            "regex": {
                "type": "boolean",
                "description": (
                    "Use regular expression (default: false). "
                    "Forces the 'direct' backend (the index cannot do regex)."
                ),
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive search (default: false).",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return per source (default: 20).",
            },
            "context_paragraphs": {
                "type": "integer",
                "description": (
                    "Number of paragraphs of context around each match "
                    "(default: 1)."
                ),
            },
            "include_frames": {
                "type": "boolean",
                "description": "Also search inside text frames (default: true).",
            },
            "include_tables": {
                "type": "boolean",
                "description": (
                    "Also search inside table cells (default: true). Cell "
                    "matches carry the table and cell names."),
            },
            "style": {
                "type": "string",
                "description": (
                    "Only match paragraphs with this paragraph style, as "
                    "reported in a match's 'style' (case-insensitive), "
                    "e.g. 'Heading 1'. Searches the body only, with the "
                    "direct backend."
                ),
            },
            "exclude_style": {
                "type": "string",
                "description": (
                    "Skip paragraphs with this paragraph style, e.g. a "
                    "table-of-contents style. Same rules as style."
                ),
            },
            "backend": {
                "type": "string",
                "enum": ["direct", "index"],
                "description": (
                    "Override the body-search backend for this call. "
                    "Defaults to the configured Options value."
                ),
            },
        },
        "required": ["pattern"],
    }
    doc_types = ["writer"]
    tier = "core"
    is_mutation = False

    def execute(self, ctx, **kwargs):
        pattern = kwargs.get("pattern", "")
        if not pattern:
            return {"status": "error", "message": "pattern is required."}

        use_regex = kwargs.get("regex", False)
        case_sensitive = kwargs.get("case_sensitive", False)
        max_results = kwargs.get("max_results", 20)
        context_paragraphs = kwargs.get("context_paragraphs", 1)
        include_frames = kwargs.get("include_frames", True)
        include_tables = kwargs.get("include_tables", True)
        style = (kwargs.get("style") or "").strip().casefold() or None
        exclude_style = (
            (kwargs.get("exclude_style") or "").strip().casefold() or None)
        styled = style is not None or exclude_style is not None

        doc = ctx.doc

        # Resolve the body-search backend: per-call override > config > default.
        backend = kwargs.get("backend")
        if not backend:
            try:
                backend = ctx.services.config.proxy_for("writer").get(
                    "search_backend", "direct")
            except Exception:
                backend = "direct"

        idx_svc = getattr(ctx.services, "writer_index", None)
        backend_note = None
        if backend == "index":
            if use_regex:
                backend = "direct"
                backend_note = "regex requested — fell back to direct backend"
            elif styled:
                backend = "direct"
                backend_note = ("style filter requested — fell back to "
                                "direct backend")
            elif idx_svc is None:
                backend = "direct"
                backend_note = "index module unavailable — fell back to direct backend"

        try:
            if backend == "index":
                body = self._search_body_index(
                    ctx, idx_svc, pattern, max_results, context_paragraphs)
            else:
                body = self._search_body_direct(
                    ctx, pattern, use_regex, case_sensitive,
                    max_results, context_paragraphs,
                    style=style, exclude_style=exclude_style)
            if body.get("status") == "error":
                return body
            matches = body["matches"]
            total_count = body["total_count"]
            _add_styles(ctx, matches)

            frame_count = table_count = 0
            # A style filter is about body paragraphs: frames and cells would
            # only add matches it cannot vouch for.
            if include_frames and not styled:
                frame_matches, frame_count = _search_frames(
                    ctx, pattern, use_regex, case_sensitive, max_results)
                matches = matches + frame_matches
            # The direct backend used to skip table cells, so it found fewer
            # matches than the index, which covers them (#28, #2637).
            if include_tables and not styled and backend == "direct":
                cell_matches, table_count = _search_tables(
                    ctx, pattern, use_regex, case_sensitive, max_results)
                matches = matches + cell_matches

            # Enrich with nearest-heading context where a paragraph is known.
            tree_svc = getattr(ctx.services, "writer_tree", None)
            if tree_svc and matches:
                enrichable = [m for m in matches
                              if m.get("paragraph_index") is not None]
                if enrichable:
                    tree_svc.enrich_search_results(doc, enrichable)

            return {
                "status": "ok",
                "backend": backend,
                "matches": matches,
                "count": total_count + frame_count + table_count,
                "body_count": total_count,
                "frame_count": frame_count,
                "table_count": table_count,
                **({"backend_note": backend_note} if backend_note else {}),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _search_body_direct(self, ctx, pattern, use_regex, case_sensitive,
                            max_results, context_paragraphs,
                            style=None, exclude_style=None):
        """Exact literal/regex scan of body paragraphs (legacy behaviour).

        *style* / *exclude_style* (casefolded) keep or skip paragraphs by
        paragraph style.
        """
        import re as re_mod

        doc = ctx.doc
        doc_svc = ctx.services.document
        para_ranges = doc_svc.get_paragraph_ranges(doc)
        para_count = len(para_ranges)

        para_texts = []
        for para in para_ranges:
            try:
                if para.supportsService("com.sun.star.text.Paragraph"):
                    para_texts.append(para.getString())
                else:
                    para_texts.append("")
            except Exception:
                para_texts.append("")

        def excluded(i):
            if style is None and exclude_style is None:
                return False
            name = (_para_style(para_ranges[i]) or "").casefold()
            if style is not None and name != style:
                return True
            return exclude_style is not None and name == exclude_style

        compiled = None
        if use_regex:
            flags = 0 if case_sensitive else re_mod.IGNORECASE
            try:
                compiled = re_mod.compile(pattern, flags)
            except re_mod.error as e:
                return {"status": "error", "error": "Invalid regex: %s" % e}

        matches = []
        total_count = 0
        for i, ptext in enumerate(para_texts):
            if not ptext or excluded(i):
                continue
            if use_regex:
                for m in compiled.finditer(ptext):
                    total_count += 1
                    if len(matches) < max_results:
                        matches.append(_build_match(
                            m.group(), i, context_paragraphs,
                            para_count, para_texts))
            else:
                haystack = ptext if case_sensitive else ptext.lower()
                needle = pattern if case_sensitive else pattern.lower()
                step = max(1, len(needle))
                pos = 0
                while True:
                    pos = haystack.find(needle, pos)
                    if pos == -1:
                        break
                    total_count += 1
                    if len(matches) < max_results:
                        matches.append(_build_match(
                            ptext[pos:pos + len(pattern)], i,
                            context_paragraphs, para_count, para_texts))
                    pos += step

        for m in matches:
            m["source"] = "body"
        return {"matches": matches, "total_count": total_count}

    def _search_body_index(self, ctx, idx_svc, pattern,
                           max_results, context_paragraphs):
        """Stemmed full-text body search via the writer_index service."""
        try:
            result = idx_svc.search_boolean(
                ctx.doc, pattern,
                max_results=max_results,
                context_paragraphs=context_paragraphs)
        except ValueError as e:
            return {"status": "error", "error": str(e)}
        matches = result.get("matches", [])
        for m in matches:
            m["source"] = "body"
        return {"matches": matches, "total_count": result.get("total_found", len(matches))}


def _para_style(para):
    try:
        return para.getPropertyValue("ParaStyleName") or None
    except Exception:
        return None


def _add_styles(ctx, matches):
    """Give each body match its paragraph's style."""
    wanted = [m for m in matches if m.get("paragraph_index") is not None]
    if not wanted:
        return
    para_ranges = ctx.services.document.get_paragraph_ranges(ctx.doc)
    for m in wanted:
        i = m["paragraph_index"]
        if 0 <= i < len(para_ranges):
            m["style"] = _para_style(para_ranges[i])


def _build_match(text, para_idx, ctx_paras, para_count, para_texts):
    """Build a single match result with context paragraphs."""
    ctx_lo = max(0, para_idx - ctx_paras)
    ctx_hi = min(para_count, para_idx + ctx_paras + 1)
    context = [
        {"index": j, "text": para_texts[j]}
        for j in range(ctx_lo, ctx_hi)
    ]
    return {
        "text": text,
        "paragraph_index": para_idx,
        "context": context,
    }


def _frame_snippet(text, pos, length, window=60):
    """Return a short snippet of frame text around a match position."""
    lo = max(0, pos - window)
    hi = min(len(text), pos + length + window)
    snippet = text[lo:hi].replace("\n", " ").strip()
    if lo > 0:
        snippet = "…" + snippet
    if hi < len(text):
        snippet = snippet + "…"
    return snippet


def _find_hits(text, pattern, compiled, case_sensitive):
    """(matched_text, position) pairs of *pattern* in *text*."""
    if compiled is not None:
        return [(m.group(), m.start()) for m in compiled.finditer(text)]
    haystack = text if case_sensitive else text.lower()
    needle = pattern if case_sensitive else pattern.lower()
    hits, pos = [], 0
    while needle:
        pos = haystack.find(needle, pos)
        if pos == -1:
            break
        hits.append((text[pos:pos + len(pattern)], pos))
        pos += len(needle)
    return hits


def _search_tables(ctx, pattern, use_regex, case_sensitive, max_results):
    """Search every table cell. Returns (matches, total_count)."""
    import re as re_mod

    doc = ctx.doc
    if not hasattr(doc, "getTextTables"):
        return [], 0
    compiled = None
    if use_regex:
        try:
            compiled = re_mod.compile(
                pattern, 0 if case_sensitive else re_mod.IGNORECASE)
        except re_mod.error:
            return [], 0
    tables = doc.getTextTables()
    matches, total = [], 0
    for name in tables.getElementNames():
        try:
            table = tables.getByName(name)
            cell_names = table.getCellNames()
        except Exception:
            continue
        for cell_name in cell_names:
            try:
                text = table.getCellByName(cell_name).getString()
            except Exception:
                continue
            if not text:
                continue
            for matched, pos in _find_hits(text, pattern, compiled,
                                           case_sensitive):
                total += 1
                if len(matches) < max_results:
                    matches.append({
                        "source": "table_cell",
                        "table": name,
                        "cell": cell_name,
                        "text": matched,
                        "snippet": _frame_snippet(text, pos, len(matched)),
                    })
    return matches, total


def _search_frames(ctx, pattern, use_regex, case_sensitive, max_results):
    """Search inside every text frame. Returns (matches, total_count).

    Frame matches carry the frame name, a text snippet, and the frame's anchor
    paragraph index (best-effort) so they integrate with heading enrichment and
    navigation. Resolves #5.
    """
    import re as re_mod

    doc = ctx.doc
    if not hasattr(doc, "getTextFrames"):
        return [], 0
    frames = doc.getTextFrames()

    compiled = None
    if use_regex:
        flags = 0 if case_sensitive else re_mod.IGNORECASE
        try:
            compiled = re_mod.compile(pattern, flags)
        except re_mod.error:
            return [], 0

    doc_svc = ctx.services.document
    para_ranges = None
    text_obj = None

    matches = []
    total = 0
    for name in frames.getElementNames():
        try:
            frame = frames.getByName(name)
            ftext = frame.getString()
        except Exception:
            continue
        if not ftext:
            continue

        hits = []  # list of (matched_text, pos)
        if use_regex:
            for m in compiled.finditer(ftext):
                hits.append((m.group(), m.start()))
        else:
            haystack = ftext if case_sensitive else ftext.lower()
            needle = pattern if case_sensitive else pattern.lower()
            step = max(1, len(needle))
            pos = 0
            while True:
                pos = haystack.find(needle, pos)
                if pos == -1:
                    break
                hits.append((ftext[pos:pos + len(pattern)], pos))
                pos += step

        if not hits:
            continue
        total += len(hits)

        # Resolve the frame anchor paragraph once we know we need it.
        anchor_para = None
        try:
            if para_ranges is None:
                para_ranges = doc_svc.get_paragraph_ranges(doc)
                text_obj = doc.getText()
            anchor = frame.getAnchor()
            anchor_para = doc_svc.find_paragraph_for_range(
                anchor, para_ranges, text_obj)
            if anchor_para is not None and anchor_para < 0:
                anchor_para = None
        except Exception:
            anchor_para = None

        for matched_text, pos in hits:
            if len(matches) >= max_results:
                break
            matches.append({
                "source": "frame",
                "frame_name": name,
                "text": matched_text,
                "snippet": _frame_snippet(ftext, pos, len(matched_text)),
                "paragraph_index": anchor_para,
            })

    return matches, total


class ReplaceInDocument(ToolBase):
    """Find and replace text preserving formatting."""

    name = "text_replace"
    aliases = ["replace_in_document"]
    description = (
        "Find and replace text in the document with regex support. "
        "Preserves existing formatting. Returns count of replacements."
    )
    parameters = {
        "type": "object",
        "properties": {
            "search": {
                "type": "string",
                "description": "Text or regex pattern to find.",
            },
            "replace": {
                "type": "string",
                "description": "Replacement text.",
            },
            "regex": {
                "type": "boolean",
                "description": "Use regular expression (default: false).",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive matching (default: false).",
            },
            "replace_all": {
                "type": "boolean",
                "description": (
                    "Replace all occurrences (default: true). "
                    "Set to false to replace only the first match."
                ),
            },
        },
        "required": ["search", "replace"],
    }
    doc_types = ["writer"]
    tier = "core"
    is_mutation = True

    def execute(self, ctx, **kwargs):
        search = kwargs.get("search", "")
        replace = kwargs.get("replace", "")
        if not search:
            return {"status": "error", "message": "search is required."}

        regex = kwargs.get("regex", False)
        case_sensitive = kwargs.get("case_sensitive", False)
        replace_all = kwargs.get("replace_all", True)

        doc = ctx.doc

        try:
            replace_desc = doc.createReplaceDescriptor()
            replace_desc.SearchString = search
            replace_desc.ReplaceString = replace
            replace_desc.SearchRegularExpression = bool(regex)
            replace_desc.SearchCaseSensitive = bool(case_sensitive)

            if replace_all:
                count = doc.replaceAll(replace_desc)
            else:
                # Replace only the first match
                found = doc.findFirst(replace_desc)
                if found is not None:
                    found.setString(replace)
                    count = 1
                else:
                    count = 0

            # Invalidate document cache after edits
            if count > 0:
                doc_svc = ctx.services.document
                doc_svc.invalidate_cache(doc)

            return {
                "status": "ok",
                "replacements": count,
                "search": search,
                "replace": replace,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
