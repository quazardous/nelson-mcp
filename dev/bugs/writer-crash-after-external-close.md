# LibreOffice aborts in Writer view code after a document is closed over UNO

Status: **observed twice, not caused by Nelson code, not reproduced on
demand.** Recorded so it is recognised the next time, and because
`doc_close` closes documents the same way.

## Occurrences

| When | Trigger | Abort in |
|---|---|---|
| 2026-09-16, bench W1 (#2626) | an external UNO script closed a Writer document | `SwFEShell::GetObjCntTypeOfSelection()` during the clipboard state update |
| 2026-09-16 20:33, format fidelity bench (#2650) | an external UNO script built a hidden Writer document, stored it, `close(True)`, then loaded it again hidden | `SwView::IsPasteAllowed()` → `std::unique_ptr<SwWrtShell>::operator*` on a null pointer (`_GLIBCXX_ASSERTIONS`), from `SwBaseShell::StateClpbrd` ← `MenuBarManager::Activate` ← `GtkSalMenu::SetFrame` |

LibreOffice 26.2.6.3, gtk3 VCL plugin, inside wbox (labwc). Backtrace of the
second one: `crash-2026-09-16-ispasteallowed.bt.txt` (coredump pid 3057148).

## What both have in common

- A Writer view is being torn down or built while the menu bar / clipboard
  state is queried, and the view's `SwWrtShell` is already (or not yet)
  gone.
- No Nelson thread is in Writer or UNO in either capture; both follow a
  close driven over the UNO socket from another process.

## Why it matters for Nelson

`doc_close` calls `model.close()` on the main thread, and `doc_create` /
`doc_open` build frames the same way. If this is a LibreOffice race between
view teardown and status updates, Nelson can trigger it too. Nothing in the
smoke suite (hundreds of create/close cycles, headless and in wbox) or the
40-cycle soak has hit it so far.

## Next steps if it comes back

- Check whether it is reported upstream (bugs.documentfoundation.org,
  `SwView::IsPasteAllowed` / `StateClpbrd` null `SwWrtShell`).
- Try to reproduce: loop hidden `loadComponentFromURL` + `close(True)` over
  UNO in wbox, with and without a visible document open.
