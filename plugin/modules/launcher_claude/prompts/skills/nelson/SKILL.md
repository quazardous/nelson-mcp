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
read_paragraphs            → read N paragraphs from a position
search_fulltext            → boolean search: "energy AND renewable", "ocean NEAR/3 warming"
get_surroundings           → nearby paragraphs, images, tables around a locator
```

### 3. Edit
```
apply_document_content     → insert/replace (supports Markdown). target: search, full, range, beginning, end
set_paragraph_text         → replace one paragraph's text (keeps style)
insert_at_paragraph        → insert before/after/replace at locator
insert_paragraphs_batch    → insert multiple paragraphs at once
delete_paragraph           → delete by index or locator
replace_in_document        → find & replace with regex, preserves formatting
```

### 4. Tables
```
list_tables → read_table → write_table_cell (A1, B2...)
create_table(rows, cols, locator)
```

### 5. Images
```
list_images → get_image_info
insert_image(image_path, locator)
replace_image / set_image_properties / delete_image
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
- Call `list_styles` before applying styles — names are localized
- Use `document_health_check` to detect structural issues
- Use `get_document_content(scope="selection")` to read the user's current selection
