# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.3.1] — 2026-03-10

### Added

- **Impress detection** — `detect_doc_type()` now returns `"impress"` for Impress documents (previously conflated with `"draw"`), enabling future Impress-specific tools
- **`is_impress()` helper** — new method on `DocumentService` for explicit Impress type checks
- **Doc-type parameter namespacing** — `_flatten_doc_type_params()` in `ToolRegistry` allows tools to declare doc-type-specific params as nested objects (`"writer": {...}`, `"calc": {...}`) that are auto-flattened before execution
- **`get_draw_page()` bridge function** — resolves the correct `DrawPage` for any document type (Writer single page, Calc per-sheet, Draw/Impress multi-page)
- **Tool coverage analysis** — `docs/analysis/tool-coverage.md` with UNO API overlap research, unification roadmap, and doc-type namespacing design
- **Calc search tools** — `search_in_spreadsheet` and `replace_in_spreadsheet` with per-sheet and all-sheets modes
- **Calc comment tools** — `list_cell_comments`, `add_cell_comment`, `delete_cell_comment` via `XSheetAnnotation` API
- **Calc navigation tools** — `list_named_ranges` and `get_sheet_overview` (used area, charts, annotations, shapes)
- **Impress speaker notes** — `get_speaker_notes` and `set_speaker_notes` (first Impress-only tools)
- **Impress transitions** — `get_slide_transition` and `set_slide_transition` with 25 FadeEffect types, speed, auto-advance duration
- **Impress layouts** — `get_slide_layout` and `set_slide_layout` with 30 named layout types
- **Print tool** — `print_document` for all document types via `XPrintable`
- **Undo/Redo tools** — `undo` and `redo` for all document types via `XUndoManager`
- **`graphic_query.py` framework helper** — cross-document image listing/lookup via `getGraphicObjects()` (Writer) and DrawPage shape iteration (Calc/Draw/Impress)

### Changed

- **Image tools unified** — `insert_image`, `list_images`, `get_image_info`, `delete_image` now work on all document types; non-Writer docs support `shape_index` lookup; `insert_image` uses doc-type namespacing for placement params
- **Validation order fix** — `ToolRegistry.execute()` now validates parameters before `_flatten_doc_type_params()`, so nested doc-type objects validate correctly against the schema

- **Styles tools unified** — `list_styles` and `get_style_info` now work on all document types (Writer, Calc, Draw, Impress) via `XStyleFamiliesSupplier`; auto-discovers available families when called without `family` param
- **Shape tools unified** — `create_shape`, `edit_shape`, `delete_shape`, `get_draw_summary` now work on all document types with drawing layer support; use doc-type namespacing for page/sheet selection
- **Draw tools support Impress** — all `doc_types = ["draw"]` updated to `["draw", "impress"]` for pages and slide tools
- **`download_image` unlocked** — now available on all document types (no UNO dependency)

### Removed

- **Broker tools** — deleted `list_available_tools` and `request_tools` (legacy chatbot feature, was broken — missing `get_tool_summaries`/`get_tool_names_by_intent` methods)

## [0.3.0] — 2026-03-07

### Added

- **HTTP client utilities** — `plugin/framework/http_client.py` with shared `parse_endpoint()`, `http_request()`, `http_json()` used by all image providers
- **HTTP helper functions** — centralized `read_json_body()`, `send_json()`, `send_cors_headers()` in `http_server.py`, eliminating 3× duplication across modules
- **Config API gate** — `http.enable_config_api` option (disabled by default) controls `/api/config` endpoint exposure
- **Debug API gate** — `debug.enable_api` option (disabled by default) controls `/api/debug` endpoint exposure
- **Debug module HTTP API** — `/api/debug` endpoint moved from MCP protocol to dedicated debug module with eval, exec, call_tool, trigger, services, config actions
- **AI images indexer** — `plugin/modules/ai_images/indexer.py` for CLIP-based gallery auto-tagging
- **SD WebUI scripts** — install, launch, and stop scripts for Forge/A1111

### Changed

- **Type hints** — added to all framework base classes (`ToolBase`, `ServiceBase`, `ModuleBase`, `ToolContext`, `EventBus`, `ServiceRegistry`) and provider ABCs (`ImageProvider`, `GalleryProvider`)
- **SD WebUI provider** — refactored to use shared `http_json()`, proper connection cleanup via `try/finally`
- **OpenAI provider** — refactored to use shared `http_json()`, removed raw `http.client` usage
- **Silent error handling** — replaced bare `except: pass` with `log.debug(..., exc_info=True)` across indexer, sdapi module, and service registry
- **Debug endpoint path** — renamed from `/debug` to `/api/debug` for consistency with `/api/config`
- **MCP protocol cleanup** — removed debug handlers from `mcp/protocol.py` (now in debug module)

### Security

- `/api/config` and `/api/debug` endpoints are now **disabled by default** — must be explicitly enabled in Options

## [0.2.1] — 2026-03-05

### Added

