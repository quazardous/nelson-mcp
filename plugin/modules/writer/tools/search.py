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
        "Returns matches with surrounding context."
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
                    max_results, context_paragraphs)
            if body.get("status") == "error":
                return body
            matches = body["matches"]
            total_count = body["total_count"]

            frame_count = 0
            if include_frames:
                frame_matches, frame_count = _search_frames(
                    ctx, pattern, use_regex, case_sensitive, max_results)
                matches = matches + frame_matches

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
                "count": total_count + frame_count,
                "body_count": total_count,
                "frame_count": frame_count,
                **({"backend_note": backend_note} if backend_note else {}),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _search_body_direct(self, ctx, pattern, use_regex, case_sensitive,
                            max_results, context_paragraphs):
        """Exact literal/regex scan of body paragraphs (legacy behaviour)."""
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
            if not ptext:
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
