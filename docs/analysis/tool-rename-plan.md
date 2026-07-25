# Tool renaming plan (#11 + #2)

**Status:** PAUSED — plan approved, implementation not started.
**Goal:** consistent `domain_verb` tool names so LLMs pick the right tool (#2) and the API surface is coherent (#11).

## Decisions (locked)

1. **No backward compatibility** — hard rename, no aliases. No existing users to preserve.
2. **Prefix Calc and Draw too** — `calc_*` / `draw_*` everywhere (not left as-is).
3. **Rename only — NO merges in this pass.** The 7 merges from #11 (image_list, frame_list, table_read, table_structure, text_insert, text_search, gallery_query) are deferred to a later pass. This pass is pure prefixing, no signature/behavior changes.
4. **By domain, separate commits** — one commit per prefix group, deploy + test a sample at each step.

## CRITICAL — cross-references to update with every rename

A tool's MCP name = its `name = "..."` class attribute (`plugin/framework/tool_registry.py` keys by `tool.name`). But these places ALSO reference tool names and break silently if not updated:

- **MCP presets** — `plugin/modules/mcp/__init__.py` `PRESETS` dict (writer-edit, writer-read, calc, gallery, minimal). Lists tool names explicitly. MUST update.
- **Tool descriptions** that cite other tools (e.g. "from list_images", "use fit_image afterwards", "from list_images)"). grep each old name in all `tools/*.py` descriptions.
- **Launcher prompts** — `plugin/modules/launcher_claude/prompts/skills/nelson/SKILL.md`, `plugin/modules/launcher_opencode/prompts/AGENTS.md`.
- **Config text** — `plugin/modules/writer/module.yaml` (label/description mention `search_in_document` → becomes `text_search`).
- **Docs** — `QUICKSTART.md`, `docs/impress-roadmap.md`, `docs/howto/setup-image-gallery.md`, `docs/tool-descriptions.md`. (Do NOT rewrite `CHANGELOG.md` history; only new entries use new names.)
- **HTML** — `plugin/modules/mcp/templates/tool_reference.html` (check if generated or static).
- **batch** — `plugin/modules/batch/tools/batch.py:212` calls `tool_reg.execute(tool_name, ...)` with a RUNTIME-provided name (from the batch payload), so no static reference to fix there.

After each domain commit: `kill → deploy → launch → nelson_log` (check 159 tools load, no errors), then call a couple of renamed tools via `mcp__mcp-dev__ (nelson-dev)`.

## Mapping

### image_ (writer/tools/images_doc.py + ai_images)
| old | new |
|-----|-----|
| list_images | image_list |
| get_image_info | image_info |
| insert_image | image_insert |
| replace_image | image_replace |
| set_image_properties | image_set |
| delete_image | image_delete |
| download_image | image_download |
| fit_image | image_fit |
| wrap_image_in_frame | image_wrap |
| generate_image | image_generate |
| edit_image | image_edit |

### frame_ (writer text frames)
| list_text_frames | frame_list |
| get_text_frame_info | frame_info |
| set_text_frame_properties | frame_set |

### table_ (writer)
| list_tables | table_list |
| read_table | table_read |
| create_table | table_create |
| delete_table | table_delete |
| set_table_properties | table_set |
| write_table_cell | table_write_cell |
| write_table_row | table_write_row |
| add_table_rows | table_add_rows |
| add_table_columns | table_add_columns |
| delete_table_rows | table_delete_rows |
| delete_table_columns | table_delete_columns |

### text_ (writer paragraphs/search)
| read_paragraphs | text_read |
| insert_at_paragraph | text_insert |
| insert_paragraphs_batch | text_insert_batch |
| set_paragraph_text | text_set |
| delete_paragraph | text_delete |
| duplicate_paragraph | text_duplicate |
| set_paragraph_style | text_set_style |
| find_text | text_find |
| search_in_document | text_search |
| replace_in_document | text_replace |
| get_document_content | text_get_range |
| apply_document_content | text_apply_range |

### style_
| list_styles | style_list |
| get_style_info | style_info |

### nav_ (writer_nav)
| goto_page | nav_goto_page |
| get_page_objects | nav_page_objects |
| get_document_tree | nav_tree |
| get_document_outline | nav_outline |
| navigate_heading | nav_heading |
| get_heading_children | nav_heading_children |
| get_heading_content | nav_heading_content |
| clone_heading_block | nav_heading_clone |
| get_surroundings | nav_surroundings |
| resolve_locator | nav_resolve |

### section_ / bookmark_ / index
| list_sections | section_list |
| read_section | section_read |
| list_bookmarks | bookmark_list |
| resolve_bookmark | bookmark_resolve |
| cleanup_bookmarks | bookmark_cleanup |
| refresh_indexes | doc_refresh_indexes |
| update_fields | doc_update_fields |
| search_fulltext | text_search_fulltext |
| get_index_stats | text_index_stats |

### comment_ / change_
| add_comment | comment_add |
| list_comments | comment_list |
| delete_comment | comment_delete |
| resolve_comment | comment_resolve |
| accept_all_changes | change_accept_all |
| reject_all_changes | change_reject_all |
| get_tracked_changes | change_list |
| set_track_changes | change_set |

### doc_ / link_ (doc module)
| get_document_info | doc_info |
| document_health_check | doc_health |
| get_document_stats | doc_stats |
| set_document_properties | doc_set_properties |
| set_document_protection | doc_protect |
| create_document | doc_create |
| open_document | doc_open |
| close_document | doc_close |
| save_document | doc_save |
| save_document_as | doc_save_as |
| export_pdf | doc_export_pdf |
| print_document | doc_print |
| get_recent_documents | doc_recent |
| list_open_documents | doc_list_open |
| undo | doc_undo |
| redo | doc_redo |
| insert_hyperlink | link_insert |
| edit_hyperlink | link_edit |
| remove_hyperlink | link_remove |
| list_hyperlinks | link_list |

### gallery_ (images) / docgallery_ (documents) — avoid collision
| gallery_list | gallery_list (keep) |
| gallery_search | gallery_search (keep) |
| gallery_get | gallery_get (keep) |
| gallery_providers | gallery_providers (keep) |
| gallery_update | gallery_update (keep) |
| images_folder_rescan | gallery_rescan |
| docs_gallery_list | docgallery_list |
| docs_gallery_search | docgallery_search |
| docs_gallery_get | docgallery_get |
| docs_gallery_providers | docgallery_providers |
| docs_gallery_update | docgallery_update |
| docs_folder_rescan | docgallery_rescan |

### workflow_ / task_ / summary_ / batch_ / job_
| get_workflow_status | workflow_get |
| set_workflow_status | workflow_set |
| check_stop_conditions | workflow_check |
| scan_tasks | task_scan |
| add_ai_summary | summary_add |
| get_ai_summaries | summary_list |
| remove_ai_summary | summary_remove |
| execute_batch | batch_execute |
| list_jobs | job_list |
| get_job | job_get |

### calc_ (calc module) — DRAFT names, confirm on resume
| add_cell_comment | calc_comment_add |
| delete_cell_comment | calc_comment_delete |
| list_cell_comments | calc_comment_list |
| add_conditional_format | calc_condformat_add |
| clear_conditional_formats | calc_condformat_clear |
| list_conditional_formats | calc_condformat_list |
| remove_conditional_format | calc_condformat_remove |
| clear_range | calc_clear_range |
| create_chart | calc_chart_create |
| delete_chart | calc_chart_delete |
| edit_chart | calc_chart_edit |
| get_chart_info | calc_chart_info |
| list_charts | calc_chart_list |
| create_sheet | calc_sheet_create |
| list_sheets | calc_sheet_list |
| switch_sheet | calc_sheet_switch |
| get_sheet_overview | calc_sheet_overview |
| get_sheet_summary | calc_sheet_summary |
| delete_structure | calc_delete_structure |
| detect_and_explain_errors | calc_detect_errors |
| import_csv_from_string | calc_import_csv |
| list_named_ranges | calc_named_range_list |
| merge_cells | calc_merge_cells |
| read_cell_range | calc_read_range |
| write_cell_range | calc_write_range |
| write_formula_range | calc_write_formula |
| replace_in_spreadsheet | calc_replace |
| search_in_spreadsheet | calc_search |
| set_cell_style | calc_set_style |
| sort_range | calc_sort_range |

### draw_ (draw module) — DRAFT names, confirm on resume
| add_slide | draw_slide_add |
| delete_slide | draw_slide_delete |
| read_slide_text | draw_slide_read |
| get_slide_layout | draw_slide_layout_get |
| set_slide_layout | draw_slide_layout_set |
| get_slide_master | draw_slide_master_get |
| set_slide_master | draw_slide_master_set |
| get_slide_transition | draw_slide_transition_get |
| set_slide_transition | draw_slide_transition_set |
| create_shape | draw_shape_create |
| edit_shape | draw_shape_edit |
| delete_shape | draw_shape_delete |
| get_placeholder_text | draw_placeholder_get |
| set_placeholder_text | draw_placeholder_set |
| list_placeholders | draw_placeholder_list |
| list_pages | draw_page_list |
| list_master_slides | draw_master_list |
| get_speaker_notes | draw_notes_get |
| set_speaker_notes | draw_notes_set |
| get_presentation_info | draw_presentation_info |
| get_draw_summary | draw_summary |

### core jobs already covered under job_ above.

## Open questions for resume
- calc_/draw_ names above are my drafts — confirm before applying those two domains.
- `set_paragraph_style` → `text_set_style` vs `style_apply`? Currently under text_.
- `search_fulltext` → `text_search_fulltext` ok? It is the index-backed variant of `text_search`.

## Suggested commit order (one per domain)
1. image_ (incl. ai_images generate/edit)
2. frame_
3. table_
4. text_
5. style_
6. nav_ + section_/bookmark_ + index
7. comment_ + change_
8. doc_ + link_
9. gallery_ / docgallery_
10. workflow_/task_/summary_/batch_/job_
11. calc_
12. draw_

Update `PRESETS` (mcp/__init__.py), launcher prompts, and docs as the relevant names change (do it incrementally or in a final sweep commit). Bump minor version (→ 0.10.0) at the end.
