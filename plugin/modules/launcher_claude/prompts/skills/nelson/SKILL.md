---
name: nelson
description: Quick reference for Nelson MCP — LibreOffice document tools
---

# Nelson MCP — Quick Reference

## Workflow: Discover → Navigate → Edit

### 1. Discover
```
get_document_info          → doc type, title, path
get_document_tree          → heading structure + _mcp_ bookmarks (depth=0 for all)
get_document_stats         → word count, page count, etc.
list_available_tools       → see extended tools you can activate
request_tools(intent=...)  → activate: navigate, edit, review, media
```

### 2. Navigate
```
get_heading_children       → body + sub-headings under a heading
navigate_heading           → next, previous, parent, first_child, next_sibling
text_read            → read N paragraphs from a position
search_fulltext            → boolean search: "energy AND renewable", "ocean NEAR/3 warming"
get_surroundings           → nearby paragraphs, images, tables around a locator
```

### 3. Edit
```
text_apply_range     → insert/replace (supports Markdown). target: search, full, range, beginning, end
text_set         → replace one paragraph's text (keeps style)
text_insert        → insert before/after/replace at locator
text_insert_batch    → insert multiple paragraphs at once
text_delete           → delete by index or locator
text_replace        → find & replace with regex, preserves formatting
```

### 4. Tables
```
table_list → table_read → table_write_cell (A1, B2...)
table_create(rows, cols, locator)
```

### 5. Images
```
image_list → image_info
image_insert(image_path, locator)
image_replace / image_set / image_delete
```

### 6. Comments & Review
```
list_comments / add_comment / resolve_comment
set_track_changes(enabled=true/false)
get_tracked_changes / accept_all_changes / reject_all_changes
scan_tasks → find TODO-AI, FIX, QUESTION in comments
```

### 7. Batch
```
execute_batch(operations=[...])
  → Use $last for previous paragraph_index
  → Use $step.N for step N's result
```

## Locators (stable addressing)
- `bookmark:_mcp_xxx` — best, created by get_document_tree
- `heading_text:Introduction` — find by heading text
- `paragraph:N` — fallback, 0-based index

## Tips
- Call `style_list` before applying styles — names are localized
- Use `document_health_check` to detect structural issues
- Use `text_get_range(scope="selection")` to read the user's current selection
