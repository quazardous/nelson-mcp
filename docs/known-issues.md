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
- **Equation names**: a `.docx` does not store object names, so on reopen
  the equations are named `Object1`, `Object2`… in document order. A name
  taken before a save and reopen may point to another equation: list them
  again after a reopen.
- **Equation source**: spacing, braces and symbols are normalized:
  `sum from {i=1} to {n} i` reads back `sum from {i = 1} to {n} {i}`, and
  `+-` reads back as `±`. Compare formulas loosely, not as strings.
- **Tracked changes**: the changes themselves survive (authors, the text
  with all accepted, the text with all rejected), but not their count:
  adjacent deletions are merged and paragraph-mark changes become empty
  `<w:ins>` elements. Counting `w:ins`/`w:del` reports a change where there
  is none; compare the accepted and rejected texts instead.
- **Package parts and settings**: empty parts (`footnotes.xml`,
  `endnotes.xml`, `webSettings.xml`…) are dropped, a single footer can come
  back as one per page style (`footer1` to `footer3`), and `settings.xml`
  loses Word's `w:rsid` entries and other Word-only settings. A structural
  diff of the package looks large for a save that changed nothing.
- **Unused section properties**: a header or footer distance with no header
  or footer is not kept: `w:header="720"` comes back as `w:header="0"`.
- **Layout metrics**: LibreOffice lays out the re-exported file again, and
  positions can shift by a point or two.

**For tests**: compare against the saved file after closing and reopening
it. A comparison made before the reopen does not see these changes.

## Range offsets (Writer)

**Status**: Fixed for body text (Unreleased). Open for matches in tables.

Offsets from `text_find` are the length of the body text before a point,
as LibreOffice's `getString()` counts it: table cells and tracked deletions
count, paragraph breaks count one each, equations and other objects anchored
as characters count nothing. `text_get_range(scope="range")` and
`text_apply_range(target="range")` used to move there with `goRight()`,
which steps over objects too, so every range after an equation drifted.
They now find the position by measuring (`ops.position_at`), and a range
that starts or ends inside a table takes the whole table.

**Still open**: a `text_find` match inside a table cell reports an offset
counted from the start of that cell, not of the body, so it cannot be used
as a range. Use `table_write_cell` for cells.

## AI Horde improvements

Open items for the ai_horde image module:

- **Progress feedback**: Generation can take minutes but sidebar only shows "Running...". The `AiHordeClient` receives progress events — thread them to the UI status bar.
- **Smart image dimensions**: `image_edit` hardcodes replacement to 512x512. Should read the original image dimensions and pass them to the generation request.
- **Translation visibility**: Prompt translation acts silently; show "Translating prompt..." status before generation starts.
