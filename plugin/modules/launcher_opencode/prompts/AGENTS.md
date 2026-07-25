# Nelson MCP — How to work with LibreOffice documents

You have access to Nelson MCP tools. These tools let you read, edit, and manage documents open in LibreOffice.

## Step 1: Find the document

First, check if a document is already open:

```
get_document_info()
```

If no document is open, find one to work with:

```
list_open_documents()        # see all open documents
get_recent_documents()       # see recently opened files
open_document(file_path="/home/user/mydoc.odt")   # open a file
create_document(doc_type="writer")                 # create new empty document
```

## Step 2: Read the document

For Writer documents, get the structure first:

```
get_document_tree(depth=0)   # shows all headings with bookmark IDs
```

This returns headings with `_mcp_` bookmark IDs like `_mcp_h1`, `_mcp_h2`, etc. Use these IDs to read specific sections:

```
get_heading_content(heading_path="1")        # read first heading section
text_read(start=0, count=20)           # read first 20 paragraphs
text_read(locator="heading_text:Annexes", count=10)  # read from a heading by name
text_read(locator="bookmark:_mcp_h3", count=10)      # read from a bookmark ID
text_search(query="budget")           # find text in document
```

## Step 3: Edit the document

Before editing, you need to unlock edit tools:

```
request_tools(intent="edit")
```

Now you can edit:

```
text_set(index=5, text="New text here")
text_insert(index=10, text="Inserted paragraph")
text_delete(index=3)
text_replace(find="old text", replace="new text")
```

## Step 4: Save

```
save_document()                                    # save to current file
save_document_as(target_path="/home/user/new.odt") # save as new file
export_pdf(path="/home/user/output.pdf")           # export as PDF
```

## Important rules

1. **Always call `get_document_info` first** to know what document you are working with. If no document is open, call `get_recent_documents` to find one, then `open_document` to open it.
2. **Read before you edit.** Always read the content before changing it.
3. **Use locators for navigation.** Many tools accept a `locator` parameter. Use `bookmark:_mcp_h1` (from `get_document_tree`) or `heading_text:Introduction` (by heading name). These are more reliable than paragraph numbers.
4. **Call `request_tools(intent="edit")` before editing.** Edit tools are not available by default.
5. **Style names depend on language.** Call `list_styles(family="paragraph")` to see available style names before applying styles.

## Working with tables

```
table_list()                          # see all tables
table_read(table_index=0)             # read first table
table_write_cell(table_index=0, cell="A1", value="Hello")  # write to cell
```

## Searching

```
text_search(query="word")                # simple text search
search_fulltext(query="budget AND 2024")        # advanced search with AND, OR, NOT
text_find(search_string="exact phrase")         # find exact text with position
```

## Batch edits

To make multiple changes at once, use `execute_batch`:

```
execute_batch(operations=[
  {"tool": "text_set", "args": {"index": 0, "text": "Title"}},
  {"tool": "text_set", "args": {"index": 1, "text": "Subtitle"}},
  {"tool": "text_insert", "args": {"index": 2, "text": "New paragraph"}}
])
```

## Other useful tools

- `get_document_stats()` — word count, page count, paragraph count
- `image_list()` / `image_insert()` — work with images
- `list_comments()` / `add_comment()` — work with comments
- `set_track_changes(enabled=false)` — disable auto track changes temporarily (enabled by default on MCP mutations)
- `list_bookmarks()` — see all bookmarks in the document
