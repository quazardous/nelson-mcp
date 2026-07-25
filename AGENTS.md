# AGENTS.md — Quickstart cheatsheet for AI agents

> [!IMPORTANT]
> Update this file after making nontrivial changes.

## Project

**Nelson MCP** — LibreOffice extension (Python/UNO) exposing document tools via MCP server.

## Where is what

```
plugin/main.py              Entry point, bootstrap
plugin/version.py           Version (single source of truth)
plugin/plugin.yaml          Global config schema
plugin/_manifest.py         Generated — do not edit
plugin/framework/           Core engine (services, tools, events, config, http, dialogs)
plugin/modules/<name>/      Feature modules (module.yaml + __init__.py + tools/ + services/)
extension/                  Static LO files (XCU, manifest, assets)
scripts/                    Build & deploy scripts
tests/                      Pytest suite (must pass — 'make test' is a gate)
Makefile                    All build/dev targets
install.ps1 / install.sh    Dev environment setup (installs bash, make, pyyaml, vendor deps)
```

## Setup & dev loop

```bash
./install.ps1               # Windows: installs deps (bash, make, pyyaml, vendor)
./install.sh                # Linux/macOS equivalent
make build                  # Build .oxt
make deploy                 # Build + reinstall + restart LO + show log
make log                    # Show ~/nelson.log
make test                   # Pytest
make set-config             # List all config keys
make help                   # All targets
```

> **AI agent note:** `make deploy` takes 60–120 seconds (kills LO, reinstalls
> extension, restarts LO, waits for bootstrap). **Do not** pipe its output
> (`| tail`, `| grep`) — this causes buffering freezes. Run it plain with a long
> timeout (300s+).

**Under wbox** (the usual agent loop) use the MCP tools instead, in this order —
never deploy while soffice is running:

```
mcp__lo-wbox__kill  →  mcp__lo-wbox__deploy  →  mcp__lo-wbox__launch
```

wbox can run headless, which is what an automated check should use; a visible
session is for when the assertion is something you have to *look* at.

> **`unopkg add -f` does not reliably replace the installed code.** It can
> report success while LibreOffice keeps running the previous version, which
> looks exactly like your fix not working — and costs a debugging cycle every
> time. If a change does not appear to take effect, verify what is actually
> deployed before doubting the code:
>
> ```bash
> NEW=$(ls -dt /tmp/lo_dev_profile/user/uno_packages/cache/uno_packages/*/nelson.oxt | head -1)
> grep -c my_new_symbol "$NEW/plugin/.../file.py"     # 0 = stale install, not a bug
> ```
>
> The reliable sequence is remove, wipe the cache, then add:
> `unopkg remove org.extension.nelson` → `rm -rf $PROFILE/user/uno_packages/cache
> $PROFILE/user/extensions` → `unopkg add -f`. Note `ls -d` is unsorted — use
> `ls -dt` or you will inspect an old cache directory and conclude the wrong thing.

> `Address already in use` on the HTTP port at startup is **not** benign, despite
> what this file used to say. It means the server did not bind, and the
> `HTTP server ready` line will be missing. It is a known intermittent bug —
> see `dev/bugs/http-server-duplicate-start.md`. Do not dismiss it; if the
> instance nonetheless answers, say so, because that combination is unexplained.

## Release

**Use `make release`.** Do not hand-roll `gh release create` — the script exists
because a release has gates that are easy to skip, most importantly that the
`.oxt` must contain the bundled Windows `pysqlite3` payload. A Linux build that
skips it produces an extension that installs and then fails on Windows.

```bash
# 1. bump EXTENSION_VERSION in plugin/version.py
# 2. add the matching section to CHANGELOG.md (the script extracts release notes from it)
make release-dry     # runs every gate, builds, publishes nothing
make release         # tags, pushes, creates the GitHub release with the .oxt
```

Gates: on `main`, no uncommitted tracked changes, in sync with origin, tag free,
CHANGELOG section present, and the built `.oxt` verified to carry the Windows
payload. `make test` must be green before you start.

The remaining manual gate is Windows: the `.oxt` is never registration-tested on
a non-UTF-8 / CJK Windows box, which is the class of bug behind #16/#17.

## Build pipeline

```
module.yaml -> generate_manifest.py -> _manifest.py + XCS/XCU + XDL
icon.svg    -> magick (ImageMagick)  -> build/generated/assets/*.png
extension/ + plugin/ + vendor/ + build/generated/ -> build_oxt.py -> .oxt
```

**Icons**: PNGs are generated from `extension/assets/icon.svg` into `build/generated/assets/` (requires ImageMagick `magick`). The Docker builder includes ImageMagick — use `make docker-build` if `magick` is not installed locally.

## Module structure

Each module in `plugin/modules/<name>/`:
- `module.yaml` — deps, config schema, actions, menus
- `__init__.py` — extends `ModuleBase`
- `tools/` — extends `ToolBase`
- `services/` — extends `ServiceBase`

Auto-discovered at build time by `generate_manifest.py`.

## Critical rules

