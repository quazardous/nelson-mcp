# Deadlock on cold start with a document (GitHub #35 / #37, tdf#173208)

**Status:** reproduced on demand and root-caused (2026-09-16, `make
coldstart-wbox`: 3 hangs in 17 cold starts with a document on the command
line). See "Root cause" below; fix in #2625.

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


## Second capture, 2026-09-16 20:57 — `/health` off the main thread

Backtrace: `deadlock-2026-09-16-health-sidebar.bt.txt` (wbox, gtk3, LibreOffice
26.2.6.3, Nelson at `a4aa1c4`+).

Not a cold start this time, but the same shape, and it involves a Nelson HTTP
thread touching UNO:

```
Thread 6  cppu_threadpool   holds SolarMutex (an external UNO client
                            dispatching .uno:SidebarDeck.NelsonDeck),
                            creating the Nelson panel -> into Python ->
                            waits on a Python lock
Thread 2  Thread-7 (process_request)   Nelson HTTP request thread ->
                            pyuno -> Desktop::getCurrentComponent ->
                            waits on SolarMutex
Thread 1  main              GdkThreadsEnter -> waits on SolarMutex
Threads 3, 4, 11            nelson-autoboot, mcp-doctype-pol x2: wait on
                            Python locks
```

The request on thread 2 was a `GET /health` poll: `McpProtocol.handle_health`
calls `doc_svc.get_active_document()` — a bare `desktop.getCurrentComponent()`
— **on the HTTP thread**, then `detect_doc_type` and `get_doc_id` (which, since
#2627, registers a document cache entry and a modify listener, also off the
main thread). That is the exact call on the Nelson side of the #37 capture.

Which Python lock threads 6/3/4/11 wait on is not visible without `py-bt`
(needs python debuginfo). Two `mcp-doctype-pol` threads also suggest that
poller is started twice.

The trigger here (an external UNO dispatch) is a test harness, not a user
action; but `/health` is polled by clients and launchers during startup, which
is exactly the #35/#37 window. **Lead for #2625: `/health` must not touch UNO
off the main thread** — answer from cached state, or marshal the document part
to the main thread with a short timeout and report `document: unknown` when it
cannot get it.


## Root cause, 2026-09-16 21:40 — reproduced by `make coldstart-wbox`

`scripts/coldstart_test.py` starts LibreOffice in wbox (gtk3, offscreen) with
a Writer document on the command line, polls `/health`, and captures gdb
when Nelson does not answer in 90 s. On the code of `5aadb97`: runs 11, 15
and 17 of 17 hung. Backtrace of run 11:
`deadlock-2026-09-16-coldstart-menu-icons.bt.txt`.

A lock-order inversion between the main thread and a Nelson thread:

```
main thread          holds SolarMutex (SynchronousDispatch loading the
                     command-line document), then
                     LayoutManager::implts_reset
                     ModuleUIConfigurationManagerSupplier::getUIConfigurationManager
                     -> waits on the supplier's mutex

Nelson thread        threading.Thread(target=_update_menu_icons), started at
"Thread-1 (_update_  the end of bootstrap: ImageManager lookup ->
menu_icons)"         ModuleUIConfigurationManagerSupplier::getUIConfigurationManager
                     holds the supplier's mutex, constructs a
                     ModuleUIConfigurationManager ->
                     -> waits on SolarMutex
```

Everyone else then queues on SolarMutex: `nelson-prebuild`
(`getCurrentComponent`, as in the #37 capture) and one HTTP thread per
`/health` poll (`getCurrentComponent` again) — which is why the server
socket accepts connections but never answers.

It needs a document on the command line (or Recovery) because only then is
the main thread creating a frame's layout — and taking the UI configuration
manager — during the few seconds Nelson bootstraps. That is why #37 first
looked tied to `RecoveryInfo/Crashed=true`, and why #35 (a mail attachment)
has the same shape.

Fix (#2625): no UNO from Nelson's own threads at startup — menu icons and
status events posted to the main thread, `nelson-prebuild` removed, the
doc-type poller replaced by document events, `/health` answered without
UNO, bootstrap no longer waiting for the main thread while holding a lock
UNO callbacks take.

## Verification by the reporter, 0.14.0, 2026-09-19 (GitHub #35)

On the machine where both hangs happened, now on LibreOffice 26.8.0.3:

- 20 replicated Thunderbird-attachment cold starts (read-only file in the
  mail client's private temp dir, handed over as a `file://` URL, with the
  mail client's environment including its `LD_LIBRARY_PATH`), plus one real
  double click: all came up with the document window, `/health` at ~0.55 s.
- 50 earlier cold starts (ordinary, recovery pending, `Crashed=true` forced)
  all came up, but by the reporter's own correction their oracle stopped at
  the lock file or the recovery dialog, so only the attachment runs cover a
  completed start.

Two corrections to the record above:

- **The NSS lead is closed.** The hung process had the mail client's
  `cert9.db` / `key4.db` open because LibreOffice inherits the mail client's
  environment; healthy starts from the attachment path open them too. It was
  a property of the launch path, not of the hang.
- **`kill -9` does not set `RecoveryInfo/Crashed=true`.** After `SIGKILL`
  the flag stays `false` and only a `RecoveryList` entry appears; the flag is
  written on shutdown. The `Crashed=true` precondition in #37's title has to
  be set by hand to be reproduced.

The A/B the reporter could not do is on our side: `make coldstart-wbox`
hung 5 of 20 before 78421fc, 0 of 50 after. Issues #35/#37 stay open until
2026-09-30 in case the hang comes back in normal use.
