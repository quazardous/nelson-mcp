# Connect ChatGPT to LibreOffice via Tailscale

This guide explains how to expose your Nelson MCP server to the internet using Tailscale Funnel, so that ChatGPT (or any remote MCP client) can control your LibreOffice documents.

> [!WARNING]
> **Read this before you start.** Tailscale **Funnel** publishes your machine on
> the *public internet*, not just on your private tailnet. Whoever can reach the
> URL gets what your MCP client gets:
>
> - read and write access to **every document open** in LibreOffice;
> - `doc_open` on **any file your user account can read**;
> - saving, exporting and closing documents.
>
> Nelson therefore **refuses to start a tunnel until an access token is set**
> (step 2), and every request must carry it. Treat that token like a password.
>
> Also keep **Enable Config API** (HTTP page) and the **debug API** turned
> **off** on an exposed machine: the first lets a caller rewrite Nelson's
> settings, the second runs arbitrary code.
>
> If the only client is on your own devices, prefer `tailscale serve`, which
> stays inside your tailnet, over Funnel.

## Prerequisites

- Nelson MCP installed in LibreOffice
- A Tailscale account (free tier works)

## Step 1 — Install Tailscale

Download and install Tailscale from https://tailscale.com/download

Then log in:

```
tailscale login
```

Enable Funnel (allows public HTTPS access to your machine):

```
tailscale funnel on
```

## Step 2 — Configure Nelson MCP

Open **Tools > Options > Nelson MCP**.

### HTTP Server

Go to the **HTTP** page and verify:

- **Enabled**: checked
- **Port**: 8766 (default)
- **Host**: localhost
- **Access Token**: set a long random value — for example the output of
  `openssl rand -hex 32`. The tunnel will not start without one.
- **Enable Config API**: unchecked

Keep the host on `localhost`: the tunnel connects locally, and binding to
`0.0.0.0` would expose the port on your network as well.

You do not need to enable SSL — Tailscale Funnel handles HTTPS termination automatically.

### Tunnel

Go to the **Tunnel** page:

- **Provider**: select **Tailscale**
- **Auto Start**: check this if you want the tunnel to start every time LibreOffice opens

### MCP

Go to the **MCP** page:

- **Enabled**: checked
- Choose a **Preset** appropriate for your use case (e.g. `writer-edit` for full Writer editing)

## Step 3 — Start the tunnel

From the menu: **Tools > Nelson MCP > Tunnel > Start Tunnel**

The status bar will show the tunnel URL once connected. You can also check it via **Tools > Nelson MCP > Tunnel > Tunnel Status**.

The URL looks like: `https://your-machine.tail1234.ts.net`

## Step 4 — Connect ChatGPT

Every request must carry the access token. If your client lets you set a
header, send it as:

```
Authorization: Bearer <your token>
```

If it only accepts a URL — as some hosted connectors do — append it as a query
parameter instead:

- **MCP endpoint**: `https://your-machine.tail1234.ts.net/mcp?token=<your token>`
- **SSE endpoint**: `https://your-machine.tail1234.ts.net/sse?token=<your token>` (for streaming)

The header is the better option when you have it: a token in a URL ends up
wherever that URL is logged. Either way, if the token leaks, change it in
Options — it applies immediately, no restart needed.

The MCP endpoint accepts JSON-RPC requests. The SSE endpoint provides Server-Sent Events for real-time streaming.

## Step 5 — Test

Ask ChatGPT to list open documents:

> "List the documents currently open in LibreOffice"

If it returns document names, the connection is working.

## Custom Endpoints

Exposing only a subset of tools is recommended for ChatGPT, which has a limited tool window — and it also narrows what a leaked token could do. A read-only list is the strongest version of that. Create a custom endpoint in **Options > Nelson MCP > MCP**:

1. Click **Add** in Custom Endpoints
2. Give it a name (e.g. "chatgpt")
3. Set the path (e.g. "/chatgpt")
4. List only the tools you need in the textarea

The endpoint will be available at `https://your-machine.tail1234.ts.net/chatgpt/mcp`.

## Troubleshooting

- **Tunnel won't start**: Check that an **Access Token** is set (Nelson refuses to open a tunnel without one), that `tailscale funnel on` was run, and that Tailscale is connected
- **401 Unauthorized**: The request did not carry the token, or carried a different one — check the header or the `?token=` parameter
- **ChatGPT can't reach the URL**: Funnel can take a few seconds to propagate. Check `tailscale funnel status`
- **Tools not showing**: Verify MCP is enabled and the preset includes the tools you need