- **UNO context**: NEVER store `ctx` from `initialize()`. Use `get_ctx()` from `framework/uno_context.py`.
- **Config**: Namespaced `"module.key"`, access via `ModuleConfigProxy`. Override: `NELSON_SET_CONFIG="key=val,..."`.
- **Document scoping**: `self.xFrame.getController().getModel()` — never `desktop.getCurrentComponent()`.
- **Sidebar**: Panels use programmatic layout (`plugin/framework/panel_layout.py`), not XDL. Use `create_panel_window()` + `add_control()` for new panels.
- **Writer drawing layer**: `hasattr(model, "getDrawPages")` is True for Writer. Use `supportsService()`.
- **Doc types**: `detect_doc_type()` returns `"writer"`, `"calc"`, `"impress"`, or `"draw"` (Impress and Draw are distinct). Use `doc_types = ["draw", "impress"]` for tools that work on both.
- **Doc-type param namespacing**: Unified tools use nested objects (`"writer": {...}`, `"calc": {...}`) for doc-type-specific params. `_flatten_doc_type_params()` in `ToolRegistry` merges the matching block before `execute()`. Tool code stays flat.
- **Draw page resolution**: Use `get_draw_page(ctx, page_index=, sheet_name=)` from `draw/bridge.py` — handles Writer (single page), Calc (per-sheet), Draw/Impress (multi-page).
- **Mutation classification is name-derived**: when a tool leaves `is_mutation` unset, `ToolBase.detects_mutation()` infers it from a name *prefix* (`get_`, `read_`, `list_`, `find_`, `search_`, `resolve_`…). Since tools are named `domain_verb`, the verb is at the **end**, so the fallback no longer matches — **always set `is_mutation` explicitly on a new tool**. Getting it wrong is silent: a read classified as a write auto-enables track changes, opens an undo context and burns an action id on every call. A tool that dispatches on an `action` argument should override `detects_mutation(**kwargs)` instead.
- **Tool names are strings, never identifiers**: renaming a tool means editing string literals only. `image_utils.insert_image()`, `ImageService.generate_image()` and the vendored `aihordeclient.generate_image()` are *functions* that happen to share names with tools — a blind search/replace corrupts them. Never touch `plugin/lib/` (vendored).
- **Former names must keep working**: add the old name to `aliases` rather than breaking callers. For a merged tool use the mapping form, which pins the arguments the old name implied: `aliases = {"add_table_rows": {"action": "add", "axis": "rows"}}`.

## Cross-renderer testing

Sidebar panels use programmatic layout (no XDL) — test on multiple VCL backends to catch rendering issues:

```bash
SAL_USE_VCLPLUGIN=kf6 make deploy      # KDE/Qt6 (install: dnf install libreoffice-kf6)
SAL_USE_VCLPLUGIN=gtk3 make deploy     # GNOME (default)
SAL_USE_VCLPLUGIN=gtk4 make deploy     # GTK4
SAL_USE_VCLPLUGIN=gen make deploy      # X11 pure
```

Check: sidebar controls visible and non-overlapping, resize works, settings dropdowns functional. If the backend is missing, LO silently falls back to default — verify visually.

## HTTP API

See [`API.md`](API.md) for the full HTTP API reference.

Key endpoints on `http://localhost:8766`:
- `GET /health` — health check (always on)
- `GET /api/config?module=X` — read config (requires `http.enable_config_api = true`)
- `POST /api/config` — write config (requires `http.enable_config_api = true`)
- `POST /api/debug` — debug actions: eval, call_tool, trigger, services (requires `debug.enable_api = true`)

> Both `/api/config` and `/api/debug` are **disabled by default**. Enable them in Options.

## Verifying a change

Nelson runs inside LibreOffice, so a change is not verified until a real
LibreOffice has run it. `make test` covers pure-Python framework logic only —
run it (it must stay green), but it proves nothing about UNO behaviour.

```bash
make test     # fast, pure Python, never starts LibreOffice
make smoke    # installs the built .oxt, runs LO headless, drives it over MCP
```

`make smoke` is the one that can catch a real regression: it asserts the bugs
that actually shipped (#11 mutation classification and aliases, #19 save-as,
#20 doc_id, #22 change recording), checking the md5 of files on disk and the
live document through the UNO socket rather than the tool's own answer.
`scripts/release.sh` runs it as a hard gate. Add a check there whenever you fix
something a unit test cannot see — that is the whole point of it.

**Do not trust a tool's own response as proof.** Asking Nelson whether Nelson
worked is circular: if the bug is in how it reports state, the check cannot see
it. Verify against something outside the tool:

| what you changed | check it against |
|---|---|
| anything written to a file | the bytes on disk — `unzip -p f.xlsx xl/comments1.xml`, `unzip -p f.odt content.xml` |
| live document state | the UNO socket (below) — a process that is not Nelson |
| anything visual (layout, overlap, position) | `mcp__lo-wbox__screenshot`. A response saying `status: ok` cannot tell you an image overlaps the body text |
| anything at all | the **live** log, for errors it did not report to you |

### Reading live document state from outside

The dev instance accepts UNO connections on port 2002
(`--accept=socket,host=localhost,port=2002;urp;`). Any external process can
inspect the *same live objects* — useful for state Nelson exposes no tool for:

```python
import uno
local = uno.getComponentContext()
ctx = local.ServiceManager.createInstanceWithContext(
    "com.sun.star.bridge.UnoUrlResolver", local).resolve(
    "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
desktop = ctx.ServiceManager.createInstanceWithContext(
    "com.sun.star.frame.Desktop", ctx)
comps = desktop.getComponents().createEnumeration()
while comps.hasMoreElements():
    doc = comps.nextElement()
    print(doc.getURL(), doc.getPropertyValue("RecordChanges"))
```

### Logs

| File | Content |
|------|---------|
| `dev/lo-wbox/log/nelson.log` | **the live plugin log** when running under wbox — this is the one you want |
| `~/nelson.log` | plugin log for a *native* LO run. **Stale under wbox** — it keeps an old session's content and will happily answer "no errors" about a run that never happened |
| `~/soffice-debug.log` | LO internal errors |

`mcp__lo-wbox__nelson_log` reads the correct path. Empty log = `main.py` never
loaded = extension not installed (`make check-ext`).
