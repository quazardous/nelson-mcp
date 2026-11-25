# Equations in Writer — plan

*Written 2026-11-24, after 0.14.7. Tracks GitHub #49.*

*Since 0.15.0 the marker is `[equation: …]` and the field `equations`;
`[formula: …]` below is the 0.14.7 name, kept as written then.*

## Where we are

A Writer equation is an embedded LibreOffice Math object (CLSID
`078B7ABA-54FC-457F-8551-6147e776a997`), almost always anchored as a
character. Its model holds the source in StarMath, in the `Formula`
property. DOCX equations (OMML) import as the same objects and export back
to OMML.

Since 0.14.7, `text_read` shows each equation in its place as
`[formula: <StarMath>]` and lists it in the paragraph's `formulas` with its
object name. That is all Nelson knows about equations. There is no tool to
list them across the document, change one, or insert one.

What #49 asks for, in order of value:

1. tell an equation from an empty paragraph — **done in 0.14.7**;
2. list equations with a stable identifier and a location, tables included;
3. read the source;
4. update an equation in place, keeping anchoring, alignment, size and
   numbering;
5. insert one, editable;
6. undo and `_document` targeting for all of it.

## Facts established so far

Checked over UNO on LibreOffice 26.2, while answering #49:

- In the paragraph's portion enumeration, an equation is a `Frame` portion.
  `createContentEnumeration("com.sun.star.text.TextContent")` on it gives the
  `TextEmbeddedObject`, whose `getEmbeddedObject()` is the Math model.
- `doc.getEmbeddedObjects()` lists every embedded object by name (`Objet1`,
  localized), equations and others (charts, OLE) alike. Filter on `CLSID`.
- An equation created over UNO (`createInstance`, `CLSID`, `AnchorType`
  `AS_CHARACTER`, `insertTextContent`, then `Formula` on the model) is a real,
  editable equation, and it survives a DOCX round trip as OMML.
- LibreOffice normalizes the source on DOCX import and export (`{b_1}` →
  `{{b} rsub {1}}`). It is the filter's behaviour, documented in
  `docs/known-issues.md`; Nelson cannot avoid it.

## Open questions — the spike answers these first

None of these is known yet. Each one changes the design, so phase 0 settles
them before any tool is written.

| # | Question | Why it matters |
|---|---|---|
| Q1 | Does Writer's undo revert a change to the Math model's `Formula`? The Math model has its own undo; Writer's undo manager may not see it. | If not, `equation_set` must replace the object (insert new, remove old) so one `doc_undo` reverts it, or say undo is not supported. |
| Q2 | Does the object's size refresh after `Formula` changes, with no view? (Headless, hidden documents.) | A stale size means overlapping or clipped equations in the saved file. |
| Q3 | Can a StarMath syntax error be detected over UNO? | Without it, a typo saves a broken equation with `ok`. Fallback: parse in a hidden Math document, or compare against the rendered result. |
| Q4 | What happens to an equation when `text_set`, `text_replace` or `text_apply_range` rewrites its paragraph? Does an agent that writes back `[formula: …]` from `text_read` replace the object with literal text? | The 0.14.7 marker makes this round trip likely. If it destroys equations, those tools must refuse or keep them. **Most urgent: it is a data-loss risk that exists today.** |
| Q5 | How is a numbered equation stored? Writer's `fn` AutoText makes a borderless 1×2 table (equation, number field); DOCX may use something else. | Numbering, location, and "preserve numbers on update" all depend on it. |
| Q6 | How do `find_paragraph_for_range` and the paragraph index behave for an equation in a table cell, a frame, a header or footer? | The location reported by the list tool. |
| Q7 | Does an insertion with change recording on show as a tracked change? Does a `Formula` change? | Agents edit with recording on by default. |
| Q8 | Same answers on LibreOffice 24.2, the version #49 runs? | The reporter's setup, and the oldest supported here. |

## Answers (spike of 2026-11-24, LibreOffice 26.2 and 26.8, same results)

