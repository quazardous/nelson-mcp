# Impress Tools Roadmap

Vision for AI-driven presentation capabilities, extending the existing Draw module.

## Current capabilities

### Shared with Draw
- `create_shape` — rectangles, ellipses, text boxes, lines
- `edit_shape` — move, resize, recolor, change text
- `delete_shape` — remove shapes
- `get_draw_summary` — list shapes and properties on current slide
- `get_page_objects` — detailed page content
- `list_master_slides` / `get_slide_master` / `set_slide_master` — master page management
- `insert_image` / `list_images` / `delete_image` — images on slides

### Impress-specific
- `get_speaker_notes` / `set_speaker_notes` — speaker notes
- `get_slide_transition` / `set_slide_transition` — 25 FadeEffect types, speed, auto-advance
- `get_slide_layout` / `set_slide_layout` — 30 named layout types
- `list_placeholders` / `get_placeholder_text` / `set_placeholder_text` — title, subtitle, body placeholders
- `goto_page` — navigate to a slide

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
