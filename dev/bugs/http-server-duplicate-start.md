# HTTP server failed to bind on restart (fixed)

**Status:** fixed — found while working on #11.

## Symptom

Every `kill → deploy → launch` cycle logged, in
`dev/lo-wbox/log/nelson.log`:

```
[ERROR] nelson.http — Failed to start HTTP server
...
OSError: [Errno 98] Adresse déjà utilisée
```

and the `HTTP server ready — …` line was **never** emitted, even though
the MCP endpoint answered requests. The bind lost a race with the
previous LibreOffice process, which still held the port for a moment
after being killed.

## Causes

1. `plugin/framework/http_server.py` bound the socket once, with no
   tolerance for the restart race, and `_ThreadedHTTPServer` did not set
   `allow_reuse_address`.
2. `plugin/modules/http/__init__.py` `_start_server()` did
   `self._server = None` in its `except`, so a failed start could drop
   the handle to a listener that was still bound — leaving
   `_stop_server()` a no-op and the status/menu reporting a server that
   was not there (or vice versa).
3. Nothing prevented `_start_server()` from running twice (reachable from
   `start_background`, the `config:changed` handler, and the menu toggle).

## Fix

- `allow_reuse_address = True` on `_ThreadedHTTPServer`.
- `HttpServer._bind()` retries EADDRINUSE 5 times, 0.4 s apart, then
  raises a plain, actionable message naming the port instead of a raw
  traceback. Other `OSError`s still propagate immediately.
- `_start_server()` returns early when a server is already running, and
  only assigns `self._server` after a successful start — a failure never
  discards an existing handle.

## Verification

Same `kill → deploy → launch` cycle that reproduced it:

- errors in the log: **0** (was 1 per launch)
- `HTTP server ready — http://localhost:8767 (9 routes)` now logged
- `tools/list` answers normally (100 tools)
