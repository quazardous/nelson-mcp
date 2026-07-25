# Index Your Photos with Ollama

This guide explains how to use Ollama (a local LLM) to automatically tag and describe your photo collection, making images searchable from LibreOffice.

## Overview

Nelson MCP indexes images in 3 passes:

1. **Pass 1 — CLIP** (requires Forge): generates a literal description of each image
2. **Pass 2 — Folder Universe** (requires Ollama): analyzes folder context to understand the theme (e.g. "safari trip", "family reunion")
3. **Pass 3 — Per-Image Tags** (requires Ollama): combines CLIP description + folder context to generate rich, thematic keywords

After indexation, you can search images by theme, activity, location, or content using the `gallery_query` tool (`action="search"`).

## Prerequisites

- Nelson MCP installed in LibreOffice
- At least one image folder configured (see [Image Gallery Setup](setup-image-gallery.md))
- Forge running for Pass 1 (see [Forge Setup](setup-forge-images.md))
- ~4 GB RAM for Ollama with a 3B model

## Step 1 — Install Ollama

Open **Tools > Options > Nelson MCP > AI Ollama**.

Click **Detect / Install Ollama**.

- **Windows**: installs via `winget install Ollama.Ollama`
- **Linux**: installs via the official install script

The installer also pulls the default model (`llama3.2:latest`, 3B parameters — good balance of speed and quality).

## Step 2 — Start Ollama

From the menu: **Tools > Nelson MCP > AI > Start Ollama**

Or start it manually in a terminal:

```
ollama serve
```

Ollama runs on port 11434 by default.

## Step 3 — Configure

In **Options > Nelson MCP > AI Ollama**, verify:

- An instance exists (e.g. "Local") pointing to `http://127.0.0.1:11434`
- **Model**: `llama3.2:latest` (recommended for indexation — fast and capable)
- **Temperature**: 0.3 (low = consistent, deterministic tags)

### Recommended Models

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| llama3.2:latest | 3B | Fast | Good for tagging |
| gemma3:4b | 4B | Fast | Good alternative |
| llama3.1:8b | 8B | Medium | Better understanding |
| qwen3:8b | 8B | Medium | Good multilingual |

## Step 4 — Enable AI Indexing on Your Folder

In **Options > Nelson MCP > Image Folders**, select your folder instance and enable:

- **AI Auto-Index**: checked
- **Writable**: checked (required for saving metadata)

## Step 5 — Run Indexation

### Pass 1 — CLIP Descriptions

Make sure Forge is running, then from the menu:

**Tools > Nelson MCP > AI Images > Start Indexer**

This scans all images without a description and sends them to Forge's CLIP model. Each image gets a literal caption like "a brown horse standing in a green field, mountains in background".

### Passes 2 & 3 — LLM Tagging

Once Pass 1 is done (or you can run them together), Ollama processes the images:

- **Pass 2** reads text files (`.txt`, `.md`) in each folder to understand the context (e.g. a `README.md` saying "Photos from Kenya safari, March 2024")
- **Pass 3** combines the CLIP caption + folder context to generate rich tags like: `safari, wildlife, rhinoceros, Kenya, savanna, March 2024`

Progress is shown in the LibreOffice status bar.

## Step 6 — Search Your Images

Once indexed, use the `gallery_query` MCP tool with `action="search"`:

> "Find photos of elephants near water"

Or use `gallery_query(action="list")` to browse by folder with keyword metadata.

## Index Language

By default, tags are generated in the same language as the folder context files. You can force a language in **Options > Nelson MCP > AI Images > Index Language** (e.g. "french", "english").

## Troubleshooting

- **Pass 1 stuck**: Check that Forge is running (`http://127.0.0.1:7860` reachable)
- **Pass 2/3 stuck**: Check that Ollama is running (`http://127.0.0.1:11434` reachable)
- **Poor tag quality**: Try a larger model (8B) or add context files in your image folders
- **Re-index**: Use the **Reset DB** button in Image Folders options to start fresh
- **Stop Ollama**: Menu **Tools > Nelson MCP > AI > Stop Ollama** (frees RAM)
