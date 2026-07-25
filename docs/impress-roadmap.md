# Impress Tools Roadmap

Vision for AI-driven presentation capabilities, extending the existing Draw module.

## Current capabilities

### Shared with Draw
- `shape_create` — rectangles, ellipses, text boxes, lines
- `shape_edit` — move, resize, recolor, change text
- `shape_delete` — remove shapes
- `shape_summary` — list shapes and properties on current slide
- `nav_page_objects` — detailed page content
- `draw_master_list` / `draw_master_get` / `draw_master_set` — master page management
- `image_insert` / `image_list` / `image_delete` — images on slides

### Impress-specific
- `draw_notes_get` / `draw_notes_set` — speaker notes
- `draw_transition_get` / `draw_transition_set` — 25 FadeEffect types, speed, auto-advance
- `draw_layout_get` / `draw_layout_set` — 30 named layout types
- `draw_placeholder_list` / `draw_placeholder_get` / `draw_placeholder_set` — title, subtitle, body placeholders
- `nav_goto_page` — navigate to a slide

## Remaining roadmap

### Near term
- `reorder_slides(from_index, to_index)` — change slide sequence
- `duplicate_slide(index)` — clone slides for templating
- Structured slide content export (title + bullets + images in one call)

### Long term: generative workflows
- Outline-to-deck conversion from Writer documents
- AI slide audits (text density, contrast, visual balance)
- Image generation for slide content
- Presentation controls (`start_presentation`, `goto_slide`)

## Implementation note

Prefer `com.sun.star.presentation` services when available, fall back to the drawing layer for fine-grained shape control.