| # | Answer | Decision |
|---|---|---|
| Q1 | No: a change to `Formula` is invisible to Writer's undo (the context it ran in is empty). Inserting a new object and removing the old one, in one context, is undone in one step. | Setting `writer.equation_update`: `replace` (default; new object, old one's name, place and model settings, undoable) or `in_place` (same object, not undoable, said in the result). Objects not anchored as a character are always changed in place. |
| Q2 | Yes: the object's `Size` follows the new source with no view and no `update()` call. | Nothing to do. |
| Q3 | No property reports an error, but the MathML export of a broken formula holds an empty `<mrow/>` where an operand is missing. A deliberate `{}` does the same. | Warn, never refuse, from the MathML export; skip the check when the source has `{}`. |
| Q4 | **Yes: `setString` on the paragraph, or on a cursor over it, deletes its equations**, and `text_set` with the text from `text_read` writes `[formula: …]` as plain text. `replaceAll` keeps them. | `text_set` and `text_insert` with `replace` refuse a paragraph that holds equations (`paragraph_has_equations`). Every other Writer write is watched by the registry, which reports `equations_removed`. |
| Q5 | Writer's `fn` AutoText (present in an English profile, absent in a French one here) makes a 1×2 table: the equation in A1, `(1)` from a number field in B1. | `equation_list` reports `number` for an equation in a two-cell table whose other cell reads like `(1)`. Numbered insertion stays for later. |
| Q6 | The anchor's text says where: `SwXBodyText`, `SwXCell` (with `CellName`), `SwXTextFrame`, `SwXHeadFootText`. | Location: `area` plus `paragraph_index`, or `table` and `cell`, or `frame`. |
| Q7 | Neither an inserted equation nor a changed source becomes a tracked change. | Say so in the result when recording is on. |
| Q8 | 24.2 is not installed here; 26.2 and 26.8 agree on every point. | Ask the #49 reporter to try on 24.2. |

## Design

### Naming

Tools prefixed `equation_`, the word users and #49 use, and the one that
does not collide with Calc formulas. The `text_read` marker says `formula`
today; rename it to `[equation: …]` and the field to `equations` in the same
release as phase 1, while 0.14.7 is the only release that has it.

### Tools

Following the house pattern (one list tool that turns into the detail read
with a name, like `image_list` and `table_list`):

- **`equation_list`** — every equation: `name`, `formula` (StarMath), and a
  location: `paragraph_index` in the body, or `table` + `cell`, or `frame`,
  or `header`/`footer`; `inline` (shares its paragraph with text) or not;
  `number` when it is a numbered equation. With `name`: the same plus base
  font size, alignment and anchor type.
- **`equation_set`** — `name`, `formula`, optional `base_font_size`. Changes
  the equation in place; anchoring, position and numbering stay. Refuses a
  syntax error if Q3 allows detecting one.
- **`equation_insert`** — `formula`, a target (`locator` / `paragraph_index`
  with `position` `before` | `after` | `inline_end`, or a table cell),
  `display` (`block`: own centred paragraph; `inline`: in the text).
  Returns the new object's name. Numbered insertion only if Q5 shows a clean
  way; otherwise later.
- **`equation_delete`** — `name`.

All are Writer-only (`doc_types = ["writer"]`), go through the registry's
undo context and `_document`, and count as mutations except the list.

### Protections

- **The text round trip (Q4).** If rewriting a paragraph destroys its
  equations, `text_set` and the replace paths refuse a paragraph that holds
  one, naming `equation_set`, unless the new text keeps the equation. The
  `text_read` hint says the marker is read-only.
- **Source normalization.** `equation_list` returns the source as
  LibreOffice holds it. An agent comparing its input to the stored source
  must expect normalized spacing and braces; the tool description says so.

### Out of scope for now

MathML in or out (the Math model can import and export it through filters;
add it if asked); equations in Calc, Impress and Draw; equation numbering
schemes beyond what Q5 reveals; formatting beyond base size and alignment.

## Phases

| Phase | Content | Size | Ships as |
|---|---|---|---|
| 0 | Spike: answer Q1–Q8 with a script against 26.x and 24.2; write the answers into this file. | ½ day | — |
| 1 | Q4 protection if needed; `equation_list`; marker rename; smoke checks with equations in body, inline, table cell, and after a DOCX reopen. | 1 day | 0.15.0 |
| 2 | `equation_set`, with undo per Q1 and size refresh per Q2; error detection per Q3. | 1 day | 0.15.0 or 0.15.1 |
| 3 | `equation_insert`, `equation_delete`; tracked-change behaviour per Q7. | 1–2 days | 0.15.x |
| 4 | If asked: numbering, MathML, other document types. | — | later |

Phase 1 alone answers most of #49 (find and read every equation, safely).
Phase 4 waits for a request.

## Tests

- **Unit**: location and listing logic over fake portions and objects, as
  `tests/test_tracked_text.py` does for the marker.
- **Smoke** (`scripts/smoke_test.py`, real LibreOffice): one check per
  phase, each built from equations inserted over UNO and from a minimal
  OMML DOCX (like the one used for #49), and each re-read after a save and
  reopen, since #49 showed that changes appear only then.
- **Every check must fail on the code before it** — run it against the
  previous commit once, as for #46 and #47.
