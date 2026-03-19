# Roadmap

## Where we are

Nelson MCP v0.7 exposes 148 tools via MCP to cloud AI agents (Claude, ChatGPT, Gemini). It works well with large models that can handle many tools, but smaller local models (7B–14B) get confused by the tool count and protocol complexity. Custom endpoints help (static filtered subsets), but don't solve the underlying problem: small models need guidance, not just fewer options.

## Where we're going

**The mission: make small local models (7B–14B) as productive as GPT-4 or Claude on document tasks.**

A 70B cloud model can browse 148 tools and figure out the right sequence. A 7B local model can't — it needs to be guided step by step, with fewer choices at each point and clear suggestions for what to do next. Nelson should bridge that gap: not by dumbing down the tools, but by being smarter about how it presents them.

---

## v0.8 — Make small models productive

The core problem: a 7B model can't reliably pick from 25 tools, compose locators, and chain multi-step workflows. Nelson should do that work for it.

### Simple REST API (`/api/do`)

A single high-level endpoint for models that struggle with tool selection:

```json
POST /api/do
{
  "action": "insert_text",
  "heading": "Introduction",
  "position": "after",
  "content": "New paragraph text..."
}
```

Nelson resolves "Introduction" internally (heading lookup → bookmark → paragraph index → `insert_at_paragraph`). The model never sees paragraph indices, bookmarks, or locators. ~15 structured actions instead of 148 low-level tools.

### Tool broker (progressive disclosure)

Bring back the two-tier tool delivery, adapted for MCP:

- **Core tools** always visible: `list_open_documents`, `get_document_info`, `get_document_outline`, `do`, `request_tools`
- **Extended tools** unlocked on demand by intent: `request_tools(intent="edit")` adds editing tools to the session
- Intent groups: `navigate`, `edit`, `search`, `tables`, `images`, `styles`, `review`, `calc`, `draw`
- `tools/list` reflects the current session — starts small, grows as the agent asks
- Compatible with MCP `listChanged` notification

### Context-aware tool filtering

`tools/list` adapts to what's happening:
- No document open → only lifecycle tools (open, create, list recent)
- Writer document → Writer tools only (no Calc/Draw noise)
- First edit done → surface `undo`, `save_document`

### Pre-trained baseline rules

Nelson ships with a `rules.json` generated from reference sessions — not hand-written heuristics. During development, we run scripted scenarios (open document, navigate, edit, save; create spreadsheet, fill data, chart; etc.) against the tool suite, collect the traces, and mine them with PrefixSpan + Markov analysis.

The result: on first install, Nelson already knows the common workflows and suggests relevant `_next` actions. No user training needed, no "cold start" problem.

```
Dev time: scripted scenarios → traces → PrefixSpan/Markov → rules.json → shipped in .oxt
Runtime:  rules.json loaded at boot → _next suggestions from day one
```

The baseline covers generic patterns (Writer editing, Calc data entry, document lifecycle). As the user works, their own traces accumulate and refine the suggestions over time (see v0.9).

### Session trace collection

Nelson logs every tool call to a local SQLite database:

```sql
session_traces (session_id, seq, tool_name, doc_type, success, prev_tool, ts)
```

No telemetry, no cloud — just local data that accumulates alongside the baseline and eventually personalizes the suggestions.

---

## v0.9 — Learn from usage

v0.8 ships with baseline rules from reference sessions. v0.9 makes them personal: the user's own traces refine the baseline, and an offline LLM interprets the patterns into richer guidance. Same techniques (PrefixSpan, Markov), now applied to real usage data.

### Research foundations

This approach builds on well-established fields:

- **Process Mining** (van der Aalst, 2011) — extracting workflow models from event logs. Our session traces are classic event logs; algorithms like the Alpha Miner produce process graphs (Petri nets) from tool call sequences. Implementation: `pm4py` or lightweight custom miner.
- **Sequential Pattern Mining** (PrefixSpan, Pei et al. 2001) — finding frequent subsequences in logs. "80% of sessions that do A→B end up doing C" — more robust than counting bigrams.
- **Markov chains** — tool transitions form a natural Markov chain. The matrix `P(next_tool | current_tool, doc_type)` is computed directly from traces. No ML needed — pure statistics.
- **Voyager** (Wang et al. 2023) — Minecraft agent that builds a *skill library* from gameplay traces, analyzed by an LLM. Our `rules.json` is their skill library: patterns extracted from experience, refined over time.
- **LATM — LLM As Tool Maker** (Cai et al. 2023) — LLM identifies repetitive tool sequences and synthesizes composite tools. If `resolve_locator → get_heading_content → insert_at_paragraph` appears 50 times, the LLM can generate `insert_under_heading` as a reusable workflow.

