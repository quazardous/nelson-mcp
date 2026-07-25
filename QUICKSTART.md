# Nelson MCP — Agent Quickstart

This guide helps LLM agents (ChatGPT, Claude, Gemini, etc.) use Nelson MCP effectively. It covers connection, tool discovery, and common workflows.

## Connect

Nelson MCP runs as an HTTP server inside LibreOffice on port 8766.

```json
{
  "mcpServers": {
    "nelson": {
      "type": "http",
      "url": "http://localhost:8766/mcp"
    }
  }
}
```

For remote access via Tailscale tunnel: `https://your-machine.tail1234.ts.net/mcp`

## Getting Started — Discovery Phase

When you first connect, you don't know what the user has. **Explore before acting.** Follow this discovery sequence:

### Step 1 — What's already open?

```
doc_list_open
```

Returns all documents currently open in LibreOffice with their `doc_id`, title, type, and file path. This is your starting point. If documents are open, the user likely wants to work on one of them.

### Step 2 — What was recently used?

```
doc_recent
```

Returns the user's recently opened documents (from LibreOffice history). Useful when nothing is open or the user mentions a document by name — you can find its path here and open it.

### Step 3 — What's available in galleries?

If document or image gallery tools are available, explore what the user has indexed:

```
docgallery_list           → browse indexed document folders
docgallery_search("report")  → search documents by content/metadata
gallery_providers                     → list configured image galleries
gallery_query(action="list")          → browse images in a gallery
gallery_query(action="search", ...)   → search images by keywords
gallery_query(action="get", ...)      → full metadata for one image
```

Galleries give you access to files the user has organized — you can open documents or insert images from them.

### Step 4 — Understand the active document

Once you know which document to work on, get its structure:

```
doc_info           → page count, word count, type, path
nav_outline        → heading tree with bookmarks (Writer)
table_list                 → sheets (Calc) or tables (Writer)
```

For Writer documents, `nav_outline` is essential — it gives you the heading hierarchy and stable bookmark references you'll use for all subsequent operations.

### Decision Tree

```
Connected
 ├─ doc_list_open
 │   ├─ Documents open → doc_info / nav_outline
 │   └─ Nothing open
 │       ├─ User names a doc → doc_recent → doc_open
 │       ├─ User wants to find a doc → docgallery_search
 │       └─ User wants a new doc → doc_create
 └─ User mentions images → gallery_query(action="search"|"list")
```

### Example: First Exchange

User says: *"Add a summary to my report"*

```
1. doc_list_open          → find "Annual Report 2025.odt" (doc_id: abc123)
2. nav_outline(_document="id:abc123")
                                → headings: Introduction, Chapter 1, Chapter 2, Conclusion
3. nav_heading_content(heading="Conclusion")
                                → read existing content
4. text_insert(index=N, text="## Summary\n\nKey findings...", position="before")
```

Don't skip steps 1-3. Without discovery, you risk creating a new document when one is already open, or inserting text in the wrong place.

## Target a Specific Document

All tools accept an optional `_document` parameter to target a document other than the active one:

- `_document: "id:abc123..."` — by Nelson doc ID (best, survives save-as)
- `_document: "title:My Report"` — by window title (partial match)
- `_document: "path:C:/Users/me/doc.odt"` — by file path

When working with multiple documents, always specify `_document` to avoid ambiguity.

## Writer Workflows

### Read a Document

```
nav_outline        → heading tree with bookmarks
nav_heading_content         → read text under a specific heading
text_read             → read paragraphs by index range
text_find / text_search → search for text
```

**Tip:** Use `nav_outline` first to understand the document structure. Headings have stable bookmarks — use `heading_text:` or `bookmark:` locators to target sections.

### Edit a Document

```
text_insert         → insert text/HTML at a position
text_set          → replace a paragraph's content
text_set_style         → apply a style (Heading 1, Body Text, etc.)
text_delete            → remove a paragraph
text_insert_batch     → insert multiple paragraphs at once
```

**Tip:** Use `nav_resolve` to convert a heading name or bookmark to a paragraph index before editing. Example: `nav_resolve(locator="heading_text:Chapter 3")` returns the paragraph index.

### Tables

```
table_list                        → find tables in the document
table_list(table_name="Table1")   → read that table's content
table_create                      → create a new table
table_write_cell                  → write to a specific cell
table_write_row                   → write an entire row
table_structure(action=, axis=)   → add/delete rows or columns
```

### Images

```
image_list                 → find images in the document
image_insert                → insert an image (with caption)
gallery_query               → browse, search or inspect gallery images
```

### Review Workflow

```
change_set(enabled=true)
  → make edits (insert, delete, modify)
change_list         → see all changes
change_accept_all          → accept
change_set(enabled=false)
```

### Styles

Always discover available styles first — names are localized:

```
style_list(family="ParagraphStyles")  → list available styles
text_set_style(index=5, style="Heading 1")
```

## Calc Workflows

```
calc_sheet(action="list")         → list sheets
calc_sheet(action="create"|"rename"|"delete"|"switch")
calc_read_range("A1:D10")         → read a cell range
calc_write_range                  → write values to a range
calc_write_formula                → write formulas or values
calc_chart(action="create", ...)  → create a chart
calc_search(action="search"|"replace")
```

## Batch Operations

Use `batch_execute` to run multiple tools in one call. Supports variable chaining:

```json
{
  "steps": [
    {"tool": "nav_outline", "output_var": "outline"},
    {"tool": "nav_heading_content", "args": {"heading": "Introduction"}}
  ]
}
```

## Undo

All mutations support `doc_undo`. If something goes wrong:

```
doc_undo    → revert last MCP operation (one Ctrl+Z)
doc_redo    → re-apply if needed
```

## Tool Presets

Custom endpoints may expose a subset of tools. Common presets:

| Preset | Tools | Best for |
|--------|-------|----------|
| minimal | 8 | Basic document read/write |
| writer-edit | 25 | Full Writer editing |
| writer-read | 14 | Read-only Writer access |
| calc | 13 | Spreadsheet operations |
| gallery | 10 | Image gallery browsing |

If you're on a custom endpoint, use `tools/list` to see which tools are available.

## Common Patterns

### "Add text under heading X"

```
1. nav_outline          → find heading bookmark
2. nav_resolve("heading_text:X")  → get paragraph index
3. text_insert(index=N+1, text="...", position="after")
```

### "Replace a paragraph"

```
1. text_find("old text")         → find paragraph index
2. text_set(index=N, text="new text")
```

### "Insert an image from gallery"

```
1. gallery_query(action="search", query="sunset beach") → find image path
2. image_insert(path="/path/to/image.jpg", paragraph_index=10)
```

### "Create a report from scratch"

```
1. doc_create(type="writer", path="C:/Users/me/report.odt")
2. text_insert_batch(paragraphs=[
     {"text": "Monthly Report", "style": "Heading 1"},
     {"text": "Summary of findings...", "style": "Body Text"}
   ])
3. doc_save
```

## Tips

- **Bookmarks over indices** — paragraph indices shift when content is added/deleted. Use heading bookmarks or `nav_resolve` for stable references.
- **Check doc_type** — tools are filtered by document type. A Writer tool won't appear on a Calc document.
- **Batch when possible** — `batch_execute` reduces round-trips and runs faster.
- **Read before writing** — always read the current state before making edits to avoid overwriting content.
