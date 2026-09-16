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
