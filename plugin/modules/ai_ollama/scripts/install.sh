#!/bin/bash
# Install Ollama and pull a starter model
# https://ollama.com

MODEL="${1:-llama3.2:latest}"

echo ""
echo "=== Ollama Install / Detect ==="
echo ""

# --- Check if Ollama is already installed ---
if command -v ollama &>/dev/null; then
    echo "[OK] Ollama found: $(which ollama)"
    ollama --version 2>/dev/null
else
    echo "[!] Ollama not found. Installing..."
    echo ""
    curl -fsSL https://ollama.com/install.sh | sh
    if ! command -v ollama &>/dev/null; then
        echo "[ERROR] Installation failed. Install manually: https://ollama.com/download"
        exit 1
    fi
    echo "[OK] Ollama installed"
fi

# --- Check if running ---
echo ""
if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "[OK] Ollama server is running"
else
    echo "[!] Starting Ollama server..."
    ollama serve &
    sleep 3
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[OK] Ollama server started"
    else
        echo "[!] Could not start server"
    fi
fi

# --- List installed models ---
echo ""
echo "Installed models:"
ollama list 2>/dev/null || echo "  (could not connect)"

# --- Pull starter model ---
if [ -n "$MODEL" ] && [ "$MODEL" != "none" ]; then
    echo ""
    if ollama list 2>/dev/null | grep -q "^$MODEL"; then
        echo "[OK] Model '$MODEL' is already installed"
    else
        echo "Pulling model '$MODEL'..."
        ollama pull "$MODEL"
    fi
fi

echo ""
echo "=== Done ==="
