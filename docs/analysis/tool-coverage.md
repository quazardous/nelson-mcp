# Nelson MCP — Tool Coverage Analysis

> Generated 2026-03-10 from codebase v0.3.0

## 1. Overview

Nelson MCP exposes **110 tools** across 4 supported LibreOffice document types. Tools are organized with intent metadata (navigate, edit, review, media).

### Tool count by document type

| Doc type | Dedicated tools | Shared (all types) | Total accessible |
|----------|----------------:|--------------------:|-----------------:|
| Writer   | 62              | 28                  | **90**           |
| Calc     | 14              | 28                  | **42**           |
| Draw     | 9               | 28                  | **37**           |
| Impress  | 9 (= Draw)      | 28                  | **37**           |
| Math     | 0               | 28                  | **28** (degraded)|

```
Writer  ██████████████████████████████████████████████████████████████ 62
Calc    ██████████████ 14
Draw    █████████ 9
Impress ═════════ 9 (shared with Draw)
Math    0
```

### Tool count by intent

| Intent   | Writer | Calc | Draw/Impress | All types | Total |
|----------|-------:|-----:|-------------:|----------:|------:|
| navigate | 18     | 0    | 0            | 0         | 18    |
| edit     | 17     | 8    | 5            | 0         | 30    |
| review   | 13     | 0    | 0            | 0         | 13    |
| media    | 7      | 0    | 0            | 16        | 23    |
| *(none)* | 7      | 6    | 4            | 12        | 26    |

---

## 2. Impress vs Draw identity crisis (P0)

Two different doc-type detection functions exist:

| Function | Location | Impress returns |
|----------|----------|-----------------|
| `DocumentService.detect_doc_type()` | `core/services/document.py:109` | `"draw"` |
| `image_utils.get_doc_type()` | `framework/image_utils.py:22` | `"impress"` |

The MCP protocol uses `detect_doc_type()`, so Impress is always `"draw"`.

**Consequences:**
- Impossible to create Impress-specific tools (transitions, speaker notes editing, layouts)
- `"impress"` in `ai_images` doc_types is dead code
- `ListOpenDocuments` in file_ops.py correctly returns `"impress"` but MCP filtering doesn't

**Fix:** `detect_doc_type()` should check `PresentationDocument` before `DrawingDocument`, return `"impress"`. All draw tools get `doc_types = ["draw", "impress"]`.

---

## 3. Broker system (legacy, to remove)

The two-tier broker (`list_available_tools` / `request_tools`) was designed for an integrated chatbot (abandoned). It's **broken** (`get_tool_summaries` and `get_tool_names_by_intent` missing from `ToolRegistry`). The tier filtering is **not implemented** — `get_mcp_schemas()` returns all tools regardless of tier.

**Action:** Delete `plugin/modules/doc/tools/broker.py`. Keep `tier` and `intent` attributes as inert documentation metadata.

---

## 4. UNO API overlap analysis — what can be unified?

Reference: `~/dev/projects/libreoffice-core` (IDL definitions in `offapi/com/sun/star/`)

### Shared interfaces (same API on all doc types)

| Interface | Writer | Calc | Draw | Impress | Unifiable? |
|-----------|:------:|:----:|:----:|:-------:|:----------:|
| `XStyleFamiliesSupplier` | yes | yes | yes | yes | **YES** |
| `XDocumentPropertiesSupplier` | yes | yes | yes | yes | **YES** (already done) |
| `XPrintable` | yes | yes | yes | yes | **YES** |
| `XDrawPage` (drawing layer) | yes* | yes | yes | yes | **PARTIAL** |

\* Writer has a single draw page via `XDrawPageSupplier`, not `XDrawPagesSupplier`.

### Divergent interfaces (separate implementations required)

