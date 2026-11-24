# Known Issues

## DOCX round trip: what LibreOffice's filter may change

**Status**: LibreOffice behaviour, not a Nelson bug (GitHub #49). Nelson saves
`.docx` through LibreOffice's own `MS Word 2007 XML` export filter and adds
nothing of its own, so a save and reopen gives what LibreOffice gives.

**Preserved**: text, paragraph and character styles, tables and their cells,
page size and body margins, and equations, which stay editable OMML with the
same content.

**May be normalized** (each reproduced with LibreOffice alone, no Nelson):

- **Equations**: the OMML is regenerated from LibreOffice's Math model, so
  run boundaries change and explicit run properties can be dropped. The
  StarMath source is normalized too: `{b_1}` reads back as
  `{{b} rsub {1}}`.
- **Unused section properties**: a header or footer distance with no header
  or footer is not kept: `w:header="720"` comes back as `w:header="0"`.
- **Layout metrics**: LibreOffice lays out the re-exported file again, and
  positions can shift by a point or two.

**For tests**: compare against the saved file after closing and reopening
it. A comparison made before the reopen does not see these changes.

## Range coordinate mismatch (Writer)

**Status**: Open — affects `text_get_range(scope="range")` and `text_apply_range(target="range")`.

Character offsets from `text_find` (cursor-based) don't match offsets used by range export (paragraph-enumeration with summed lengths). The same numeric range is interpreted in two different coordinate systems, producing corrupted output (e.g. "## ary..." instead of "## Summary...").

**Recommended fix**: Use cursor-based paragraph offsets — for each enumerated paragraph, measure start/end with `gotoRange(para.getStart(), True)` + `len(cursor.getString())`. This aligns range export with `text_find` coordinates.

**Workaround**: Avoid `scope="range"` for section replacement. Use `target="search"` with full section text instead.

Workaround: use `target="search"` with full section text instead of range coordinates.

## AI Horde improvements

Open items for the ai_horde image module:

- **Progress feedback**: Generation can take minutes but sidebar only shows "Running...". The `AiHordeClient` receives progress events — thread them to the UI status bar.
- **Smart image dimensions**: `image_edit` hardcodes replacement to 512x512. Should read the original image dimensions and pass them to the generation request.
- **Translation visibility**: Prompt translation acts silently; show "Translating prompt..." status before generation starts.
