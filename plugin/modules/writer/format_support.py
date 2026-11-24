# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Format conversion helpers for Writer tools.

Handles exporting documents as markdown/HTML, importing formatted
content via ``insertDocumentFromURL``, format-preserving text
replacement, and text search utilities.
"""

import contextlib
import logging
import os
import re
import tempfile

log = logging.getLogger("nelson.writer")


# ---------------------------------------------------------------------------
# Format configuration
# ---------------------------------------------------------------------------

FORMAT_CONFIG = {
    "markdown": {"filter": "Markdown", "extension": ".md"},
    "html": {"filter": "HTML (StarWriter)", "extension": ".html"},
}

# System temp directory (cross-platform).
TEMP_DIR = tempfile.gettempdir()


def _get_format(config_svc=None):
    """Return the configured export format (``'markdown'`` or ``'html'``).

    ``core.document_format`` in Options; ``'markdown'`` when unset or
    unknown (#2650).
    """
    if config_svc is not None:
        try:
            fmt = config_svc.get("core.document_format", caller_module=None)
            if fmt and fmt in FORMAT_CONFIG:
                return fmt
        except Exception:
            pass
    return "markdown"


def resolve_export_format(config_svc=None, requested=None):
    """The format to read a document out in: the call's, else the setting."""
    if requested in FORMAT_CONFIG:
        return requested
    return _get_format(config_svc)


# HTML is recognised by its tags; a '<' in prose ("a < b") is not a tag.
_HTML_TAG = re.compile(
    r"<(?:!doctype|/?(?:html|body|head|p|br|hr|h[1-6]|ul|ol|li|table|thead|"
    r"tbody|tr|td|th|div|span|b|i|u|s|strong|em|a|img|pre|code|blockquote|"
    r"sup|sub|font|center)\b)[^>]*>", re.IGNORECASE)

_MARKDOWN_LINE = re.compile(
    r"^(?:#{1,6}\s|\s*[-*+]\s+\S|\s*\d+[.)]\s+\S|\s*>\s|\s*\|.*\||"
    r"```|\s*[-*_]{3,}\s*$)", re.MULTILINE)
_MARKDOWN_INLINE = re.compile(
    r"\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\)")


def detect_content_format(content):
    """``'html'``, ``'markdown'`` or ``None`` (plain text) for *content*.

    HTML wins when both appear: a '#' or '*' inside HTML is text, while
    tags inside Markdown are rare and LibreOffice's Markdown import would
    show them literally anyway.
    """
    if not isinstance(content, str) or not content.strip():
        return None
    if _HTML_TAG.search(content):
        return "html"
    if _MARKDOWN_LINE.search(content) or _MARKDOWN_INLINE.search(content):
        return "markdown"
    return None


def resolve_import_format(content, requested=None):
    """The filter to import *content* with: the call's format if given,
    else what the content looks like. Plain text keeps the HTML path, which
    turns blank lines into paragraphs (#2635: never the global setting)."""
    if requested in FORMAT_CONFIG:
        return requested
    return detect_content_format(content) or "html"


# ---------------------------------------------------------------------------
# UNO helpers (import inside functions to avoid import-time dependency)
# ---------------------------------------------------------------------------

def _file_url(path):
    """Return a ``file://`` URL for *path*."""
    import urllib.parse
    import urllib.request
    return urllib.parse.urljoin(
        "file:", urllib.request.pathname2url(os.path.abspath(path))
    )


def _create_property_value(name, value):
    """Create a ``com.sun.star.beans.PropertyValue``."""
    import uno
    p = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    p.Name = name
    p.Value = value
    return p


@contextlib.contextmanager
def _with_temp_buffer(content=None, fmt="html"):
    """Context manager that yields ``(path, file_url)`` for a temp file
    with the extension of *fmt*.

    If *content* is not ``None`` it is written to the file.
    The file is deleted on exit.
    """
    ext = FORMAT_CONFIG.get(fmt, FORMAT_CONFIG["html"])["extension"]
    fd, path = tempfile.mkstemp(suffix=ext, dir=TEMP_DIR)
    try:
        if content is not None:
            if isinstance(content, list):
                content = "\n".join(str(x) for x in content)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            os.close(fd)
        yield (path, _file_url(path))
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _strip_html_boilerplate(html_string):
    """Extract content between ``<body>`` tags if present."""
    if not html_string or not isinstance(html_string, str):
        return html_string
    match = re.search(
        r"<body[^>]*>(.*?)</body>", html_string, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return html_string


def _wrap_html_fragment(html_content):
    """Wrap an HTML fragment in a full document structure for LO's filter."""
    if not html_content or not isinstance(html_content, str):
        return html_content
    has_html = "<html" in html_content.lower() and "</html>" in html_content.lower()
    has_body = "<body" in html_content.lower() and "</body>" in html_content.lower()
    if has_html and has_body:
        return html_content
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '<meta charset="UTF-8">\n</head>\n<body>\n'
        "%s\n</body>\n</html>" % html_content
    )


def _ensure_html_linebreaks(content):
    """Convert newlines to ``<br>``/``<p>`` when content is plain text
    and the active format is HTML, so LO's filter preserves them.
    """
    if not isinstance(content, str) or not content:
        return content
    import html as html_mod

    unescaped = html_mod.unescape(content)
    html_tags = [
        "<p>", "<br>", "</h1>", "</h2>", "</h3>",
        "</ul>", "</li>", "</div>", "<html>",
    ]
    has_html = any(tag in unescaped.lower() for tag in html_tags)
    if has_html:
        return _wrap_html_fragment(unescaped)

    content = re.sub(r"\n{3,}", "\n\n", content)
    paras = content.split("\n\n")
    out = []
    for p in paras:
        if not p.strip():
            continue
        p_html = p.replace("\n", "<br>\n")
        out.append("<p>%s</p>" % p_html)
    return _wrap_html_fragment("\n".join(out))


# ---------------------------------------------------------------------------
# Document -> content
# ---------------------------------------------------------------------------

# com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK
_PARAGRAPH_BREAK = 0


def document_to_content(model, ctx, services, max_chars=None,
                        scope="full", range_start=None, range_end=None,
                        fmt=None):
    """Export a Writer document (or part of it) as markdown/HTML.

    Args:
        model: UNO document model.
        ctx: UNO component context.
        services: ServiceRegistry.
        max_chars: Truncate result to this length.
        scope: ``'full'``, ``'selection'``, or ``'range'``.
        range_start: Character offset start (for scope ``'range'``).
        range_end: Character offset end (for scope ``'range'``).

    Returns:
        Content string.
    """
    config_svc = services.get("config") if services else None
    fmt = resolve_export_format(config_svc, fmt)

    if scope == "selection":
        from plugin.modules.writer.ops import get_selection_range
        start, end = get_selection_range(model)
        return _finish(_export_copy(model, ctx, fmt, start, end) or "",
                       fmt, max_chars)

    if scope == "range":
        start = int(range_start) if range_start is not None else 0
        end = int(range_end) if range_end is not None else 0
        doc_len = services.document.get_document_length(model) if services else 0
        start = max(0, min(start, doc_len))
        end = min(end, doc_len)
        return _finish(_export_copy(model, ctx, fmt, start, end) or "",
                       fmt, max_chars)

    # scope == "full"
    try:
        filter_name = FORMAT_CONFIG[fmt]["filter"]
        content = None
        from plugin.modules.writer import equations
        if equations.math_objects(model):
            content = _export_copy(model, ctx, fmt)
        if content is None:
            with _with_temp_buffer(None, fmt) as (path, file_url):
                props = (_create_property_value("FilterName", filter_name),)
                model.storeToURL(file_url, props)
                with open(path, "r", encoding="utf-8",
                          errors="replace") as f:
                    content = f.read()
        return _finish(content, fmt, max_chars)
    except Exception as exc:
        log.debug("document_to_content (full) failed: %s", exc)
        return ""


def _finish(content, fmt, max_chars):
    if fmt == "html":
        content = _strip_html_boilerplate(content)
    if max_chars and len(content) > max_chars:
        content = content[:max_chars] + "\n\n[... truncated ...]"
    return content


def _export_copy(model, ctx, fmt, start=None, end=None):
    """Export a hidden copy of *model*, cut to ``[start, end)`` if given.

    Two things the filters cannot do on the document itself:

    - a part of it: the copy is cut to the range, offsets as text_find
      gives them, so formatting, tables and tracked changes come out as in
      a full export. This replaced a rebuild from paragraph strings, which
      lost all of that (GitHub #49);
    - equations as text: the Markdown and HTML filters write an equation as
      its picture, base64 inside the text. In the copy each one becomes a
      plain-letter token, which no filter escapes, and the tokens become
      [equation: <StarMath>] afterwards.

    Returns None when the export failed.
    """
    import html as html_mod
    from plugin.modules.writer import equations
    from plugin.modules.writer.ops import get_text_cursor_at_range

    copy = None
    odt_fd, odt_path = tempfile.mkstemp(suffix=".odt", dir=TEMP_DIR)
    os.close(odt_fd)
    try:
        model.storeToURL(_file_url(odt_path), (
            _create_property_value("FilterName", "writer8"),))
        desktop = ctx.getServiceManager().createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)
        copy = desktop.loadComponentFromURL(
            _file_url(odt_path), "_blank", 0,
            (_create_property_value("Hidden", True),))
        # The copy inherits change recording: cuts and tokens would come
        # out as tracked deletions and insertions.
        try:
            copy.setPropertyValue("RecordChanges", False)
        except Exception:
            pass
        if start is not None:
            if end is None or end <= start:
                return ""
            text = copy.getText()
            kept = get_text_cursor_at_range(copy, start, end)
            if kept is None:
                return None
            tail = text.createTextCursorByRange(kept.getEnd())
            tail.gotoEnd(True)
            tail.setString("")
            head = text.createTextCursorByRange(kept.getStart())
            head.gotoStart(True)
            head.setString("")
        markers = {}
        for i, obj in enumerate(equations.math_objects(copy).values()):
            token = "NelsonEquation%05dMarker" % i
            markers[token] = "[equation: %s]" % equations.source(obj)
            anchor = obj.getAnchor()
            anchor.getText().insertString(anchor.getStart(), token, False)
            anchor.getText().removeTextContent(obj)
        with _with_temp_buffer(None, fmt) as (path, file_url):
            copy.storeToURL(file_url, (_create_property_value(
                "FilterName", FORMAT_CONFIG[fmt]["filter"]),))
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        for token, marker in markers.items():
            if fmt == "html":
                marker = html_mod.escape(marker, quote=False)
            content = content.replace(token, marker)
        return content
    except Exception as exc:
        log.debug("export of a copy failed: %s", exc)
        return None
    finally:
        if copy is not None:
            try:
                copy.close(True)
            except Exception:
                pass
        try:
            os.unlink(odt_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Content -> Document
# ---------------------------------------------------------------------------

def insert_content_at_position(model, ctx, content, position,
                               config_svc=None, fmt=None):
    """Insert formatted content at *position* (``'beginning'``,
    ``'end'``, or ``'selection'``) using ``insertDocumentFromURL``.
    """
    fmt = resolve_import_format(content, fmt)
    if fmt == "html":
        import html as html_mod
        content = html_mod.unescape(content)
        content = _ensure_html_linebreaks(content)

    with _with_temp_buffer(content, fmt) as (_path, file_url):
        text = model.getText()
        cursor = text.createTextCursor()

        if position == "beginning":
            cursor.gotoStart(False)
        elif position == "end":
            cursor.gotoEnd(False)
        elif position == "selection":
            try:
                controller = model.getCurrentController()
                sel = controller.getSelection()
                if sel and sel.getCount() > 0:
                    rng = sel.getByIndex(0)
                    rng.setString("")
                    cursor.gotoRange(rng.getStart(), False)
                else:
                    vc = controller.getViewCursor()
                    cursor.gotoRange(vc.getStart(), False)
            except Exception:
                cursor.gotoEnd(False)
        else:
            raise ValueError("Unknown position: %s" % position)

        filter_name = FORMAT_CONFIG[fmt]["filter"]
        filter_props = (_create_property_value("FilterName", filter_name),)
        cursor.insertDocumentFromURL(file_url, filter_props)


def replace_full_document(model, ctx, content, config_svc=None, fmt=None):
    """Clear the document and insert *content*."""
    fmt = resolve_import_format(content, fmt)
    if fmt == "html":
        import html as html_mod
        content = html_mod.unescape(content)
        content = _ensure_html_linebreaks(content)

    with _with_temp_buffer(content, fmt) as (_path, file_url):
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        cursor.setString("")
        cursor.gotoStart(False)
        filter_name = FORMAT_CONFIG[fmt]["filter"]
        filter_props = (_create_property_value("FilterName", filter_name),)
        cursor.insertDocumentFromURL(file_url, filter_props)


def apply_content_at_range(model, ctx, content, start, end,
                           config_svc=None, fmt=None):
    """Replace character range ``[start, end)`` with rendered *content*."""
    from plugin.modules.writer.ops import get_text_cursor_at_range

    cursor = get_text_cursor_at_range(model, start, end)
    if cursor is None:
        raise ValueError(
            "Invalid range or could not create cursor for (%d, %d)" % (start, end)
        )

    fmt = resolve_import_format(content, fmt)
    if fmt == "html":
        import html as html_mod
        content = html_mod.unescape(content)
        content = _ensure_html_linebreaks(content)

    with _with_temp_buffer(content, fmt) as (_path, file_url):
        cursor.setString("")
        filter_name = FORMAT_CONFIG[fmt]["filter"]
        filter_props = (_create_property_value("FilterName", filter_name),)
        cursor.insertDocumentFromURL(file_url, filter_props)


def apply_content_at_search(model, ctx, content, search,
                            all_matches=False, case_sensitive=True,
                            config_svc=None, fmt=None):
    """Find *search* in the document and replace with rendered *content*.

    Returns the number of replacements made.
    """
    fmt = resolve_import_format(content, fmt)
    prepared = content
    if fmt == "html":
        import html as html_mod
        prepared = html_mod.unescape(content)
        prepared = _ensure_html_linebreaks(prepared)

    with _with_temp_buffer(prepared, fmt) as (_path, file_url):
        filter_name = FORMAT_CONFIG[fmt]["filter"]
        filter_props = (_create_property_value("FilterName", filter_name),)

        sd = model.createSearchDescriptor()
        sd.SearchString = search
        sd.SearchRegularExpression = False
        sd.SearchCaseSensitive = case_sensitive

        count = 0
        found = model.findFirst(sd)
        while found:
            text_obj = found.getText()
            cursor = text_obj.createTextCursorByRange(found)
            cursor.setString("")
            cursor.insertDocumentFromURL(file_url, filter_props)
            count += 1
            if not all_matches:
                break
            found = model.findNext(cursor.getEnd(), sd)
            if count > 200:
                break
        return count


# ---------------------------------------------------------------------------
# Text search
# ---------------------------------------------------------------------------

def find_text_ranges(model, ctx, search, start=0, limit=None,
                     case_sensitive=True):
    """Find occurrences of *search*, returning a list of
    ``{"start": int, "end": int, "text": str}`` dicts.
    """
    try:
        sd = model.createSearchDescriptor()
        sd.SearchString = search
        sd.SearchRegularExpression = False
        sd.SearchCaseSensitive = case_sensitive

        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        if start > 0:
            _GO_RIGHT_CHUNK = 8192
            remaining = start
            while remaining > 0:
                n = min(remaining, _GO_RIGHT_CHUNK)
                cursor.goRight(n, False)
                remaining -= n

        # Searching finds tracked deletions too; flag those matches, as the
        # text no longer reads that way (GitHub #48).
        from plugin.modules.writer import tracked_text
        deleted = tracked_text.deletions(model)

        matches = []
        found = model.findNext(cursor, sd)
        while found:
            measure = found.getText().createTextCursor()
            measure.gotoStart(False)
            measure.gotoRange(found.getStart(), True)
            m_start = len(measure.getString())
            matched_text = found.getString()
            m_end = m_start + len(matched_text)
            match = {"start": m_start, "end": m_end, "text": matched_text}
            if deleted and tracked_text.in_deletion(found, deleted):
                match["in_deletion"] = True
            matches.append(match)
            if limit and len(matches) >= limit:
                break
            found = model.findNext(found, sd)
        return matches
    except Exception as exc:
        log.debug("find_text_ranges failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Markup detection & format-preserving replacement
# ---------------------------------------------------------------------------

def content_has_markup(content):
    """Return ``True`` if *content* appears to contain Markdown or HTML."""
    return detect_content_format(content) is not None


def replace_preserving_format(model, target_range, new_text, ctx=None):
    """Replace text in *target_range* with *new_text* character by
    character, preserving per-character formatting (bold, italic,
    font, color, etc.).

    Each single-character ``setString()`` inherits ALL character
    properties from the character it replaces.

    Two cases take a plain replace instead (the new text takes the format
    of the first character):

    - change recording is on: a deleted character stays in the text, so a
      character-by-character pass shifts on every one and garbles the
      result ("closes" -> "ends" read "Deltandses"); one deletion and one
      insertion is also what a reviewer wants to see;
    - the range holds an object (an equation): it has no character in the
      string, so the two would not line up.

    Positions are taken from the range itself. They used to come from
    goRight() from the top of the body, which drifted past equations and
    was wrong for a range in a table cell.
    """
    text = target_range.getText()
    old_text = target_range.getString()
    old_len = len(old_text)
    new_len = len(new_text)

    if old_len == 0 and new_len == 0:
        return
    if old_len == 0:
        cursor = text.createTextCursorByRange(target_range.getStart())
        text.insertString(cursor, new_text, False)
        return

    probe = text.createTextCursorByRange(target_range.getStart())
    probe.goRight(old_len, True)
    if _recording(model) or probe.getString() != old_text:
        cursor = text.createTextCursorByRange(target_range)
        cursor.setString(new_text)
        return

    overlap = min(old_len, new_len)

    # Optional toolkit for UI responsiveness.
    toolkit = None
    if ctx:
        try:
            toolkit = ctx.getServiceManager().createInstanceWithContext(
                "com.sun.star.awt.Toolkit", ctx
            )
        except Exception:
            pass

    main_cursor = text.createTextCursorByRange(target_range.getStart())

    for i in range(overlap):
        if i > 0 and i % 500 == 0 and toolkit:
            try:
                toolkit.processEvents()
            except Exception:
                toolkit = None

        if new_text[i] == old_text[i]:
            main_cursor.goRight(1, False)
            continue

        ins = text.createTextCursorByRange(main_cursor)
        ins.goRight(1, False)
        text.insertString(ins, new_text[i], False)

        deleter = text.createTextCursorByRange(main_cursor)
        deleter.goRight(1, True)
        deleter.setString("")

        main_cursor.goRight(1, False)

    # main_cursor now sits after the first *overlap* characters.
    if new_len > old_len:
        text.insertString(main_cursor, new_text[old_len:], False)
    elif old_len > new_len:
        leftover = text.createTextCursorByRange(main_cursor)
        leftover.goRight(old_len - new_len, True)
        leftover.setString("")


def _recording(model):
    try:
        return bool(model.getPropertyValue("RecordChanges"))
    except Exception:
        return False
