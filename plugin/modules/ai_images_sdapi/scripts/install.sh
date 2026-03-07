#!/bin/bash
# Install Stable Diffusion WebUI Forge - fully automated
# https://github.com/lllyasviel/stable-diffusion-webui-forge

STARTER_MODEL="${1:-dreamshaper8}"
INSTALL_DIR="$HOME/stable-diffusion-webui"

# --- Model catalog ---
case "$STARTER_MODEL" in
    juggernaut_xl)
        MODEL_FILE="juggernautXL_v9Lightning.safetensors"
        MODEL_URL="https://civitai.com/api/download/models/357609"
        MODEL_SIZE="6.5 GB"
        REQUIRED_GB=16
        ;;
    dreamshaper8)
        MODEL_FILE="dreamshaper_8.safetensors"
        MODEL_URL="https://civitai.com/api/download/models/128713?type=Model&format=SafeTensor&size=pruned&fp=fp16"
        MODEL_SIZE="2.1 GB"
        REQUIRED_GB=12
        ;;
    dreamshaperxl)
        MODEL_FILE="dreamshaperXL_v21.safetensors"
        MODEL_URL="https://civitai.com/api/download/models/351306?type=Model&format=SafeTensor&size=pruned&fp=fp16"
        MODEL_SIZE="6.5 GB"
        REQUIRED_GB=16
        ;;
    none)
        MODEL_FILE=""
        MODEL_URL=""
        MODEL_SIZE="0"
        REQUIRED_GB=10
        ;;
    *)
        echo "Unknown model: $STARTER_MODEL - falling back to juggernaut_xl"
        STARTER_MODEL="juggernaut_xl"
        MODEL_FILE="juggernautXL_v9Lightning.safetensors"
        MODEL_URL="https://civitai.com/api/download/models/357609"
        MODEL_SIZE="6.5 GB"
        REQUIRED_GB=16
        ;;
esac

echo "=== Stable Diffusion WebUI Forge Installer ==="
echo "Model: $STARTER_MODEL ($MODEL_SIZE)"
echo ""

# --- Disk space check ---
FREE_KB=$(df -k "$HOME" | tail -1 | awk '{print $4}')
FREE_GB=$((FREE_KB / 1048576))
echo "Disk space: ${FREE_GB} GB free"
if [ "$FREE_GB" -lt "$REQUIRED_GB" ]; then
    echo "ERROR: At least ${REQUIRED_GB} GB required for this setup."
    echo "Free up some space or choose a smaller model."
    read -p "Press Enter to close..."
    exit 1
fi
echo "OK: ${FREE_GB} GB available (need ${REQUIRED_GB} GB)."
echo ""

# --- Check Git ---
if ! command -v git &>/dev/null; then
    echo "ERROR: Git not found. Install git first."
    read -p "Press Enter to close..."
    exit 1
fi

# --- Install uv if not present ---
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "ERROR: uv installation failed."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "uv installed."
fi

# --- Clone or update Forge ---
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory already exists: $INSTALL_DIR"
    echo "Updating..."
    cd "$INSTALL_DIR" && git pull
else
    echo "Cloning Forge into $INSTALL_DIR ..."
    git clone https://github.com/lllyasviel/stable-diffusion-webui-forge.git "$INSTALL_DIR"
    if [ $? -ne 0 ]; then
        echo "ERROR: git clone failed."
        read -p "Press Enter to close..."
        exit 1
    fi
fi

# --- Create venv ---
VENV_DIR="$INSTALL_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo ""
    echo "Creating venv with Python 3.10 via uv..."
    uv venv --python 3.10 --seed "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create venv."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "venv created."
else
    echo "venv already exists."
fi

# --- Install dependencies ---
REQ_FILE="$INSTALL_DIR/requirements_versions.txt"
if [ -f "$REQ_FILE" ]; then
    echo ""
    echo "Installing dependencies (this may take a while)..."
    uv pip install -p "$VENV_PYTHON" torch==2.3.1 torchvision==0.18.1 --extra-index-url https://download.pytorch.org/whl/cu121
    uv pip install -p "$VENV_PYTHON" -r "$REQ_FILE"
    uv pip install -p "$VENV_PYTHON" --no-build-isolation "https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip"
    uv pip install -p "$VENV_PYTHON" numpy==1.26.2
    echo "Dependencies installed."
fi

# --- Download model ---
if [ "$STARTER_MODEL" != "none" ]; then
    MODELS_DIR="$INSTALL_DIR/models/Stable-diffusion"
    MODEL_PATH="$MODELS_DIR/$MODEL_FILE"
    mkdir -p "$MODELS_DIR"

    if [ -f "$MODEL_PATH" ]; then
        SIZE_MB=$(du -m "$MODEL_PATH" | cut -f1)
        echo ""
        echo "Model already exists: $MODEL_FILE (${SIZE_MB} MB)"
    else
        echo ""
        echo "Downloading model: $STARTER_MODEL ($MODEL_SIZE)..."
        if command -v curl &>/dev/null; then
            curl -L -o "$MODEL_PATH" "$MODEL_URL"
        elif command -v wget &>/dev/null; then
            wget -O "$MODEL_PATH" "$MODEL_URL"
        else
            echo "WARNING: Neither curl nor wget found. Download a model manually into:"
            echo "  $MODELS_DIR"
        fi

        if [ -f "$MODEL_PATH" ]; then
            SIZE_MB=$(du -m "$MODEL_PATH" | cut -f1)
            echo "Model downloaded: $MODEL_FILE (${SIZE_MB} MB)"
        else
            echo "WARNING: Model download may have failed."
            echo "Download a model manually and place it in:"
            echo "  $MODELS_DIR"
        fi
    fi
fi

# --- Activate model if API is running ---
if [ "$STARTER_MODEL" != "none" ] && [ -n "$MODEL_FILE" ]; then
    API_URL="http://127.0.0.1:7860"
    if curl -s --max-time 3 "$API_URL/sdapi/v1/sd-models" >/dev/null 2>&1; then
        echo ""
        echo "API is running - activating model..."
        curl -s -X POST "$API_URL/sdapi/v1/refresh-checkpoints" >/dev/null 2>&1
        curl -s -X POST "$API_URL/sdapi/v1/options" \
            -H "Content-Type: application/json" \
            -d "{\"sd_model_checkpoint\":\"$MODEL_FILE\"}" \
            --max-time 120 >/dev/null 2>&1
        echo "Model activated: $MODEL_FILE"
    else
        echo "API not running - model will be activated on next launch."
    fi
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Use the 'Launch Forge' button in Nelson Options to start the WebUI."
echo ""
read -p "Press Enter to close..."
