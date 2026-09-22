# Nelson HTTP API

Base URL: `http://localhost:8766` (configurable via `http.port`)

## Access token

Off by default. Once `http.auth_token` is set, **every** request needs it — the
MCP endpoints, `/health`, `/api/config`, everything — or gets `401` with
`WWW-Authenticate: Bearer`:

```
Authorization: Bearer <token>
```

For clients that can only be given a URL, `?token=<token>` is accepted too. The
header is preferable: a token in a URL is recorded wherever URLs are logged.
The comparison is constant-time. CORS preflights (`OPTIONS`) never carry
credentials and are not checked; the browser-origin rule below still applies to
them.

The server **refuses to start** on any host other than `localhost` /
`127.0.0.1` / `::1` while no token is set, and the tunnel module refuses to
start a tunnel. Clearing the token while bound elsewhere stops the server
rather than leaving it open. Changing the token applies immediately.

## Browser origins

The server validates the `Origin` header on every request, as the MCP
Streamable HTTP transport requires.

- **No `Origin` header** — allowed. Every MCP client (Claude Code, OpenCode,
  ollmcp, anything speaking plain HTTP) lands here, and nothing about it
  changed.
- **`Origin` on the `http.allowed_origins` list** — allowed. The response
  echoes that exact origin; the server never answers `*`.
- **Any other `Origin`** — `403`, with no CORS headers, preflight included.

`http.allowed_origins` is a comma-separated list, **empty by default**, so no
web page can call the server until you name one. This is what stops a page the
user happens to be visiting from driving LibreOffice: binding to localhost does
not, on its own, keep a browser out.

## Endpoints

### `GET /`

Server info and list of all routes.

```json
{"name": "Nelson", "version": "0.2.0", "routes": ["GET /health", ...]}
```

### `GET /health`

Readiness probe. Answers without touching LibreOffice from the HTTP thread:
the `document` block comes from a snapshot kept up to date on the main thread,
after every tool call and on document events.

```json
{"status": "ok", "version": "0.14.2", "session_id": "…", "tools": 145,
 "document": {"available": true, "doc_type": "writer", "doc_id": "…"},
 "default_save_dir": "/home/me/Documents"}
```

`document.pending: true` means Nelson has not read the active document yet,
right after startup.

### Config API

> **Requires** `http.enable_config_api = true` (disabled by default; switch it
> on in Options > Nelson > Http).

Lets a client, typically the agent itself, read and change Nelson's settings
without anyone opening Options: the read limits, the exchange format, the name
on its tracked changes, its MCP endpoints. Changes apply at once.

It cannot change what protects the user. These settings are **reserved to
Options**:

| Reserved | Why |
|---|---|
| `http.*` | the access token, address and port, allowed origins, SSL, and this API's own switch |
| `tunnel.*` | publishing the server |
| `debug.*` | the debug API, which runs arbitrary code |
| `launcher.*` | the terminal and arguments of commands Nelson runs |
| `*.instances` | folders the tools can reach; AI providers' endpoints and keys |
| `core.force_track_changes` | the guard against an agent switching off change recording |

Secrets are never returned: the token, password-type settings and the keys
inside provider entries read as `"***"` when set.

### `GET /api/config`

Read configuration values.

| Query param | Example | Returns |
|---|---|---|
| (none) | `/api/config` | All config |
| `?key=X` | `?key=ai_images.sdapi.instances` | Single key value |
| `?module=X` | `?module=ai_images` | All keys for module (auto-adds `.` prefix) |
| `?prefix=X` | `?prefix=ai_images.sdapi` | All keys starting with prefix |

```bash
# All config for a module
curl "http://localhost:8766/api/config?module=images.folder"

# Single key
curl "http://localhost:8766/api/config?key=ai_images.sdapi.instances"
```

### `POST /api/config`

> **Requires** `http.enable_config_api = true` (disabled by default).

Write configuration values. Body is a JSON object of key-value pairs.