- **Options page scrollbar** — pages with overflowing content now get a vertical scrollbar at runtime
- **Ollama model selector** — OpenCode config has a dropdown populated from installed Ollama models

### Changed

- **Windows launcher fixes** — proper `CREATE_NEW_CONSOLE` subprocess, PowerShell quoting for args with spaces, "Press Enter to close" on exit
- **Recent documents tool** — rewritten to use LO configuration registry (`PickList` history)
- **Sidebar panel background** — reads system DialogColor from LO theme instead of hardcoded value (fixes black background on Windows)
- **Launcher CWD defaults** — empty CWD field now shows the default path via `default_provider`; helper says "Clear to restore default"
- **OpenCode AGENTS.md** — rewritten for small local models: step-by-step workflow, concrete tool call examples, locator patterns (`bookmark:`, `heading_text:`)

### Removed

- `--continue` flag from OpenCode default args (caused stale session issues)

## [0.2.0] — 2026-03-05

### Added

- **Sidebar panel factory** with Actions and Jobs panels in the Nelson deck
- **Job manager** — framework-level background task runner with `get_job` / `list_jobs` tools
- **AI image generation/editing tools** — `generate_image` and `edit_image` submit background jobs, with gallery auto-save and configurable filename templates
- **Launcher modules** — Claude Code, Gemini CLI, and OpenCode launchers with install scripts and prompt templates
- **Panel module** — UNO panel factory registration for sidebar panels
- **Options widgets**: `button` (with optional confirm dialog), `check` (runtime status display), multiline helpers
- **Folder gallery tools**: `rescan` tool, rescan/reset buttons in Options, `rescan_on_startup` config toggle
- `.mcp.json-dist` template for MCP server configuration

### Changed

- Refactored `generate_manifest.py` — extracted `_emit_field` / `_add_widget` to deduplicate XDL generation across pages, inline children, and list_detail dialogs
- About dialog now shows the extension logo and updated GitHub URL (`nelson-mcp`)
- `constants.py` URLs updated to `quazardous/nelson-mcp`
- Folder gallery provider supports `dest_name` with subdirectory creation
- `FolderIndex.scan()` accepts `force` flag for full re-index
- AI Horde provider passes `prompt_strength` parameter

## [0.1.0] — 2026-03-05

### Changed

- Project renamed from **LocalWriter** to **Nelson**. Version numbering reset to 0.1.0 to reflect the new project identity. Previous versions (1.x) refer to the LocalWriter era.

## [1.7.3] — 2026-02-28

### Changed

- Sidebar panels use programmatic Python layout instead of XDL files (fixes cross-VCL-backend rendering issues on KDE/Qt)
- Added `plugin/framework/panel_layout.py` with `create_panel_window()` and `add_control()` helpers
- Removed `LocalWriterDialogs/` (XDL sidebar dialogs no longer needed)
- Cross-renderer testing documentation in DEVEL.md and AGENTS.md

## [1.7.2] — 2026-02-27

### Changed

- Chat spinner: braille circling dot animation
- Removed `chatbot.show_panel` option (LO sidebar API limitation)
- `description.xml` generated from template (`description.xml.tpl`)
- Release process documented in AGENTS.md and DEVEL.md

## [1.7.0] — 2026-02-27

### Added

- Inline submodule config: `config_inline: true` merges fields onto parent page with labeled separators
- `config_inline` accepts explicit module name (e.g., `config_inline: main`) for cross-module grouping
- Page titles (bold) and helpers on all module config pages
- Automatic cleanup of stale XDL files during build

### Changed

- Tunnel submodules (bore, cloudflare, ngrok, tailscale) inlined onto parent Tunnel page
- Core and debug modules inlined onto Main page
- Writer and calc modules inlined onto Doc page
- Renamed module `common` to `doc`
- Bold title (font-weight 150) and semibold separator labels (font-weight 110) via `dlg:styles`

### Fixed

- `get_provider_options()` missing `services` parameter (tunnel provider dropdown was empty)
- Options handler early return on modules with no own config but with inline children
- Submodules with no visible config fields no longer show empty separators

## [1.6.0] — 2026-02-26

### Added

- Tool broker: two-tier tool delivery with core tools always sent, extended tools on demand
- Intent-based tool grouping: 78 extended tools tagged (navigate/edit/review/media)
- Meta-tools: `request_tools(intent="...")` and `list_available_tools()`
- Lazy probe: Enter sends without tools, auto-retries if LLM needs them
- Chat vs Do modes: Enter=lazy, Ctrl+Enter=force tools, status label hint
- BROKER_HINT in system prompt to guide LLM on intent activation
- Ollama model pull/status support
- Cross-platform Makefile, Windows dev setup scripts

### Changed

- OpenAI streaming improvements
- Broker logging in streaming.py (broker vs classic mode)

## [1.5.1] — 2026-02-25

### Changed

- Unified streaming + tool-calling loop into `chat_event_stream()` generator in `streaming.py`
- Panel and HTTP API chatbot handlers now consume the same NDJSON event stream

