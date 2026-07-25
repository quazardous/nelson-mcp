# Writing Good Tool Descriptions

Guidelines for writing MCP tool descriptions that help AI clients use tools effectively.

## Principles

### 1. Embed behavioral guarantees in the summary

State what the tool preserves or guarantees directly in the description line:

```
"Find and replace text (preserves formatting)"
"Replace the entire text of a paragraph (preserves style)"
```

If `text_apply_range` with `target="search"` preserves character formatting (bold, color, font), say so — otherwise the AI will unnecessarily re-specify formatting.

### 2. Explain the "why", not just the "what"

Tell the AI *why* it should choose one approach over another:

- "Bookmarks are stable across edits" — explains why bookmarks are preferred over paragraph indices
- "LO strips search string to plain to match" — prevents confusing failures when searching formatted text

### 3. Add usage hints in parameter descriptions

Brief inline hints help the AI use parameters correctly:

```python
"depth": {"description": "Levels: 1=direct children, 2=two levels, 0=unlimited (default: 1)"}
"count": {"description": "Consecutive paragraphs to duplicate (default: 1)"}
```

### 4. Return context in search results

When returning search matches, include surrounding content so the AI can verify it found the right place before editing.

## Workflow patterns for system prompts

These patterns should appear in system prompts or AGENTS.md:

```
REVIEW WORKFLOW: set_track_changes(enabled=true) → make edits →
get_tracked_changes → accept_all_changes or reject_all_changes →
set_track_changes(enabled=false).

TABLE WORKFLOW: table_list → table_read → table_write_cell for targeted edits.
For new tables or full rewrites, use text_apply_range with HTML/Markdown table.

STYLE WORKFLOW: list_styles (discover exact localized names) → apply style by name.
```
