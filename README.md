# Nelson MCP

A LibreOffice extension that turns your documents into an MCP server. External AI clients connect over HTTP and get full access to document tools — reading, editing, navigating, formatting, and more.

Works with any MCP-compatible client: Claude Code, OpenCode, Goose, ollmcp, etc.

## How it works

Nelson MCP runs an HTTP server inside LibreOffice and speaks the [Model Context Protocol](https://modelcontextprotocol.io/). AI agents connect to it and use tools to interact with your open document — no copy-paste, no file export.

```
┌─────────────┐       HTTP/MCP        ┌──────────────┐
│  AI Client   │ ──────────────────── │  LibreOffice  │
│ (Claude Code,│   tools/call         │  + Nelson MCP │
│  OpenCode…)  │ ◄──────────────────  │               │
└─────────────┘    tool results       └──────────────┘
```

## Features

- **148 document tools** — read content, edit text, manage styles, insert images, handle tables, charts, conditional formatting, hyperlinks, track changes, navigate headings, search, and more
- **Custom MCP endpoints** — expose only the tools your agent needs. Built-in presets (minimal, writer-edit, writer-read, calc, gallery) or create your own filtered endpoints
- **Writer, Calc, Draw, Impress** — tools adapt to the active document type
- **Calc `=PROMPT()`** — call an LLM directly from a spreadsheet cell
- **Built-in launchers** — launch Claude Code, Gemini CLI, or OpenCode directly from LibreOffice with one click. Nelson handles MCP config, prompt injection, and working directory setup automatically
- **AI image generation** — generate and edit images from text prompts using Stable Diffusion (A1111/Forge), OpenAI, or AI Horde. One-click detect/install/launch for Automatic1111
- **Beginner-friendly setup** — all tools come with install buttons, auto-detection of existing installations, and guided configuration. No manual config files to edit
- **Tunnels** — expose the MCP server externally via ngrok, Cloudflare, bore, or Tailscale
- **SSL** — optional HTTPS with auto-generated certificates
- **Modular** — each feature is a self-contained module with its own config, services, and tools

## Install

1. Download the latest `.oxt` from the [releases page](https://github.com/quazardous/nelson-mcp/releases)
2. In LibreOffice: **Tools > Extension Manager > Add**
3. Restart LibreOffice
4. The MCP server starts automatically (default: `http://localhost:8766/mcp`)

## Quick start

Once installed, point your MCP client at the server:

```json
{
  "mcpServers": {
    "nelson": {
      "type": "http",
      "url": "http://localhost:8766/mcp"
    }
  }
}
```

Open a document in LibreOffice, then ask your AI client to read or edit it.

**For AI agents:** see [`QUICKSTART.md`](QUICKSTART.md) — a step-by-step guide for LLM agents on how to discover documents, navigate structure, and use tools effectively.

## Modules

| Module | Description |
|--------|-------------|
| `core` | Document access, config, events, formatting |
| `writer` | Content editing, comments, styles, tables, change tracking |
| `writer.nav` | Heading tree, bookmarks, proximity navigation |
| `writer.index` | Full-text search with Snowball stemming |
| `calc` | Cells, sheets, formulas, charts, conditional formatting, comments |
| `draw` | Shapes, pages, slides, placeholders, master slides, transitions (Draw and Impress) |
| `images` | Image generation and editing (pluggable providers) |
| `batch` | Multi-tool execution with variable chaining |
| `http` | Shared HTTP server with optional SSL |
| `mcp` | MCP JSON-RPC protocol handler |
| `tunnel` | Tunnel manager (ngrok, Cloudflare, bore, Tailscale) |

## Development

```bash
./install.sh              # Set up dev environment
make deploy               # Build + install + restart LO + show log
make test                 # Run tests
```

See [DEVEL.md](DEVEL.md) for the complete developer guide and [docs/modules.md](docs/modules.md) for the module framework reference.

## Documentation

- [`QUICKSTART.md`](QUICKSTART.md) — agent guide: discovery, workflows, tool patterns
- [`AGENTS.md`](AGENTS.md) — developer cheatsheet: project structure, build pipeline, critical rules
- [`docs/howto/`](docs/howto/) — user guides: Tailscale + ChatGPT, Forge, Ollama indexation, image galleries
- [`CHANGELOG.md`](CHANGELOG.md) — version history

## Acknowledgments

Nelson MCP is the result of merging and reworking two other projects:

- **[LocalWriter](https://github.com/KeithCu/localwriter)** — a LibreOffice extension that embedded a chatbot sidebar with AI providers (OpenAI-compatible APIs, Ollama, AI Horde). Originally created as **LibreCalc AI Assistant** by [Umut Çelik](https://extensions.libreoffice.org/en/extensions/show/99509), then forked and expanded by [@balisujohn](https://github.com/balisujohn/localwriter) and significantly developed by [@KeithCu](https://github.com/KeithCu) (Keith Curtis) who added AI Horde support, multi-provider management, the chatbot sidebar, and Calc `=PROMPT()` integration. The module framework, the tool system, and the per-module config architecture were developed by [@quazardous](https://github.com/quazardous).

- **[mcp-libre](https://github.com/patrup/mcp-libre)** — a standalone LibreOffice MCP server that exposed Writer tools to external AI clients via MCP. It demonstrated that the MCP approach (external AI + document tools) was more flexible than an embedded chatbot. Nelson MCP adopts this MCP-first architecture: the chatbot and AI provider modules have been removed, and the extension focuses entirely on being a tool server for external clients.

## License

MPL 2.0 — see `License.txt`.