| Capability | Writer API | Calc API | Draw/Impress API |
|------------|-----------|----------|-----------------|
| **Search/Replace** | `XSearchable` on document | `XReplaceable` on cell ranges | none |
| **Annotations** | `XAnnotation` (`com.sun.star.office`) | `XSheetAnnotation` (`com.sun.star.sheet`) | none |
| **Content model** | Paragraphs + text ranges | Cells + sheets | Shapes + pages |
| **Images (list)** | `getGraphicObjects()` | inspect DrawPage shapes | inspect DrawPage shapes |

### Existing pattern: `image_utils.py` (gold standard)

`framework/image_utils.py` already demonstrates multi-doc tool design:
```python
doc_type = get_doc_type(model)
if doc_type in ("writer", "web"):
    image = model.createInstance("com.sun.star.text.GraphicObject")
    model.Text.insertTextContent(...)
else:
    image = model.createInstance("com.sun.star.drawing.GraphicObjectShape")
    draw_page.add(image)
```

Minimal branching, reusable core logic.

---

## 5. Doc-type parameter namespacing (framework pattern)

### Problem

Unified tools that work across doc types need doc-specific parameters. Example: `insert_image` needs `locator`/`paragraph_index` for Writer, `page_index`/`x`/`y` for Draw, `sheet_name` for Calc. Mixing them flat makes the tool schema confusing for agents.

### Solution: nested doc-type objects

Tool parameters use **top-level keys for shared params** and **nested objects for doc-type-specific params**:

```json
{
  "image_path": "/tmp/photo.jpg",
  "width_mm": 80,
  "caption": "Figure 1",
  "writer": {
    "locator": "heading_text:Chapter 1",
    "paragraph_index": 5
  },
  "draw": {
    "page_index": 0,
    "x": 5000,
    "y": 3000
  },
  "calc": {
    "sheet_name": "Sheet1"
  }
}
```

The agent only fills the sub-object matching the current doc type.

### Framework implementation

A **preprocessing step** in `ToolRegistry.execute()` flattens the relevant doc-type block before calling `tool.execute()`. The tool code stays simple — it just reads `kwargs["locator"]` without caring about namespacing.

```python
_DOC_TYPE_KEYS = frozenset(("writer", "calc", "draw", "impress"))

def _flatten_doc_type_params(kwargs, doc_type):
    """Merge doc-type-specific nested params into top-level kwargs."""
    merged = {}
    for k, v in kwargs.items():
        if k in _DOC_TYPE_KEYS:
            if k == doc_type and isinstance(v, dict):
                merged.update(v)
        else:
            merged[k] = v
    return merged
```

In `ToolRegistry.execute()`:
```python
kwargs = _flatten_doc_type_params(kwargs, ctx.doc_type)
result = tool.execute(ctx, **kwargs)
```

### Schema declaration in tools

```python
class InsertImage(ToolBase):
    doc_types = None  # all types
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "..."},
            "width_mm":   {"type": "integer", "description": "..."},
            "caption":    {"type": "string", "description": "..."},
            "writer": {
                "type": "object",
                "description": "Writer-specific options",
                "properties": {
                    "locator":         {"type": "string", "description": "..."},
                    "paragraph_index": {"type": "integer", "description": "..."},
                }
            },
            "draw": {
                "type": "object",
                "description": "Draw/Impress-specific options",
                "properties": {
                    "page_index": {"type": "integer", "description": "..."},
                    "x":          {"type": "integer", "description": "Position X (1/100 mm)"},
                    "y":          {"type": "integer", "description": "Position Y (1/100 mm)"},
                }
            },
            "calc": {
                "type": "object",
                "description": "Calc-specific options",
                "properties": {
                    "sheet_name": {"type": "string", "description": "..."},
                }
            },
        },
        "required": ["image_path"],
    }
```

### Benefits

- **Self-documenting**: agent sees which params apply to which doc type directly in the schema
- **Zero impact on tool code**: flatten step is transparent, tools receive flat kwargs
- **Extensible**: adding Impress-specific params = new `"impress"` block in schema
- **Validation-friendly**: JSON Schema validates each nested object independently
- **Reusable**: any unified tool can adopt this pattern

### Where it applies

