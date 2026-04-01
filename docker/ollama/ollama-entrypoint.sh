#!/bin/bash
set -e

echo "[VidForge] Starting Ollama server..."

# Start ollama serve in background
ollama serve &
SERVER_PID=$!

# Wait for server to be ready
echo "[VidForge] Waiting for Ollama server to be ready..."
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "[VidForge] Ollama server is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "[VidForge] Timeout waiting for Ollama server"
        exit 1
    fi
    sleep 1
done

DEFAULT_MODEL="llama3.2"

# Function to pull a model
pull_if_missing() {
    local model=$1
    if ! ollama list | grep -q "$model"; then
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

# Wait for the server process (keep container running)
wait $SERVER_PID
