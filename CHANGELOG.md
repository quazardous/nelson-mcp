# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **`fit_image` tool** (#10) — auto-fit a Writer image using its real content aspect ratio (read server-side from the embedded image data, so it stays correct even after a manual rotation). `fit="width"`/`"height"` keep one dimension and recompute the other; `fit="frame"` fits the image to its parent text frame's inner width and resizes the frame height to match. Resets cropping
- **`wrap_image_in_frame` tool** (#12) — wrap an existing frameless Writer image into a captioned text frame, preserving size/rotation/anchor. Reuses the embedded image data directly, so it works even when the source file path is unknown
- **Image rotation** (#9) — `set_image_properties` gains a `rotation` parameter (degrees clockwise), mapped to Writer's `GraphicRotation`
- **`get_image_info` enrichment** (#12) — now returns `native_width_px`, `native_height_px`, `native_ratio` (real content ratio) and `rotation`, plus an `OriginURL` fallback for the otherwise-empty `graphic_url`

### Changed

- **`replace_image` adapts to aspect ratio** (#8) — by default (`fit="width"`) it now resets cropping and recomputes the height from the new image's aspect ratio, so portrait↔landscape swaps are no longer distorted. `fit="height"` keeps the height; `fit="exact"` preserves the previous behaviour (old frame size). Explicit `width_mm`/`height_mm` still override

## [0.8.2] — 2026-04-08

### Fixed

- **Dynamic gallery sync** — adding/removing image or document folders in Options takes effect immediately (no restart needed). Both `images_folder` and `documents_folder` now subscribe to `config:changed`

## [0.8.1] — 2026-04-08

### Added

- **Scripts framework** — scripts are now declared in `module.yaml` with tags (`install`, `auto`, `once`, `button`, `visible`, `pause`). Centralized launch via `plugin/framework/deps.py` and `plugin/framework/terminal.py`. Build validates declared scripts vs files
- **`sqlite3_ctypes`** — pure-Python DB-API 2.0 wrapper using `ctypes.CDLL` to load `sqlite3.dll` directly. No `.pyd` needed — works on all Windows machines regardless of LO's custom `python312.dll`. Bundled `sqlite3.dll` v3.51.3 from sqlite.org (FTS5 included)
- **Build ID** — each `.oxt` is stamped with a `timestamp-hash` for traceability (visible in first log line)
- **BUILD_TAG** — `plugin/version.py` supports patch release suffixes (e.g. `nelson-0.8.1-2.oxt`)
- **SQLite3 status check** — Options > Nelson MCP shows `[OK] sqlite3 3.51.3` or `[FAIL]`
- **`NELSON_LOG_LEVEL`** — env var overrides configured log level
- **`NELSON_SQLITE3_DLL`** — env var overrides sqlite3 DLL path
- **Dynamic gallery sync** — adding/removing image or document folders in Options takes effect immediately (no restart needed)

### Changed

- **Log level deferred** — configured log level is applied after bootstrap completes, so all boot messages are visible
- **`make deploy`** uses `build-force` (no stale docker cache)
- **Versioned `.oxt`** — build output is `nelson-0.8.1.oxt` (was `nelson.oxt`)

### Fixed

- **sqlite3 on Windows** (#3) — `_sqlite3.pyd` from both pysqlite3 and LO fails to load due to missing symbols in LO's `python312.dll`. Replaced with pure-ctypes approach + bundled DLL

## [0.7.2] — 2026-03-29

### Added

- **`requires_service` tool attribute** — tools can declare a service dependency (`requires_service = "images"`). If the service has no registered instances, the tool is hidden from `tools/list`. Applied to image gallery (6 tools), document gallery (6 tools), and AI image generation (2 tools). Agents on a fresh install without galleries configured see only relevant tools

### Fixed

- **Tailscale tunnel not starting on fresh Windows installs** — LibreOffice's Python may not inherit the user's full PATH. `_find_tailscale()` now checks `C:\Program Files\Tailscale\` and `%LOCALAPPDATA%\Tailscale\` before falling back to bare `tailscale` name

## [0.7.1] — 2026-03-19

### Added

- **HTML help system** — `generate_help.py --html` converts module docs to static HTML pages with sidebar navigation. Bundled in .oxt at `help/`, opened from Help menu entry via default browser
- **How-To guides** — 4 guides in `docs/howto/`: Connect ChatGPT via Tailscale, Generate images with Forge, Index photos with Ollama, Set up an image gallery
- **Help menu entry** — "Help" action in Nelson menu opens HTML help index in browser

### Changed

- **Makefile `docs` target** — switched from `--xhp` to `--html`
- **Help sidebar nav** — left-side fixed panel with section headers (How-To / Modules), one link per line, GitHub link at top

## [0.7.0] — 2026-03-19

### Added

- **Custom MCP endpoints** — configurable filtered endpoints in Options > MCP. Each endpoint exposes a subset of tools (one per line in textarea). Presets available: minimal (8), writer-edit (25), writer-read (15), calc (20), gallery (10). Useful for smaller LLMs (fixes #2)
- **Tool reference page** — `/api/tools` HTML endpoint with searchable tool documentation, auto-generated from schemas. "Tool Reference" button in Options opens it
- **Undo support** — all MCP mutations wrapped in `UndoContext`, Ctrl+Z reverts entire tool operation. Each action has a unique `_action_id` visible in undo history and MCP results
- **MCP bridge** — `dev/mcp-bridge/server.py` stdio-to-HTTP proxy with auto re-initialize on 409, `-Xutf8` for Windows UTF-8
- **Dev Docker build** — persistent `nelson-dev` container with `docker exec`, Make targets with file dependencies (skip vendor/manifest/icons if unchanged). `make build` from PowerShell works
- **md2xhp converter** — `tools/md2xhp/md2xhp.py` converts Markdown subset to LibreOffice XHP help format (headings, lists, code, notes, inline formatting)
- **PageMap** (idxV2, disabled) — sparse paragraph↔page cache with interpolation, kept as commented code for future unified index

### Changed

- **Insert image with frame + caption** — TextFrame wraps image + caption (AS_CHARACTER + CharHeight 1 pattern). Aspect ratio always preserved, `max_height_mm` default 160
- **follow_activity** — uses `goto_paragraph` (same as panel Show), disabled complex PageMap estimation
- **Cache invalidation** — moved AFTER tool execution (tool uses valid cache). Prebuild at boot with retry + status bar
- **`_enrich_result` simplified** — no scanning, no PageMap estimation, no `vc.getPage()` in hot paths
- **Makefile** — Docker dev container (`make dev-up`), PowerShell compatible (`make deploy` works from PS), `make rebuild` forces clean build, `build_oxt.py --check` skips if up to date
- **Menu groups** — `menu_group` field on modules, sorted with separators (ai, network, tools). Debug menu removed
- **Deploy** — polls log + health instead of `sleep 12`, pip-cache Docker volume

### Fixed

- **Viewport jump on insert** — `lockControllers` during `get_paragraph_ranges` enumeration, cache invalidation after (not before) tool execution
- **Panel Show freeze** — uses cached `find_paragraph_element` instead of full enumeration
- **Idle rebuild loop** — disabled (idxV2), was causing infinite cursor events

## [0.6.1] — 2026-03-18

### Added

- **Insert image with frame + caption** — Writer images are wrapped in a TextFrame with auto-caption (description > title > filename). Aspect ratio always preserved, `max_height_mm` default 160 for portrait images. `caption=false` for standalone mode
- **PageMap** — sparse `{para_index → page}` cache with linear interpolation for fast navigation. Self-correcting: enriched by every goto_paragraph, tool result, and cursor movement
- **Cursor tracker** — `XSelectionChangeListener` on the document controller tracks `current_page` in real-time, zero overhead
- **MCP bridge** — `dev/mcp-bridge/server.py`: stdio-to-HTTP proxy with auto re-initialize on 409, `-Xutf8` for Windows UTF-8 support
- **Systematic result enrichment** — `_enrich_result` adds `paragraph_index`, `_page`, `_bookmark` to every Writer tool response. Calc gets `_sheet`, Draw/Impress gets `_page_index`. All resolved from cached data (no scan)
- **Ollama install scripts** — `install.ps1` / `install.sh` for detect/install/pull model

### Changed

- **follow_activity works** — auto-scrolls to mutation location via `jumpToPage` (instant) or `goto_paragraph` (PageMap-assisted). Tools return `paragraph_index` for the event
- **goto_paragraph** — iterative page jumps via PageMap instead of O(n) scan. Skips jump if already on correct page, skips gotoRange if already at paragraph
- **Panel "Show" button** — uses PageMap-based goto_paragraph (no freeze)
- **Cache invalidation preserves PageMap** — PageMap is a flexible guide, not a binary cache. Never cleared on mutation, self-corrects via observations
- **Deploy** — polls `/health` + log marker instead of `sleep 12`. Returns immediately when ready

### Fixed

- **Post-insertion freeze** — `_enrich_result` no longer calls `goto_paragraph` or `find_heading_for_paragraph` (both triggered full para scan after cache invalidation). Uses PageMap estimation + cached bookmark map instead
- **ActionLog nested args** — resolves `writer.paragraph_index` for panel "Show" button
- **UTF-8 in MCP bridge** — `-Xutf8` flag fixes accent corruption on Windows

## [0.6.0] — 2026-03-17

### Added

- **AI text module** — `plugin/modules/ai` with `AiService` registry, `LlmProvider` ABC, instance-based provider management
- **Ollama provider** — `plugin/modules/ai_ollama` with list_detail instances, start/stop menu, detect/install scripts (ps1/sh), create preset button, combo_text model selector
- **Multi-pass AI indexation** — 3-pass pipeline: CLIP caption (pass 1), folder universe via LLM (pass 2), per-image contextual tags via LLM (pass 3)
- **Hierarchical folder universe** — pass 2 processes top-down (root first), parent universe propagated as context to child folders
- **Categorized themes** — pass 2 produces structured tags (context/activities/places/people) instead of flat generic lists, avoiding vague tags like "outdoor", "people", "scenic"
- **Template manager** — `plugin/framework/template_manager.py` with `{placeholder}` substitution, per-module `templates/` directory, language variant support
- **Indexation language config** — `ai_images.index_language` option to force tag language (French, English, etc.) with auto-detect fallback
- **Folder context files** — pass 2 reads all `.txt`/`.md` files in a folder as context, with LLM summary if content exceeds 2000 chars
- **Per-image context** — `<image>.txt` sidecar files injected into pass 3 prompt
- **CLIP noise removal** — pass 3 asks LLM to identify and remove CLIP hallucinations (art movements, artist names) via `"remove"` field
- **`combo_text` widget** — split combo for Options: select dropdown + editable text field, with listener sync. Works in list_detail item fields
- **`menu_group`** — modules declare their menu group; menus sorted by group with separators between groups (ai, network, tools)
- **`index_stage` column** — tracks which passes have been completed per image, with schema version check and auto-reset on mismatch

### Changed

- **Indexer menu** — two toggle entries "Pass 1 — Image AI (CLIP)" and "Pass 2 — Text AI (LLM)" with per-pass stop label
- **Non-blocking launch** — indexation starts directly in background job, no more HTTP check freezing the LO main thread
- **Status bar progress** — real partial fill (X/Y per image), not flash-to-100%
- **ImageMagick subprocess** — `CREATE_NO_WINDOW` on Windows (no flashing terminal)
- **DB reset** — soft reset via `DELETE FROM` instead of `os.remove` (fixes Windows file lock)
- **HTTP Server menu** — actions wrapped in submenu
- **Debug menu removed** — actions available via `/api/debug` endpoint only

## [0.5.1] — 2026-03-17

### Added

- **`GET /health` endpoint** — readiness probe returning version, session ID, tool count, active document, and `default_save_dir` for agent bootstrapping
- **`_resolved` context in all tool responses** — every response includes `_resolved` (doc_id, doc_type, title) and `_session` so agents always know which document was targeted
- **Structured error codes** — all errors now include `code`, `message`, `hint`, `retryable` fields (e.g. `document_not_found`, `unsaved_document`, `incompatible_doc_type`, `invalid_params`, `server_busy`, `execution_timeout`)
- **Enum suggestions on validation** — invalid enum values trigger "Did you mean 'X'?" hints using Levenshtein distance (e.g. `chart_type: "lines"` → `Did you mean 'line'?`)
- **`default_save_dir` resolution** — `DocumentService.get_default_save_dir()` resolves the best save directory: document gallery folder → LibreOffice `$(work)` path → `~/Documents`
- **Batch step timings** — `execute_batch` results include per-step `elapsed_ms`

### Fixed

- **Save path bug** — `_save_to_path` now normalizes paths (`expanduser`, `abspath`), creates parent directories, and adds the `Overwrite` property
- **"Save As" semantics** — `storeToURL` + `.uno:SaveAs` dispatch fallback ensures the document adopts its new file path (URL, title, modified state all updated). Previously `storeToURL` alone would export a copy without updating the document's internal URL
- **`save_document_as` description** — corrected from "save a copy" to "save as" (document adopts the new path)
- **Validation errors in Actions panel** — `tool:failed` events now emitted for parameter validation and doc_type incompatibility errors, so they appear in the sidebar panel
- **Session validation** — stale `Mcp-Session-Id` now returns `409 Conflict` with structured error instead of being silently accepted

### Changed

- **`save_document` error on unsaved docs** — now returns `default_save_dir` and example path in the hint instead of a generic "use File > Save As" message
- **`create_document` path tip** — description suggests using `get_recent_documents` to discover valid directories on the target machine

## [0.5.0] — 2026-03-17

### Added

- **Document IDs** — every document gets a persistent `NelsonDocId` (UUID stored in UserDefinedProperties). Survives save, save-as, and close+reopen. Returned by `create_document`, `open_document`, `list_open_documents`, and `get_document_info`
- **`_document` meta-parameter** — all tools accept an optional `_document` parameter to target a specific document instead of the active one. Supports `id:<doc_id>`, `path:<file_path>`, `title:<frame_title>`, or bare 32-char hex doc_id
- **Multi-document awareness** — `get_document_info` now includes `_other_open_documents` hint listing other open docs with their `doc_id`, title, and type
- **`save_document` first-save support** — accepts an optional `path` parameter to save unsaved documents for the first time (no more "Use File > Save As" error)
- **`create_document` with `path`** — optional `path` parameter to create and save a document in a single call (recommended to avoid ambiguity with multiple unsaved docs)
- **`read_log` tool (mcp-dev)** — new tool in the dev MCP proxy to read Nelson and LibreOffice logs with level/pattern filtering, so agents can diagnose friction without filesystem access

### Changed

- **`enumerate_open_documents` helper** — centralized in DocumentService, used by `list_open_documents` (replaces per-tool frame enumeration)
- **`_document` URI resolution** — protocol handler activates the matching frame before tool execution, so all existing tools benefit from document targeting without code changes
- **`_document` schema injection** — `schema_convert.py` auto-injects the `_document` parameter into all tools with `requires_doc=True`
- **Error messages** — `save_document` on unsaved docs now suggests the `path` parameter and lists supported extensions

## [0.4.1] — 2026-03-14

### Added

- **Document gallery** — new `documents` and `documents.folder` modules, mirroring the image gallery architecture with provider registry, folder provider, and SQLite+FTS5 indexing
- **Document gallery tools** — `docs_gallery_list`, `docs_gallery_get`, `docs_gallery_search`, `docs_gallery_providers`, `docs_gallery_update`, `docs_folder_rescan` (all `requires_doc=False`)
- **Document metadata extraction** — reads title, description, subject, keywords, creator, page count, word count, character count, paragraph count, image count, table count from ODF (`meta.xml` + `document-statistic`) and OOXML (`docProps/core.xml` + `app.xml`) via pure stdlib `zipfile` — no LibreOffice needed
- **Document metadata writing** — `docs_gallery_update` writes title, description, subject, keywords into ODF and OOXML files via zip rewriting (atomic temp-file swap); supports creating `docProps/core.xml` when absent
- **Document type filter** — `docs_gallery_list` and `docs_gallery_search` accept `doc_type` filter (writer, calc, impress, draw, other)
- **Document index** — SQLite+FTS5 database per folder (`~/.config/nelson/documents_<hash>.db`) with incremental mtime-based scanning, same pattern as image gallery

## [0.4.0] — 2026-03-13

### Added

- **Follow activity** — `core.follow_activity` config option auto-scrolls the document view to the location of MCP mutation operations (page granularity). Subscribes to `tool:completed` events; only triggers for MCP-caller mutations with a `paragraph_index` in the result
- **BM25 search ranking** — `search_fulltext` now scores results using BM25 relevance (IDF + term frequency normalization) with 2× heading boost, replacing the previous unranked set intersection
- **Search heading context** — `search_in_document` enriches results with nearest heading bookmark via `writer_tree.enrich_search_results()`
- **Panel "Show" button** — Actions panel now tracks `paragraph_index` per entry and shows a "Show" button to navigate to the paragraph of a completed action
- **Tunnel status dialog** — redesigned with separate MCP and SSE endpoint URLs, per-field copy buttons, and provider name in menu text
- **Options tab support** — modules with many settings can use tabs in their Options page; shared layout constants in `plugin/_layout.py`
- **`tool:completed` event enrichment** — EventBus now passes `is_mutation` and `doc` to `tool:completed` subscribers

### Changed

- **Mutation detection** — extended `_READ_PREFIXES` with `resolve_`, `navigate_`, `goto_`, `scan_`, `check_`, `export_`, `print_`, `document_health` so these tools are no longer misclassified as mutations
- **`get_page_count`** — now uses `model.getPropertyValue("PageCount")` (no cursor movement) instead of `jumpToLastPage()` with save/restore

### Fixed

- **Viewport stability on read operations** — all tools that resolve page numbers via the view cursor (`get_document_tree`, `get_document_stats`, `list_images`, `get_page_objects`, `search_fulltext` with pages, `resolve_locator page:`) now properly save/restore the viewport position using the pattern: save page + lock → work → unlock → `jumpToPage(saved_page)` + `gotoRange(saved)`
- **`annotate_pages` nested locking** — refactored from per-node `get_page_for_paragraph` calls (each locking/unlocking) to a single lock cycle with cached `para_ranges`
- **`list_images_writer` viewport jump** — wrapped image enumeration in a single lock cycle with save/restore after unlock
- **`_build_page_map` (fulltext search)** — added cursor restore after unlock
- **`get_page_objects` viewport jump** — added cursor save/restore around view cursor page resolution
- **Options handler early logging** — ensures nelson logger has a handler when `options_handler.py` loads before `main.py`

## [0.3.3] — 2026-03-10

### Added

- **Slide placeholders** — `list_placeholders`, `get_placeholder_text`, `set_placeholder_text` for Impress/Draw with role detection (title, subtitle, body) via ClassName or positional heuristic
- **`write_cell_range`** — bulk-write a 2D array of values to Calc cells (strings, numbers, booleans, formulas, null)
- **Hyperlink edit/remove** — `edit_hyperlink` and `remove_hyperlink` for Writer (inline HyperLinkURL + TextField.URL) and Calc (cell text fields)
- **`requires_doc` attribute** — `ToolBase.requires_doc = False` allows `create_document`, `open_document`, `list_open_documents`, `get_recent_documents` to work when no document is open

### Fixed

- **`create_document` with no doc open** — MCP protocol no longer blocks tools when no document is open; checks `requires_doc` attribute before rejecting
- **`insert_hyperlink` Writer** — fixed `IllegalArgumentException` by using inline `HyperLinkURL` property instead of `TextField.URL` via `insertTextContent()`
- **`insert_hyperlink` Calc double kwargs** — filtered shared params from kwargs to avoid `got multiple values` error
- **Conditional formatting entry parsing** — `_entry_to_dict()` now uses `XSheetCondition` interface methods (getOperator/getFormula1/getFormula2) instead of broken `getPropertyValues()`

## [0.3.2] — 2026-03-10

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
- **Writer table tools** — `delete_table`, `set_table_properties` (equal columns, custom column widths, alignment, repeat header, background color, width), `add_table_rows`, `add_table_columns`, `delete_table_rows`, `delete_table_columns`, `write_table_row`
- **Calc chart tools** — `list_charts`, `get_chart_info`, `edit_chart`, `delete_chart` for managing embedded charts on sheets
- **Calc conditional formatting** — `list_conditional_formats`, `add_conditional_format`, `remove_conditional_format`, `clear_conditional_formats` via `XSheetConditionalEntries`
- **Impress/Draw master slides** — `list_master_slides`, `get_slide_master`, `set_slide_master` for master page management
- **Hyperlink tools** — `list_hyperlinks` and `insert_hyperlink` for Writer (URL text fields + inline HyperLinkURL) and Calc (cell text fields)

### Changed

- **Image tools unified** — `insert_image`, `list_images`, `get_image_info`, `delete_image` now work on all document types; non-Writer docs support `shape_index` lookup; `insert_image` uses doc-type namespacing for placement params
- **Validation order fix** — `ToolRegistry.execute()` now validates parameters before `_flatten_doc_type_params()`, so nested doc-type objects validate correctly against the schema

- **Styles tools unified** — `list_styles` and `get_style_info` now work on all document types (Writer, Calc, Draw, Impress) via `XStyleFamiliesSupplier`; auto-discovers available families when called without `family` param
- **Shape tools unified** — `create_shape`, `edit_shape`, `delete_shape`, `get_draw_summary` now work on all document types with drawing layer support; use doc-type namespacing for page/sheet selection
- **Draw tools support Impress** — all `doc_types = ["draw"]` updated to `["draw", "impress"]` for pages and slide tools
- **`download_image` unlocked** — now available on all document types (no UNO dependency)

### Fixed

- **close_document context loss** — closing a document no longer loses MCP context; `CloseDocument` now enumerates remaining frames and activates the next document via `frame.activate()`
- **Cache deploy missing icons** — `make cache` now syncs `build/generated/assets/` (PNG icons generated from SVG) into the extension cache

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