| Unified tool | Common params | Writer-specific | Calc-specific | Draw/Impress-specific |
|---|---|---|---|---|
| `insert_image` | path, size, caption | locator, paragraph_index | sheet_name | page_index, x, y |
| `delete_image` | image_name | remove_frame | sheet_name | page_index |
| `list_images` | — | — | sheet_name | page_index |
| `search_in_document` | query, regex, case | — | sheet_name, range | — |
| `create_shape` | shape_type, size, text | — | sheet_name | page_index |
| `list_styles` | — | family | family | family |

---

## 6. Image tools unification plan

### Current state

| Tool | doc_types | Location |
|---|---|---|
| `insert_image` | writer | `writer/tools/images_doc.py` — own Writer-only impl |
| `list_images` | writer | `writer/tools/images_doc.py` — `getGraphicObjects()` |
| `get_image_info` | writer | `writer/tools/images_doc.py` — `getGraphicObjects()` |
| `set_image_properties` | writer | `writer/tools/images_doc.py` — anchor, orient, size |
| `delete_image` | writer | `writer/tools/images_doc.py` — `removeTextContent()` |
| `replace_image` | writer | `writer/tools/images_doc.py` — keeps frame/position |
| `download_image` | writer | `writer/tools/images_doc.py` — pure HTTP, no UNO |
| `generate_image` | all | `ai_images/tools/` — uses `image_utils.insert_image()` |
| `edit_image` | all | `ai_images/tools/` — uses `image_utils.replace_image_in_place()` |

### Target state

| Tool | doc_types | Strategy |
|---|---|---|
| `insert_image` | **all** | Delegate to `image_utils.insert_image()`. Writer always uses frame/caption. Uses doc-type param namespacing. |
| `list_images` | **all** | New `framework/graphic_query.py` with branching: Writer=`getGraphicObjects()`, others=iterate DrawPage shapes. |
| `get_image_info` | **all** | Same framework helper. Normalized output + doc-specific fields via namespacing. |
| `delete_image` | **all** | Branching: Writer=`removeTextContent()`, others=`page.remove(shape)`. Writer-specific `remove_frame` in `writer: {}`. |
| `download_image` | **all** | Trivial — just change `doc_types = None` (no UNO code). |
| `set_image_properties` | **writer** | Stays Writer-only: anchor_type, orientation, crop are Writer-specific concepts. |
| `replace_image` | **writer** | Stays Writer-only: preserves TextFrame, anchor position — no equivalent elsewhere. |

### Writer caption behavior

In Writer, `insert_image` **always** wraps images in a `TextFrame` with caption text (via `image_utils._insert_frame()`). This is the standard Writer behavior for production documents. The `caption` parameter provides the legend text.

For complex Writer-specific image manipulation (anchor types, orientation, frame properties), the agent uses `set_image_properties` and `replace_image` which remain Writer-only.

---

## 7. Unification roadmap

### Quick wins (low effort, high impact)

#### 7.1 Styles tools → all doc types — DONE (v0.3.1)

`list_styles` and `get_style_info` now use `doc_types = None` with auto-discovery of available style families.

#### 7.2 Shape tools → add Writer + Calc — DONE (v0.3.1)

`create_shape`, `edit_shape`, `delete_shape`, `get_draw_summary` now use `doc_types = None` with `get_draw_page(ctx)` bridge helper and doc-type namespacing.

#### 7.3 download_image → all types — DONE (v0.3.1)

Trivial change: `doc_types = None` (no UNO dependency).

#### 7.4 Search → Calc — DONE (v0.3.1)

Separate Calc tools (`search_in_spreadsheet`, `replace_in_spreadsheet`) using `XReplaceable` on sheets. Supports per-sheet and all-sheets modes.

#### 7.5 Annotations → Calc — DONE (v0.3.1)

`list_cell_comments`, `add_cell_comment`, `delete_cell_comment` via `XSheetAnnotation` API.

#### 7.6 Calc navigation tools — DONE (v0.3.1)

