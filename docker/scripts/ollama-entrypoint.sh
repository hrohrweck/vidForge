#!/bin/bash
set -e

echo "[VidForge] Checking for Ollama models..."

OLLAMA_MODELS_DIR="/root/.ollama/models"
DEFAULT_MODEL="llama3.2"

# Function to pull a model
pull_if_missing() {
    local model=$1
    if ! ollama list | grep -q "^$model"; then
        echo "[VidForge] Pulling $model..."
        ollama pull "$model"
    else
        echo "[VidForge] Model $model already present"
    fi
}

# Pull default model if not present
if [ -n "$DEFAULT_MODEL" ]; then
    pull_if_missing "$DEFAULT_MODEL"
fi

# Also check for embedding models
pull_if_missing "nomic-embed-text"

echo "[VidForge] Ollama setup complete."

# Start Ollama serve
exec ollama serve
