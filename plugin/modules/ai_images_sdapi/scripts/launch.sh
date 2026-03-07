#!/bin/bash
# Launch Stable Diffusion WebUI Forge with --api flag (uses uv for deps)

WEBUI_DIR="$1"

if [ -z "$WEBUI_DIR" ] || [ ! -d "$WEBUI_DIR" ]; then
    echo "ERROR: WebUI directory not found: $WEBUI_DIR"
    read -p "Press Enter to close..."
    exit 1
fi

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install it from https://docs.astral.sh/uv/"
    read -p "Press Enter to close..."
    exit 1
fi

echo "=== Launching Stable Diffusion WebUI Forge ==="
echo "Directory: $WEBUI_DIR"
echo ""

cd "$WEBUI_DIR"

VENV_DIR="$WEBUI_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# Create venv with uv if it doesn't exist
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Creating venv with Python 3.10 via uv..."
    uv venv --python 3.10 --seed "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create venv."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "venv created."
fi

echo "Using Python: $VENV_PYTHON"

# Install dependencies via uv pip
REQ_FILE="$WEBUI_DIR/requirements_versions.txt"
if [ -f "$REQ_FILE" ]; then
    echo "Installing dependencies via uv pip..."
    uv pip install -p "$VENV_PYTHON" torch==2.3.1 torchvision==0.18.1 --extra-index-url https://download.pytorch.org/whl/cu121
    uv pip install -p "$VENV_PYTHON" -r "$REQ_FILE"
    uv pip install -p "$VENV_PYTHON" --no-build-isolation "https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip"
    # Force numpy to pinned version (scikit-image needs matching binary)
    uv pip install -p "$VENV_PYTHON" numpy==1.26.2
    echo ""
fi

# Launch
LAUNCH_PY="$WEBUI_DIR/launch.py"
if [ ! -f "$LAUNCH_PY" ]; then
    echo "ERROR: launch.py not found in $WEBUI_DIR"
    read -p "Press Enter to close..."
    exit 1
fi

echo "Starting: launch.py --api"
echo ""

"$VENV_PYTHON" "$LAUNCH_PY" --api

echo ""
echo "WebUI exited."
read -p "Press Enter to close..."
