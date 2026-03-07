# Nelson HTTP API

Base URL: `http://localhost:8766` (configurable via `http.port`)

## Endpoints

### `GET /`

Server info and list of all routes.

```json
{"name": "Nelson", "version": "0.2.0", "routes": ["GET /health", ...]}
```

### `GET /health`

Health check. Returns version.

```json
{"status": "healthy", "server": "Nelson", "version": "0.2.0"}
```

### `GET /api/config`

> **Requires** `http.enable_config_api = true` (disabled by default).

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
  -d '{"core.log_level": "DEBUG"}'
```

Returns `200` on success, `207` on partial failure with `errors` array.

### `GET /api/debug`

> **Requires** `debug.enable_api = true` (disabled by default).

Lists available debug actions and all registered tools.

### `POST /api/debug`

> **Requires** `debug.enable_api = true` (disabled by default).

Debug endpoint with multiple actions:

| Action | Description | Body |
|---|---|---|
| `eval` | Evaluate Python expression | `{"action": "eval", "code": "1+1"}` |
| `exec` | Execute Python code | `{"action": "exec", "code": "_result = 'hello'"}` |
| `call_tool` | Call a registered MCP tool | `{"action": "call_tool", "tool": "list_jobs", "args": {}}` |
| `trigger` | Simulate a menu action | `{"action": "trigger", "command": "ai_images.ai_index_toggle"}` |
| `services` | List registered services | `{"action": "services"}` |
| `config` | Get/set a config value | `{"action": "config", "key": "mcp.port"}` |

```bash
# List jobs via debug
curl -X POST http://localhost:8766/api/debug \
  -H "Content-Type: application/json" \
  -d '{"action": "call_tool", "tool": "list_jobs", "args": {"limit": 5}}'

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
