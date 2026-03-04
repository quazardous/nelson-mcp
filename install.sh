#!/usr/bin/env bash
# install.sh — Set up the Nelson MCP development environment (Linux/macOS).
#
# Usage:
#   ./install.sh          Install dev dependencies
#   ./install.sh --check  Verify environment only

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
fi

echo "Nelson MCP Development Setup"
echo "=============================="
echo ""

# ── Python ────────────────────────────────────────────────────────────

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | head -1)
        PYTHON="$cmd"
        info "Found $ver at $(which $cmd)"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    error "Python 3.8+ not found. Install Python first."
    exit 1
fi

# ── pip ───────────────────────────────────────────────────────────────

if $PYTHON -m pip --version &>/dev/null; then
    info "pip available"
else
    error "pip not found. Install pip: $PYTHON -m ensurepip"
    exit 1
fi

# ── PyYAML (required for build) ──────────────────────────────────────

if $PYTHON -c "import yaml" 2>/dev/null; then
    info "PyYAML installed"
else
    if $CHECK_ONLY; then
        warn "PyYAML not installed (needed for build)"
    else
        echo "Installing PyYAML..."
        $PYTHON -m pip install --user pyyaml
        info "PyYAML installed"
    fi
fi

# ── LibreOffice ──────────────────────────────────────────────────────

LO=""
for cmd in soffice libreoffice; do
    if command -v "$cmd" &>/dev/null; then
        LO="$cmd"
        ver=$("$cmd" --version 2>&1 | head -1 || echo "unknown")
        info "LibreOffice: $ver"
        break
    fi
done

if [[ -z "$LO" ]]; then
    warn "LibreOffice not found on PATH (needed for running the extension)"
fi

# ── unopkg ───────────────────────────────────────────────────────────

if command -v unopkg &>/dev/null; then
    info "unopkg available"
else
    warn "unopkg not found (needed for extension installation)"
fi

# ── openssl (for MCP TLS) ───────────────────────────────────────────

if command -v openssl &>/dev/null; then
    info "openssl available (for MCP TLS certificates)"
else
    warn "openssl not found (optional, needed for MCP HTTPS)"
fi

# ── make ─────────────────────────────────────────────────────────────

if command -v make &>/dev/null; then
    info "make available"
else
    warn "make not found (optional, but recommended)"
fi

echo ""

# ── Vendored dependencies ──────────────────────────────────────────

if [[ -f requirements-vendor.txt ]]; then
    if $CHECK_ONLY; then
        if [[ -d vendor ]]; then
            info "vendor/ directory exists"
        else
            warn "vendor/ not populated (run: make vendor)"
        fi
    else
        echo "Installing vendored dependencies..."
        if command -v uv &>/dev/null; then
            uv pip install --target vendor -r requirements-vendor.txt
        else
            $PYTHON -m pip install --target vendor -r requirements-vendor.txt
        fi
        info "Vendored dependencies installed"
    fi
fi

echo ""

if $CHECK_ONLY; then
    echo "Environment check complete."
else
    echo "Setup complete. Available commands:"
    echo "  make build          Build the .oxt extension"
    echo "  make install        Build + install in LibreOffice"
    echo "  make dev-deploy     Symlink for fast dev iteration"
    echo "  make lo-start       Launch LibreOffice with debug logging"
fi