### Three-level analysis

Pattern extraction runs in layers, each adding intelligence without requiring the next:

```
Level 1 — Statistics (zero deps, always on)
  Markov transition matrix from traces
  → P(next_tool | current_tool, doc_type)
  → Basic _next suggestions

Level 2 — Sequential mining (lightweight, on-demand)
  PrefixSpan on accumulated traces
  → Frequent multi-step workflows discovered
  → Anti-patterns detected (sequences ending in undo/failure)

Level 3 — LLM interpretation (offline, when GPU is free)
  Feed Level 1+2 outputs to LLM
  → Human-readable hints and reasons
  → Composite tool generation (LATM)
  → System prompt enrichment with proven workflows
```

Level 1 works from day one with just a few sessions. Level 2 kicks in after enough data accumulates. Level 3 runs only when the user's GPU is idle — no conflict with the client model.

### The learning cycle

```
Runtime                    Idle / on-demand              Next boot
─────────                  ────────────────              ─────────
Agent calls tools    →     L1: Markov matrix update      rules.json loaded
Traces saved to SQLite     L2: PrefixSpan mining    →    State machine applies rules
Zero overhead              L3: LLM interprets patterns   Zero overhead
                           (only when GPU is free)
```

### Output: `rules.json`

All three levels feed a single rules file, loaded at boot:

```json
[
  {
    "after": ["list_open_documents", "get_document_outline"],
    "doc_type": "writer",
    "suggest": ["get_heading_content", "find_text"],
    "confidence": 0.85,
    "source": "markov"
  },
  {
    "after": ["insert_at_paragraph"],
    "followed_by_undo_rate": 0.30,
    "hint": "Verify paragraph_index with resolve_locator before inserting",
    "source": "prefixspan"
  },
  {
    "pattern": "resolve_locator → get_heading_content → insert_at_paragraph → save",
    "name": "edit_section",
    "frequency": 0.60,
    "source": "llm",
    "composite_tool": true
  }
]
```

- **Workflow patterns** — common sequences that work, ranked by frequency and confidence
- **Anti-patterns** — sequences that lead to undo or failure, with corrective hints
- **Composite tools** — auto-generated high-level tools from repeated patterns (LATM)
- **Suggestion weights** — what to propose after each tool, specific to this user's habits and document types

### `_next` suggestions

Both MCP and `/api/do` return `_next` after every action, powered by the learned rules:

**MCP response:**
```json
{
  "result": { "paragraph_index": 12 },
  "_next": [
    {"tool": "get_heading_content", "args": {"heading": "Conclusion"}},
    {"tool": "save_document", "reason": "5 unsaved edits"}
  ]
}
```

**`/api/do` response:**
```json
{
  "result": { "ok": true },
  "_next": [
    {"action": "read", "heading": "Conclusion"},
    {"action": "save"}
  ]
}
```

Large cloud models can ignore `_next`. Small local models follow it like breadcrumbs — at each step, Nelson tells them exactly what makes sense next. A 7B model doesn't need to understand 148 tools if Nelson says "you just read a heading, here are the 3 things you can do now."

The effect: a small model guided by `_next` behaves like a much larger model that figured out the workflow on its own.

### System prompt enrichment

Nelson injects the most reliable workflow patterns into the MCP `instructions` field at initialize time, tailored to the active document type and endpoint. Instead of a generic "here are tools", the agent starts with: "to edit a section, do X→Y→Z. To insert an image, do A→B." Learned from real sessions, not hardcoded.

---

## v1.0 — Production ready

### Stability & trust

- **CI/CD pipeline** — automated build + test on push, release artifacts
- **Integration tests** — tool execution against a real LibreOffice instance (headless)
- **Range coordinate fix** — resolve the known Writer coordinate mismatch
- **Session authentication** — API keys for exposed endpoints

### Packaging & distribution

- **LibreOffice Extensions site** — publish on the official marketplace
- **Linux packages** — .deb/.rpm for distro repos
- **One-click installer** — bundled LibreOffice + Nelson for non-technical users

### Protocol

- **MCP resources** — expose document structure and gallery contents as browsable resources
- **MCP prompts** — predefined prompt templates for common tasks
- **WebSocket transport** — alternative to HTTP+SSE for persistent connections

---

## Beyond v1.0

- **Unified document index (idxV2)** — paragraph↔page cache with cursor tracking for instant navigation in large documents
- **RAG over galleries** — vector embeddings for semantic search across image and document libraries
- **AI slide generation** — outline-to-deck conversion from Writer documents
- **Multi-user sessions** — concurrent agents on different documents with session isolation
- **Cross-document workflows** — copy content between documents, merge, compare
