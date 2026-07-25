# Set Up an Image Gallery

This guide explains how to configure a folder of images as a searchable gallery in Nelson MCP, so you can browse, search, and insert images into your documents.

## Overview

Nelson MCP's image gallery system indexes local folders and makes their contents available through the `gallery_query` MCP tool. Images are indexed in a local SQLite database with full-text search. Metadata is stored in standard XMP sidecar files.

## Step 1 — Add a Folder

Open **Tools > Options > Nelson MCP > Image Folders**.

Click **Add** to create a new folder instance:

- **Name**: a display name (e.g. "Photos 2024")
- **Path**: absolute path to your image folder (e.g. `C:\Users\me\Pictures\2024` or `/home/me/Pictures/2024`)

### Options

- **Recursive**: scan subfolders (default: yes)
- **Writable**: allow Nelson to save metadata (XMP sidecars) and add images. Required for AI indexing
- **Extensions**: file types to index (default: jpg, jpeg, png, gif, bmp, tiff, webp, svg)
- **AI Auto-Index**: enable automatic AI tagging when the indexer runs (requires Ollama + Forge)
- **Sync to LO Gallery**: copy indexed images to a LibreOffice Gallery theme for use in Insert > Media > Gallery

## Step 2 — Initial Scan

Click **Rescan** to trigger an immediate scan, or restart LibreOffice (folders are scanned at startup if **Rescan on Startup** is enabled).

The scan:

1. Walks the folder tree
2. Reads image dimensions and file metadata
3. Reads XMP sidecar files (if they exist) for title, description, keywords, rating
4. Stores everything in a SQLite database with FTS5 full-text search

Only changed files are re-indexed on subsequent scans (incremental, based on file modification time).

## Step 3 — Browse and Search

### From an MCP Client

Use these tools:

- `gallery_query(action="list")` — browse images by folder, with pagination
- `gallery_query(action="search")` — full-text search across filenames, titles, descriptions, and keywords
- `gallery_query(action="get")` — get full metadata for a specific image

### Example

> "Search my gallery for sunset photos"

Returns matching images with paths, descriptions, and keywords.

### Insert into Document

Use `image_insert` with the image path returned by gallery tools to insert directly into your Writer document.

## Step 4 — Add Metadata (optional)

### XMP Sidecars

If your images already have XMP sidecar files (`.xmp`), Nelson reads them automatically. Supported fields:

- **Title** (dc:title)
- **Description** (dc:description)
- **Keywords** (dc:subject)
- **Creator** (dc:creator)
- **Rating** (xmp:Rating, 0-5)

XMP files follow the standard `filename.jpg.xmp` naming convention.

### AI Indexing

For automatic tagging, see [Index Your Photos with Ollama](setup-ollama-indexation.md).

## Multiple Galleries

You can add as many folder galleries as needed. Each gets its own index database. Use `gallery_providers` to list all configured galleries, and specify a provider in search/list calls to target a specific one.

## Database Management

- **Reset DB**: deletes the index and rebuilds from scratch. Use this if the index seems corrupted or after changing folder structure
- Database location: `~/.config/nelson/images_<hash>.db`
- The database is lightweight — it stores metadata only, not image data

## Troubleshooting

- **No images found**: check the folder path and extensions. Make sure the folder contains supported image files
- **Stale results**: click Rescan or restart LibreOffice to re-index
- **Permission errors**: on Windows, avoid folders with restricted access. The folder must be readable by LibreOffice
- **Large folders (10,000+ images)**: initial scan may take a minute. Subsequent scans are incremental and fast