## [1.5.0] — 2026-02-25

### Added

- Document context strategies (full/page/tree/stats/auto) with config `chatbot.context_strategy`
- Session summary compression: older messages condensed when history exceeds 24K chars
- Chatbot HTTP API module (`chatbot_api`): REST/SSE endpoints for external integrations
- Debug module: System Info and Test AI Providers actions (conditional on `debug.enabled`)
- Dummy AI provider (`ai_dummy`): Homer Simpson mode for testing (streams "D'oh!")
- Enter-to-send in chat panel (Shift+Enter for newline), configurable via `chatbot.enter_sends`
- Query input history with up/down arrow keys, persisted across sessions
- EndpointImageProvider: separate image instance when `image: true` on ai_openai instances
- Model name displayed in AI Settings dropdown labels
- `internal: true` support in module.yaml config fields (hidden from Options UI, stored in registry)

### Changed

- AI Settings panel: fixed height, inline labels ("Text AI" / "Image AI") next to dropdowns
- AI Settings panel: wider dropdowns, better vertical spacing

## [1.4.0] — 2026-02-25

### Changed

- Removed `LlmService` and `ImageService` shims — `AiService` is the sole AI service
- Moved provider ABCs (`LlmProvider`, `ImageProvider`) from `core/services/` to `ai/provider_base.py`
- Writer image tools use `services.ai.generate_image()` directly (no more `services.image`)
- Module dependencies: `chatbot`, `writer`, `draw` now require `ai` instead of `llm`/`image`
- AI provider modules no longer declare `provides_services: [llm]` or `[image]`
- Core module no longer provides `llm` or `image` services

## [1.3.0] — 2026-02-25

### Added

- AI Settings sidebar panel with dropdown selects for Text AI and Image AI instances
- Volatile instance selection: sidebar changes are session-only, Options panel sets persistent defaults
- `AiService.set_active_instance()` / `get_active_instance()` for volatile overrides
- Dynamic status display in query label ("Ask (Ready)", "Ask (...)")

### Changed

- Renamed config keys `ai.text_instance` / `ai.image_instance` → `ai.default_text_instance` / `ai.default_image_instance`
- Chat panel: removed "Chat:" response label, response area starts at top
- Chat panel: query label shows status instead of separate status field
- Sidebar panel order: AI Settings first, Chat with Document second
- Dropdown controls created programmatically via `addControl()` for proper rendering in sidebar

## [1.2.0] — 2026-02-25

### Added

- Unified AI service (`plugin/modules/ai/`) with model catalog, instance registry, and capability-based routing
- Flat model catalog format: each model has `ids` (provider-specific IDs) and `capability` field
- `resolve_model_id()` helper for provider-aware model ID resolution
- YAML model files support both new flat format and old grouped format (backward-compatible)
- `providers` field on custom models to restrict visibility to specific providers
- Endpoint-based image provider (`ai_openai/image_provider.py`)
- Menus, dialogs, icons, and dispatch handler via module manifests
- `generate_manifest.py`: XDL dialog generation, Addons.xcu menus, Accelerators.xcu shortcuts
- Options handler: list_detail widget, file picker, number spinner, dynamic options_provider
- Chatbot module: panel factory, dialog-based settings, multi-instance support
- Document service helpers (`core/services/document.py`)
- Example YAML model files in `contrib/yaml/`

### Changed

- Renamed AI modules: `openai_compat` → `ai_openai`, `ollama` → `ai_ollama`, `horde` → `ai_horde`
- Model catalog: nested `{provider: {cap: [...]}}` dict → flat list with `ids`/`capability` per model
- Deduplicated cross-provider models (Llama 3.3, Mistral Large, GPT-OSS, Mistral 7B, Pixtral Large)
- `get_model_catalog(providers=)` accepts provider key list instead of single `provider_type`
- AI module `get_model_options()` functions now use provider-filtered catalog

### Removed

- Old status bar icons (`running_*.png`, `starting_*.png`, `stopped_*.png`)

## [1.1.1] — framework branch

> The master port is not yet complete.

### Added

- Modular plugin framework with service registry, tool registry, event bus, and YAML-based module manifests
- 39 tools ported from mcp-libre (editing, search, images, frames, workflow, lifecycle, impress, diagnostics)
- HTTP server, tunnel, batch, writer navigation, and writer index modules

### Changed

- Architecture: flat `core/` monolith → modular `plugin/framework/` + `plugin/modules/`
- Config: `localwriter.json` → per-module YAML schemas with LibreOffice native Options panel
- Build: `build.sh` → `Makefile` + Python scripts (cross-platform)

### Removed

- `core/` directory, root-level `main.py`/`chat_panel.py`, custom settings dialogs
- `localwriter.json.example`, `build.sh`, root `META-INF/`
- `pricing.py`, `eval_runner.py` (not yet ported)

### Fixed

- UNO context going stale — now uses fresh `get_ctx()` on every call
- `search_in_document` regex compilation and result counting
- `set_image_properties` crop parameter handling