```bash
curl -X POST http://localhost:8766/api/config \
  -H "Content-Type: application/json" \
  -d '{"writer.max_content_chars": 200000, "core.document_format": "html"}'
```

| Status | Meaning |
|---|---|
| `200` | every key written: `{"written": [...]}` |
| `207` | some keys failed: `written` plus an `errors` array |
| `403` | the body names a reserved setting: **nothing is written**, and `refused` lists the reserved keys |

```json
{"error": "reserved_setting", "refused": ["http.auth_token"],
 "message": "These settings can only be changed in Tools > Options > Nelson, not through the config API: http.auth_token. Nothing was written."}
```

### `GET /api/debug`

> **Requires** `debug.enable_api = true` (disabled by default).

Lists available debug actions and all registered tools.

### `POST /api/debug`

> **Requires** `debug.enable_api = true` (disabled by default).

It runs arbitrary Python inside LibreOffice, so it can read and change any
setting, reserved or not. Keep it off outside development; it cannot be
switched on through the config API.

Debug endpoint with multiple actions:

| Action | Description | Body |
|---|---|---|
| `eval` | Evaluate Python expression | `{"action": "eval", "code": "1+1"}` |
| `exec` | Execute Python code | `{"action": "exec", "code": "_result = 'hello'"}` |
| `call_tool` | Call a registered MCP tool | `{"action": "call_tool", "tool": "job_list", "args": {}}` |
| `trigger` | Simulate a menu action | `{"action": "trigger", "command": "ai_images.ai_index_toggle"}` |
| `services` | List registered services | `{"action": "services"}` |
| `config` | Get/set a config value | `{"action": "config", "key": "mcp.port"}` |

```bash
# List jobs via debug
curl -X POST http://localhost:8766/api/debug \
  -H "Content-Type: application/json" \
  -d '{"action": "call_tool", "tool": "job_list", "args": {"limit": 5}}'

# Trigger menu action
curl -X POST http://localhost:8766/api/debug \
  -H "Content-Type: application/json" \
  -d '{"action": "trigger", "command": "ai_images.ai_index_toggle"}'
```

### MCP (Model Context Protocol)

| Endpoint | Description |
|---|---|
| `GET /sse` | SSE transport (Server-Sent Events) |
| `POST /sse` | SSE message endpoint |
| `POST /messages` | Streamable HTTP transport |
| `GET /mcp` | MCP info |
| `POST /mcp` | MCP JSON-RPC |
| `DELETE /mcp` | Close MCP session |

## Common config keys

| Key | Description |
|---|---|
| `core.log_level` | Log level: DEBUG, INFO, WARN, ERROR |
| `http.port` | HTTP server port (default: 8766) |
| `http.enable_config_api` | Enable `/api/config` endpoint (default: false) |
| `debug.enable_api` | Enable `/api/debug` endpoint (default: false) |
| `ai_images.default_instance` | Default AI image provider |
| `ai_images.interrogate_instance` | Provider for CLIP interrogation |
| `ai_images.save_to_gallery` | Auto-save generated images to gallery |
| `ai_images.sdapi.instances` | JSON array of SD WebUI instances |
| `images.folder.instances` | JSON array of folder gallery configs |

## Instance config (JSON arrays)

### `ai_images.sdapi.instances`

```json
[{
  "name": "juggernaut_xl",
  "endpoint": "http://127.0.0.1:7860",
  "model": "juggernautXL_v9Lightning.safetensors",
  "resolution": "1024x1024",
  "sampler": "DPM++ SDE Karras",
  "steps": 6,
  "cfg_scale": 2.0,
  "negative_prompt": "ugly, deformed, ...",
  "hires_fix": false,
  "hires_scale": 1.5,
  "hires_steps": 10,
  "hires_denoising": 0.4
}]
```

### `images.folder.instances`

```json
[{
  "name": "My Photos",
  "path": "C:\\Users\\david\\Pictures",
  "recursive": true,
  "writable": true,
  "ai_index": true,
  "extensions": "jpg,jpeg,png,gif,bmp,tiff,tif,webp,svg",
  "sync_gallery": false
}]
```
