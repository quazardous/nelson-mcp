#!/bin/bash
set -e

echo "=== Nelson MCP Docker Build ==="

# Persistent working directory (Docker volume, survives between builds)
WORK="${BUILD_WORK:-/tmp/build-work}"
mkdir -p "$WORK"

# Incremental sync from read-only source (only changed files)
echo "Copying source..."
rsync -a --delete \
    --exclude='build/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    /src/ "$WORK/"
cd "$WORK"

# Install vendored pip dependencies (skip if unchanged)
VENDOR_HASH=$(md5sum requirements-vendor.txt 2>/dev/null | cut -d' ' -f1)
VENDOR_MARKER="vendor/.hash_$VENDOR_HASH"
if [ ! -f "$VENDOR_MARKER" ]; then
    echo "Installing vendor dependencies..."
    pip install --target vendor -r requirements-vendor.txt
    rm -f vendor/.hash_*
    touch "$VENDOR_MARKER"
else
    echo "Vendor dependencies cached."
fi

# Generate manifests (skip if inputs unchanged)
MANIFEST_HASH=$(find plugin/modules -name 'module.yaml' -exec md5sum {} \; \
    plugin/plugin.yaml plugin/version.py 2>/dev/null | md5sum | cut -d' ' -f1)
MANIFEST_MARKER="build/.manifest_$MANIFEST_HASH"
if [ ! -f "$MANIFEST_MARKER" ]; then
    echo "Generating manifests..."
    python3 scripts/generate_manifest.py
    rm -f build/.manifest_*
    touch "$MANIFEST_MARKER"
else
    echo "Manifests cached."
fi

# Generate icons (skip if SVG unchanged and PNGs exist)
ICON_SRC="extension/assets/icon.svg"
ICON_DIR="build/generated/assets"
if [ "$ICON_SRC" -nt "$ICON_DIR/icon_16.png" ] 2>/dev/null || [ ! -f "$ICON_DIR/icon_16.png" ]; then
    echo "Generating icons..."
    mkdir -p "$ICON_DIR"
    magick -background none -density 256 "$ICON_SRC" -resize 16x16 "$ICON_DIR/icon_16.png"
    magick -background none -density 256 "$ICON_SRC" -resize 24x24 "$ICON_DIR/icon_24.png"
    magick -background none -density 256 "$ICON_SRC" -resize 42x42 "$ICON_DIR/logo.png"
else
    echo "Icons cached."
fi

# Build .oxt
echo "Building .oxt..."
python3 scripts/build_oxt.py --output /output/nelson.oxt

# Report result
echo ""
echo "=== Build complete ==="
ls -lh /output/nelson.oxt