`list_named_ranges` and `get_sheet_overview` (used area, charts, annotations, shapes).

#### 7.7 Impress speaker notes — DONE (v0.3.1)

`get_speaker_notes` and `set_speaker_notes` — first Impress-only tools.

#### 7.8 Print tool — DONE (v0.3.1)

`print_document` for all doc types via `XPrintable`.

#### 7.9 Undo/Redo — DONE (v0.3.1)

`undo` and `redo` for all doc types via `XUndoManager`.

#### 7.10 Image tools — unify insert/list/info/delete — DONE (v0.3.1)

Created `framework/graphic_query.py` with cross-doc image query helpers. `insert_image`, `list_images`, `get_image_info`, `delete_image` now work on all doc types. Writer uses `getGraphicObjects()`, Calc/Draw/Impress use DrawPage shape iteration. Non-Writer tools support `shape_index` for lookup (Draw shapes often have empty names). Doc-type namespacing for `insert_image` (`writer: {locator, paragraph_index}`, `draw: {page_index, x, y}`, `calc: {sheet_name}`).

Also fixed: validation now runs before `_flatten_doc_type_params()` so nested doc-type params validate against the schema correctly.

### Remaining work

#### Impress transitions/layouts

- `set_slide_transition` — presentation DrawPage properties
- `get_slide_layout` / `set_slide_layout` — `Layout` property

---

## 8. Summary matrix — current state (v0.3.1)

| Capability | Writer | Calc | Draw | Impress | Notes |
|------------|:------:|:----:|:----:|:-------:|:------|
| Content read/write | deep | basic | basic | basic | — |
| Search/replace | yes | yes | no | no | Calc added v0.3.1 |
| Comments/annotations | yes | yes | no | no | Calc added v0.3.1 |
| Styles | yes | yes | yes | yes | Unified v0.3.1 |
| Images (insert) | yes | yes | yes | yes | Unified v0.3.1 |
| Images (list/manage) | yes | yes | yes | yes | Unified v0.3.1 |
| Shapes | yes | yes | yes | yes | Unified v0.3.1 |
| Navigation/outline | deep | basic | no | no | Calc added v0.3.1 |
| Tracked changes | yes | no | no | no | Writer-specific |
| Speaker notes | — | — | — | yes | Added v0.3.1 |
| Transitions | — | — | — | **no** | **TODO** |
| Named ranges | — | yes | — | — | Added v0.3.1 |
| Undo/redo | yes | yes | yes | yes | Added v0.3.1 |
| Print | yes | yes | yes | yes | Added v0.3.1 |

**Bold** = remaining gaps.

---

## 9. Implementation log

| # | Action | Status |
|---|--------|--------|
| 1 | Fix Impress/Draw detection | **DONE** v0.3.1 |
| 2 | Delete broker.py | **DONE** v0.3.1 |
| 3 | Add `_flatten_doc_type_params` to `ToolRegistry` | **DONE** v0.3.1 |
| 4 | Unify styles → all doc types | **DONE** v0.3.1 |
| 5 | Unify shapes → all doc types (with namespacing) | **DONE** v0.3.1 |
| 6 | Unlock `download_image` → all types | **DONE** v0.3.1 |
| 7 | Add Calc search/replace | **DONE** v0.3.1 |
| 8 | Add Calc comments | **DONE** v0.3.1 |
| 9 | Add Calc navigation (named ranges, overview) | **DONE** v0.3.1 |
| 10 | Add Impress speaker notes editing | **DONE** v0.3.1 |
| 11 | Add print tool (XPrintable, all types) | **DONE** v0.3.1 |
| 12 | Add undo/redo tool (all types) | **DONE** v0.3.1 |
| 13 | Unify image tools (insert/list/info/delete) | **DONE** v0.3.1 |
| 14 | Fix validation order (validate before flatten) | **DONE** v0.3.1 |

### Remaining

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 15 | Add Impress transitions/layouts | M | Impress-specific |
