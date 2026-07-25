# Developer Guide

## Prerequisites

### Required

| Tool | Min version | Install (Linux) | Install (Windows) |
|------|-------------|-----------------|-------------------|
| **Python** | 3.8+ | `sudo dnf install python3` / `sudo apt install python3` | [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3` |
| **PyYAML** | any | `pip install --user pyyaml` or `uv pip install pyyaml` | `pip install pyyaml` |
| **LibreOffice** | 7.0+ | `sudo dnf install libreoffice` / `sudo apt install libreoffice` | [libreoffice.org](https://www.libreoffice.org/download/) |
| **make** | any | `sudo dnf install make` / `sudo apt install make` | `winget install GnuWin32.Make` |
| **git** | any | `sudo dnf install git` / `sudo apt install git` | `winget install Git.Git` |
| **pip** or **uv** | any | Usually bundled with Python | `pip` bundled; uv: `winget install astral-sh.uv` |

### Windows only

| Tool | Purpose | Install |
|------|---------|---------|
| **bash** (Git Bash) | Makefile uses Unix commands | Comes with Git for Windows |

### Optional

| Tool | Purpose | Install |
|------|---------|---------|
| **openssl** | MCP HTTPS/TLS certificates | Usually pre-installed; Windows: `winget install ShiningLight.OpenSSL` |
| **uv** | Faster pip alternative | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## Check your setup

Run the check script to verify everything is installed:

```bash
# Linux / macOS
bash scripts/check-setup.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\check-setup.ps1
```

The script outputs a copy-paste brief at the end — useful for sharing in issues.

## Docker build (no local setup needed)

If you just want to build the `.oxt` without installing Python, PyYAML, or any local dependencies, use the Docker build:

```bash
make docker-build
# or directly:
docker compose -f builder/docker-compose.yml up --build
```

The built extension will be at `build/nelson.oxt`. This is the recommended approach for contributors who don't have the full dev stack installed.

To use Docker for **all** build targets (`deploy`, `install`, etc.):

```bash
# One-shot:
make deploy USE_DOCKER=1

# Persistent (create a gitignored Makefile.local):
echo "USE_DOCKER = 1" > Makefile.local
make deploy   # now uses Docker automatically
```

**Requirements:** Docker with Compose plugin (`docker compose`).

## First-time setup

```bash
# 1. Clone the repo
git clone https://github.com/quazardous/localwriter.git
cd localwriter
git checkout framework

# 2. Install dev dependencies (PyYAML, vendor libs, bash/make on Windows)
./install.sh              # Linux / macOS
# .\install.ps1           # Windows (PowerShell as Admin for winget)

# 3. Build and deploy
make deploy
```

## Build commands

| Command | What it does |
|---------|-------------|
| `make build` | Generate manifests + vendor deps + assemble `.oxt` |
| `make deploy` | **Main dev loop**: build + kill LO + unopkg reinstall + restart LO + show log |
| `make install` | Build + install via `scripts/install-plugin.sh` (interactive, asks before killing LO) |
| `make install-force` | Same as `install` but non-interactive |
| `make uninstall` | Remove extension via unopkg |
| `make clean` | Delete `build/` and `__pycache__` |

### `deploy` vs `install`

- **`make deploy`** — automated: kills LO, reinstalls, restarts, shows log. Use this for daily dev.
- **`make install`** — interactive: prompts before killing LO and before restarting. Use this for first install or when you want control.

Both do the same thing (build + unopkg remove/add), just with different levels of automation.

## Dev iteration shortcuts

| Command | What it does |
|---------|-------------|
| `make cache` | Hot-deploy to LO cache via rsync (no unopkg, faster but less reliable) |
| `make dev-deploy` | Symlink project into LO extensions dir (changes apply on restart) |
| `make dev-deploy-remove` | Remove the dev symlink |
| `make repack` | Re-zip `build/bundle/` without regenerating (fast after manual edits) |
| `make repack-deploy` | Repack + kill LO + reinstall + restart + show log |

## LibreOffice commands

| Command | What it does |
|---------|-------------|
| `make lo-start` | Launch LO with `--writer --norestore` + WARN/ERROR logging |
| `make lo-start-full` | Same but with INFO level (verbose, slow startup) |
| `make lo-kill` | Kill all LO processes |
| `make lo-restart` | Kill + wait + start |

## Config overrides

Nelson config can be overridden at launch time via the `NELSON_SET_CONFIG` environment variable. This avoids changing persistent settings in LO's Options dialog.

**Format:** `"key=value,key=value,..."` — values are auto-coerced to the type declared in the module schema (boolean, integer, string).

```bash
# Via make (any target that starts LO)
make deploy NELSON_SET_CONFIG="core.log_level=DEBUG"
make lo-start NELSON_SET_CONFIG="mcp.port=9000,core.log_level=DEBUG"

# Or via environment variable directly
NELSON_SET_CONFIG="core.log_level=DEBUG" make lo-start
```

### Common overrides

| Key | Values | Description |
|-----|--------|-------------|
| `core.log_level` | `DEBUG`, `INFO`, `WARN`, `ERROR` | Plugin log verbosity (default: `WARN`). Set to `DEBUG` for full diagnostics in `~/nelson.log`. |
| `mcp.port` | integer | MCP server port (default: `2044`) |
| `mcp.host` | string | MCP server bind address (default: `127.0.0.1`) |
| `http.port` | integer | HTTP API port |
| `debug.enable_api` | `true`/`false` | Enable `/api/debug` endpoint |

### List all available config keys

```bash
make set-config
```

This shows all module config keys with their types and defaults.

## Cross-renderer testing

LibreOffice uses VCL backend plugins for rendering. The sidebar panels use programmatic layout (`setPosSize()` + `XWindowListener`) instead of XDL files to ensure consistent rendering across all backends.

### Available backends

List installed VCL plugins:

```bash
ls /usr/lib64/libreoffice/program/libvclplug_*
```

Common backends: `gtk3`, `gtk4`, `kf6` (KDE/Qt6), `gen` (X11, no toolkit).

### Installing additional backends

```bash
# Fedora — install KDE/Qt6 backend alongside GTK (non-destructive)
sudo dnf install libreoffice-kf6

# Arch/Manjaro (KDE) — install GTK backend alongside Qt
sudo pacman -S libreoffice-fresh  # includes all VCL backends
# or if using libreoffice-still:
sudo pacman -S libreoffice-still
```

On Arch, `libreoffice-fresh` ships all VCL backends (gtk3, gtk4, qt5, qt6, gen) in one package. No extra packages needed.

### Testing with a specific backend

Set `SAL_USE_VCLPLUGIN` before any `make` target that starts LO:

```bash
# Deploy and start LO with the KDE/Qt6 backend
SAL_USE_VCLPLUGIN=kf6 make deploy

# Just restart LO with a different backend (no rebuild)
SAL_USE_VCLPLUGIN=kf6 make lo-restart

# Other backends
SAL_USE_VCLPLUGIN=gtk3 make deploy     # GNOME (default)
SAL_USE_VCLPLUGIN=gtk4 make deploy     # GTK4
SAL_USE_VCLPLUGIN=gen make deploy      # X11 pure (no toolkit)
```

If the requested backend is not installed, LO silently falls back to the default. Verify which plugin is actually loaded by checking for visual differences (widget style, font rendering).

### What to check

1. Sidebar chat panel — all 6 controls visible, no overlap
2. Resize sidebar — controls reflow correctly
3. Settings panel — AI dropdowns render and respond to clicks
4. Modal dialogs (Tools > Nelson MCP options) — layout is acceptable

## Dev MCP servers (Linux)

For visual debugging and automated testing, the project provides MCP servers that run LibreOffice in an isolated nested compositor. This allows taking screenshots, injecting keyboard/mouse input, and deploying the extension — all from Claude Code.

### Prerequisites

```bash
# Fedora
sudo dnf install weston cage grim xdotool scrot ImageMagick uv

# Ubuntu/Debian
sudo apt install weston cage grim xdotool scrot imagemagick
pip install uv
```

Then install the Python dependencies:

```bash
cd dev/lo-dev-mcp
uv venv && uv pip install -e ../compositor && uv pip install mcp pyyaml
```

### MCP entries in `.mcp.json`

The project `.mcp.json` defines three MCP servers:

| Server | Type | Purpose |
|--------|------|---------|
| `nelson` | HTTP `:8766` | Production Nelson extension (host LO) |
| `nelson-dev` | HTTP `:8767` | Nelson extension inside the compositor LO |
| `lo-dev` | stdio | Compositor automation (launch, screenshot, input, deploy) |

`nelson` and `nelson-dev` are standard Nelson HTTP MCP endpoints — they expose the same document manipulation tools. The difference is which LO instance they connect to.

`lo-dev` is the compositor control server. It manages the nested Wayland compositor and the isolated LO instance running inside it. The `nelson-dev` port (8767) must match the `nelson_port` in `dev/lo-dev-mcp/config.yaml` — `lo-dev` injects this port via `NELSON_SET_CONFIG` when launching the caged LO.

### Compositor backends

| Backend | Window | Resize | Screenshot | Best for |
|---------|--------|--------|------------|----------|
| **weston** (default) | Resizable, movable | Yes (restart) | `weston-screenshooter` | Daily dev |
| **cage** | Kiosk, no decorations | No | `grim` | CI / headless |

Configure in `dev/lo-dev-mcp/config.yaml`:

```yaml
compositor: weston       # or "cage"
screen: "1280x800"
weston_shell: kiosk      # "kiosk" or "desktop"
weston_backend: x11      # x11 = resizable window on host
app:
  doc_type: writer
  vcl_plugin: gtk3
  profile_dir: /tmp/lo_dev_profile
  nelson_port: 8767
```

### Autonomous dev with Claude Code

The `lo-dev` MCP gives Claude Code full control over an isolated LibreOffice instance: launch, screenshot, mouse/keyboard input, deploy. This allows Claude to work autonomously — build, deploy, visually inspect, click through UI, fix issues — without manual intervention.

**Setup:** after installing prerequisites, run `/mcp` in Claude Code to connect to `lo-dev`.

**Workflow:**
1. `lo-dev` > `launch` — starts a weston compositor window with LO inside
2. `lo-dev` > `deploy` — builds Nelson `.oxt` and installs it into the caged LO
3. `lo-dev` > `screenshot` — Claude sees the LO UI and can analyze it
4. `lo-dev` > `click` / `key` / `type_text` — Claude interacts with LO (menus, dialogs, etc.)
5. `nelson-dev` tools become available to test Nelson document manipulation on the caged instance
6. `lo-dev` > `kill` — clean up when done

Claude can iterate on code, redeploy, and visually verify the result in a loop — fully autonomous.

See `dev/README.md` for the full tool list and `mcp-test.py` CLI usage.

## Logs and debugging

| File | Content |
|------|---------|
| `~/nelson.log` | Plugin log — native/production LO (overwritten each session) |
| `~/soffice-debug.log` | LO internal errors |
| `dev/lo-dev-mcp/log/nelson.log` | Plugin log — **dev compositor** LO instance |

Symlinks exist in the project root for convenience (`./nelson.log`, `./soffice-debug.log`). Created by `scripts/check-setup.sh`.

> **Dev vs native logs:** When using the `lo-dev` MCP compositor, Nelson logs go to `dev/lo-dev-mcp/log/nelson.log` (not `~/nelson.log`). The `lo-dev` > `tail_log` tool reads from this path.

**Enable verbose logging** for a session (default is `WARN`):

```bash
make lo-start NELSON_SET_CONFIG="core.log_level=DEBUG"
```

This logs tool discovery, frame enumeration, config reads, and all tool executions to `~/nelson.log`.

```bash
make log          # Show plugin log
make log-tail     # Tail plugin log (live)
make lo-log       # Show LO error log
```

**Empty log = extension not loaded.** Check:

1. `make check-ext` — verify extension is registered
2. LO sidebar: View > Sidebar > Nelson MCP panel
3. If crash on startup, try `make nuke-cache` then `make deploy`

## Cache management

| Command | What it does |
|---------|-------------|
| `make clean-cache` | Repair extension cache (fix revoked flags, remove locks) |
| `make nuke-cache` | Wipe entire cache (requires `make deploy` after) |
| `make unbundle` | Remove bundled dev symlink |

## Release

1. Bump version in `plugin/version.py`
2. Update `CHANGELOG.md`
3. Commit and push
4. Build and create GitHub release with the `.oxt` artifact:

```bash
make build
gh release create v1.x.y --target framework --title "v1.x.y" --notes "changelog"
gh release upload v1.x.y build/nelson.oxt
```

## Tests

```bash
make test
```

Runs pytest on `tests/`. The suite is expected to pass in full — treat a failure as a regression, not as noise.

## Troubleshooting

### `std::bad_alloc` during `unopkg add`

**Cause**: running `unopkg` from a Python venv instead of system Python.

**Fix**: deactivate any venv before running `make deploy`:

```bash
deactivate          # if in a venv
make deploy
```

### Panel is empty / no sidebar

1. Check `~/nelson.log` — if empty, extension didn't load
2. `make nuke-cache && make deploy`
3. In LO: View > Sidebar, look for the Nelson MCP panel

### LO crashes on second startup

Extension cache is corrupted from a failed install.

```bash
make lo-kill
make nuke-cache
make deploy
```

### `unopkg not found`

LibreOffice's `program/` directory is not on PATH. The scripts search common locations automatically. If it still fails, find it manually:

```bash
# Linux
find /usr -name unopkg -type f 2>/dev/null
find /opt -name unopkg -type f 2>/dev/null

# Windows (PowerShell)
Get-ChildItem "C:\Program Files\LibreOffice" -Recurse -Filter "unopkg.exe"
```

### XCS/XCU files — are they needed?

Yes. These are LibreOffice's standard mechanism for declarative configuration. Each module declares its config schema in `module.yaml`, and the build generates the corresponding XCS (schema) and XCU (defaults) files. They are required for the LO Options dialog and for config persistence across sessions.
