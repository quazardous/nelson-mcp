# Deadlock on cold start with a document (GitHub #35 / #37, tdf#173208)

**Status:** open, not reproduced locally. One strong lead in Nelson's own code,
recorded here because nobody has posted it on either issue yet.

## The two issues are one bug

- **#35** (2026-08-14) — cold start with a document on the command line, no
  window ever appears, port 8766 bound, `oosplash` and `soffice.bin` alive.
- **#37** (2026-08-20) — same hang, originally attributed to
  `RecoveryInfo/Crashed=true`.

The 2026-08-26 comment on #37 **invalidates #37's own title**. On the second
occurrence Recovery was not involved: `RecoveryList` was absent, and the
`Crashed=true` entry present had been written *by the hung run itself*, 1.7 s
after it stopped making progress. LibreOffice sets that flag at the start of
every session and clears it on clean exit, so its presence proves nothing.

What both occurrences share is `SynchronousDispatch` on the main thread, which
happens on **any** cold start with a document on the command line. Recovery is
one way to get there; a mail client handing an attachment to `soffice` is
another. #35 is the general statement of the bug; #37 is a special case of it
with the better backtrace.

Upstream half: **tdf#173208**, which also carries the isolation-leak defect
(`-env:UserInstallation` not honoured for crash-time Recovery writes). Either
side's fix breaks the cycle.

## The cycle

```
main thread          holds SolarMutex, waits on a framework mutex
                     comphelper::SynchronousDispatch::dispatch
                     SalUserEventList::DispatchUserEvents
                     QtInstance::ImplYield  ->  Application::Execute

Nelson Python thread holds the framework lock, waits on SolarMutex
                     framework::Desktop::getActiveFrame
                     framework::Desktop::getCurrentFrame
                     framework::Desktop::getCurrentComponent
                     libpyuno -> _PyObject_MakeTpCall
```

Five threads were queued on `SolarMutex::doAcquire` in the capture.

## The lead: `nelson-prebuild` calls getCurrentComponent() off the main thread

`plugin/modules/core/__init__.py:70` — `CoreModule.start_background()` spawns a
daemon thread and never posts its UNO work to the main thread:

```python
threading.Thread(target=self._prebuild_cache,
                 daemon=True, name="nelson-prebuild").start()
```

`_prebuild_cache` then polls, **every 2 s for up to 30 s**:

```python
doc = self._doc_svc.get_active_document()
```

and `get_active_document` (`plugin/modules/core/services/document.py:175`) is a
bare `desktop.getCurrentComponent()` — precisely the call in the backtrace, and
precisely the call `AGENTS.md` forbids:

> **Document scoping**: `self.xFrame.getController().getModel()` — never
> `desktop.getCurrentComponent()`.

The timing fits: `start_background` already runs off the main thread (Phase 2b,
Job thread), and the first poll lands ~2 s after bootstrap, inside the window
where the command-line document is being dispatched.

Contrast in the same file: `_attach_page_logger()` does the same kind of work
**correctly**, through `post_to_main_thread(_attach)` (`core/__init__.py:190`).

### Second caller of the same shape

`plugin/modules/mcp/__init__.py:225` — the `listChanged` poller (#24) calls
`get_active_document()` every 2 s from a background thread for as long as an
SSE client is connected. Not boot-specific, so not a candidate for #35/#37, but
the same rule violation and the same deadlock ingredients.

## What this is not

Not a diagnosis. The reporter failed to reproduce in nine deliberate attempts
(plain `soffice <file>`, `--calc` with the byte-identical command line, and the
same with Thunderbird's environment copied verbatim). His strongest lead remains
NSS initialisation, which ran in the hung process and in none of the healthy
ones. What is recorded here is that Nelson contains a code path doing exactly
what the backtrace shows, on the thread it shows, in the window where the hang
occurs, against the project's own written rule.

## Red herring, on the record

`get_active_document: getCurrentComponent() returned None` in the log is **not**
a deadlock signature. Nelson writes it on every startup, successful ones
included. The reporter initially read it as one and said so.

## Workaround that holds

Let an empty Start Center come up first, then hand the document to the running
instance:

```bash
soffice --norestore      # wait for the window and "Framework bootstrap complete"
soffice /path/to/file.xlsx
```

## Next step

Instrument before believing any of this: log thread name and identity at every
`get_active_document()` entry, and confirm whether `nelson-prebuild` is live at
the moment of the hang. If it is, the fix is to route `_prebuild_cache` through
`post_to_main_thread` like `_attach_page_logger` already does — or to drop the
poll entirely and build the cache on first use.


## Update 2026-09-16 — a Nelson deadlock captured locally, second lock pair

Reproduced **by accident, headless under wbox** (`make wbox-up`), while taking
README screenshots: after a few MCP edits (`text_set`, `text_set_style`,
`text_insert_batch`) and a sidebar interaction, LibreOffice froze — `/health`
stopped answering. `ptrace_scope` was 0, so the full backtrace was taken
without sudo: `deadlock-2026-09-16-import-lock.bt.txt` (all threads, 40 frames).

This is **not** the lock pair of #35/#37, but the same class of defect:

```
soffice.bin (main)        holds SolarMutex, waits on Python's import lock
                          _imp_acquire_lock <- import_find_and_load

Thread-13 (_update_menu_icons)
                          holds the import lock (inside PyImport_ImportModuleLevelObject,
                          nested twice), and while tearing down frames destroys a
                          Writer text cursor:
                          SwXTextCursor::~SwXTextCursor -> SolarMutex::doAcquire  (blocked)

nelson-prebuild           Desktop::getCurrentComponent -> SolarMutex::doAcquire  (blocked)
Thread-14 (process_request?)  Desktop::getCurrentComponent -> SolarMutex         (blocked)
2x mcp-doctype-pol        waiting on a Python lock                               (blocked)
```

Three things in Nelson line up to make this possible:

1. **`_update_menu_icons` runs UNO off the main thread.** `notify_menu_update()`
   (`plugin/main.py`) starts a fresh thread for it on *every* `menu:update`
   event, and it does `import uno`, loads graphics and writes ImageManagers
   there. Same rule violation as `nelson-prebuild`.
2. **PyUNO proxies die on whatever thread drops them.** The text cursor was
   created on the main thread by an MCP tool; its last reference went away — or
   the cyclic GC collected it — inside the menu-icon thread. Its C++ destructor
   needs the SolarMutex. So *any* background thread that runs Python can end up
   needing the SolarMutex, even one that never calls UNO itself.
3. **Lazy imports inside functions** mean the main thread takes the import lock
   at runtime, not only at startup.

Also seen: **two `mcp-doctype-pol` threads**. The `listChanged` poller was
started twice — the same shape as the duplicate HTTP server start in
`http-server-duplicate-start.md`.

`nelson-prebuild` was still alive and blocked in `getCurrentComponent` here too:
it is on the scene of both deadlocks.

### Not yet known

- Whether it reproduces on demand. One occurrence so far.
- Which interaction fired `menu:update` (candidates: the MCP edits, a
  document-type change, the sidebar deck being opened).

### Direction for the fix

Nelson threads must not run Python that can touch UNO objects — including
destructors — outside the main thread. Concretely: route `_update_menu_icons`
and `_prebuild_cache` through `post_to_main_thread`, start each poller once, and
hoist the lazy imports out of functions that run on the main thread.
