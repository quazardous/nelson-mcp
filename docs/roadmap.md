# Roadmap

## Where we are

Nelson MCP v0.7 exposes 148 tools via MCP to cloud AI agents (Claude, ChatGPT, Gemini). It works well with large models that can handle many tools, but smaller local models (7B–14B) get confused by the tool count and protocol complexity. Custom endpoints help (static filtered subsets), but don't solve the underlying problem: small models need guidance, not just fewer options.

## Where we're going

The next versions shift Nelson from a passive tool server ("here are 148 tools, figure it out") to an active collaborator that adapts to the agent's capabilities and guides it through workflows.

---

## v0.8 — Make small models productive

The core problem: a 7B model can't reliably pick from 25 tools, compose locators, and chain multi-step workflows. Nelson should do that work for it.

### Tool broker (progressive disclosure)

Bring back the two-tier tool delivery from the chatbot era, adapted for MCP:

- **Core tools** (always visible): `list_open_documents`, `get_document_info`, `get_document_outline`, `do`, `request_tools`
- **Extended tools** unlocked on demand by intent: `request_tools(intent="edit")` adds editing tools to the session, `request_tools(intent="tables")` adds table tools
- Intent groups: `navigate`, `edit`, `search`, `tables`, `images`, `styles`, `review`, `calc`, `draw`
- `tools/list` reflects the current session — starts small, grows as the agent asks for more
- Compatible with MCP `listChanged` notification so clients refresh their tool list

### Simple REST API (`/api/do`)

A single high-level endpoint for models that struggle with tool selection:

```json
POST /api/do
{
  "action": "insert_text",
  "where": "after heading Introduction",
  "content": "New paragraph text..."
}
```

Nelson resolves "after heading Introduction" internally (heading lookup → bookmark → paragraph index → `insert_at_paragraph`). The model never sees paragraph indices, bookmarks, or locators.

Actions: `read`, `insert_text`, `replace_text`, `delete`, `insert_image`, `find`, `list_headings`, `read_table`, `write_table`, etc. ~15 high-level verbs instead of 148 low-level tools.

### Context-aware tool filtering

`tools/list` adapts to what's happening:
- No document open → only lifecycle tools (open, create, list recent)
- Writer document → Writer tools only (no Calc/Draw noise)
- Agent just did `get_document_outline` → suggest editing tools next
- Agent seems stuck → surface `request_tools` hint

---

## v0.9 — Server-side intelligence

Nelson stops waiting for the agent to figure things out and starts helping.

### Workflow engine

Pre-wired multi-step workflows exposed as single tools:

- `replace_section(heading, new_content)` — resolves heading, reads current content, deletes it, inserts new content, preserves styles
- `move_paragraph(from, to)` — reads, deletes, inserts at destination
- `summarize_and_insert(heading, target)` — reads section, calls LLM summary, inserts result
- `format_as_table(paragraph_range)` — detects tabular text, converts to proper table

Each workflow wraps 3–5 tool calls in a single undo context.

### Proactive suggestions

After each tool call, Nelson can return `_suggestions`: a list of likely next actions based on what just happened.

```json
{
  "result": { ... },
  "_suggestions": [
    {"action": "read_next_section", "reason": "You just read the introduction"},
    {"action": "insert_image", "reason": "This section has no images"}
  ]
}
```

Agents can ignore suggestions, but small models benefit from the guidance.

### Local LLM router

For users running Ollama: Nelson routes internal tasks to the right model automatically:
- Fast small model (3B) for tagging, classification, intent detection
- Larger model (8B+) for summaries, content generation, translation
- CLIP for image descriptions

The user configures models once; Nelson picks the right one per task.

---

## v1.0 — Production ready

### Stability & trust

- **CI/CD pipeline** — automated build + test on push, release artifacts
- **Integration tests** — test tool execution against a real LibreOffice instance (headless)
- **Range coordinate fix** — resolve the known Writer coordinate mismatch
- **Session authentication** — API keys or OAuth for exposed endpoints

### Packaging & distribution

- **LibreOffice Extensions site** — publish on the official marketplace
- **Linux packages** — .deb/.rpm for distro repos
- **One-click installer** — bundled LibreOffice + Nelson for non-technical users

### Protocol evolution

- **MCP resources** — expose document structure, gallery contents, and config as browsable resources
- **MCP prompts** — predefined prompt templates ("summarize this document", "review my changes")
- **WebSocket transport** — alternative to HTTP+SSE for persistent connections

---

## Beyond v1.0

- **Unified document index (idxV2)** — paragraph↔page cache with cursor tracking for instant navigation in large documents. Code exists (disabled), needs stabilization
- **RAG over galleries** — vector embeddings for semantic search across image and document libraries
- **AI slide generation** — outline-to-deck conversion from Writer documents
- **Multi-user sessions** — concurrent agents on different documents with session isolation
- **Cross-document workflows** — copy content between documents, merge, compare
