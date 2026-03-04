#!/bin/bash
set -e

echo "=== Nelson MCP Docker Build ==="

# Use a temp working dir (writable by any UID)
WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

# Copy source from read-only mount to working dir
echo "Copying source..."
cp -a /src/. "$WORK/"
cd "$WORK"

# Install vendored pip dependencies
echo "Installing vendor dependencies..."
pip install --no-cache-dir --target vendor -r requirements-vendor.txt

# Generate manifests
echo "Generating manifests..."
python3 scripts/generate_manifest.py

# Build .oxt
echo "Building .oxt..."
python3 scripts/build_oxt.py --output /output/nelson.oxt

# Report result
echo ""
echo "=== Build complete ==="
ls -lh /output/nelson.oxt
