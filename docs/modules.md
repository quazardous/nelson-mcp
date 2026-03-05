# Module Framework

## Core rule

**One module = one `module.yaml` = one config namespace = at most one Options page.**

## Module layout

```
plugin/modules/my_module/
├── module.yaml          # Manifest (deps, config, actions, menus, shortcuts)
├── __init__.py          # Module class (extends ModuleBase)
├── tools/               # Auto-discovered ToolBase subclasses
├── services/            # ServiceBase subclasses
├── icons/               # 16x16 PNGs for menus
└── dialogs/             # XDL for modal dialogs (optional)
```

## module.yaml

```yaml
name: my_module                            # Dotted for submodules: tunnel.ngrok
title: My module
requires: [document, config, events]       # Service dependencies
provides_services: []                      # Exported services

actions:
  my_action:
    title: "Do Something"

menus:
  - action: my_action
    context: [writer, calc]                # Doc type filter

shortcuts:
  my_action:
    key: Q_MOD1
    context: [writer, calc]

config:
  my_field:
    type: string             # string, int, float, boolean
    default: "hello"
    widget: text             # text, textarea, password, number, slider,
                             # checkbox, select, file, folder, list_detail, button
    label: My Field
    helper: "Help text"      # Optional, shown in Options UI
    public: false            # true = other modules can read
    internal: false          # true = hidden from Options UI
```

`select` requires `options` (static) or `options_provider` (dynamic function). `list_detail` requires `item_fields` for structured JSON data. `button` requires `action` (`"module.path:function_name"`) — no `type`/`default` needed, it doesn't store a config value. `button` also supports an optional `confirm` string — when set, a Yes/No dialog is shown before executing the action.

## Lifecycle

Modules load in dependency order (topological sort on `requires`).

1. **`initialize(services)`** — register services, subscribe events, read config
2. **`start(services)`** — VCL main thread (UI setup)
3. **`start_background(services)`** — background thread (servers, connections)
4. **`shutdown()`** — cleanup

## Services

Singletons registered during `initialize()`, accessed by name:

```python
services.register(MyService())       # MyService.name = "my_service"
svc = services.my_service            # Attribute access
```

## Tools

Auto-discovered from `tools/` — any `ToolBase` subclass is registered. Key attributes: `name`, `description`, `parameters` (JSON Schema), `doc_types`, `tier` ("core"/"extended"), `intent`.

## Config access

```python
cfg = services.config.proxy_for(self.name)
cfg.get("port")                      # Auto-prefixed: "my_module.port"
cfg.set("port", 9000)                # Writes to LO registry
```

Cross-module reads work only for `public: true` fields. Environment overrides: `NELSON_SET_CONFIG="key=val"`.

## Events

Synchronous pub/sub: `events.subscribe("config:changed", callback)` / `events.emit("my:event", **data)`.

Key events: `config:changed`, `tool:executing`, `tool:completed`, `tool:failed`, `menu:update`.

## Submodules and config_inline

Submodules use dotted names (`tunnel.ngrok`). `config_inline: true` merges their Options fields into the parent page. Each module keeps its own config namespace — only the UI is grouped.

```yaml
name: tunnel.ngrok
config_inline: true          # Appears on parent "tunnel" Options page
```

This is the answer to "merge modules vs split config pages": **modules stay separate, `config_inline` merges the UI**.

## UNO context

Never store `ctx` from `initialize()`. Use `get_ctx()` from `plugin.framework.uno_context` for a fresh context every time.

## Creating a module

1. Create `plugin/modules/my_module/module.yaml`
2. Create `plugin/modules/my_module/__init__.py` with `Module(ModuleBase)`
3. `make deploy` — auto-discovered, everything generated

## Build pipeline

```
module.yaml → generate_manifest.py → _manifest.py + XCS/XCU + XDL + Addons.xcu + Accelerators.xcu
```
