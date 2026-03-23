#!/bin/bash
set -e

MODELS_DIR="/workspace/ComfyUI/models"
VAE_DIR="$MODELS_DIR/vae"
CHECKPOINT_DIR="$MODELS_DIR/checkpoints"

echo "[VidForge] Checking for Wan2.2 models..."

# Check if VAE exists
if [ ! -f "$VAE_DIR/wan_2.1_vae.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.1 VAE..."
    curl -# -L -o "$VAE_DIR/wan_2.1_vae.safetensors" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"
    echo "[VidForge] VAE downloaded successfully"
else
    echo "[VidForge] VAE already present"
fi

# Check if any Wan model exists
WAN_MODEL=$(ls "$CHECKPOINT_DIR"/*wan* "$CHECKPOINT_DIR"/*Wan* 2>/dev/null | head -1 || true)
if [ -z "$WAN_MODEL" ]; then
    echo "[VidForge] Downloading Wan2.2 5B model (GGUF format)..."
    echo "[VidForge] This is ~5GB, please wait..."
    wget -q --show-progress -P "$CHECKPOINT_DIR/" \
        "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/wan2.2-Fun-S2-5B-Q4_K_M.gguf" \
        || curl -# -o "$CHECKPOINT_DIR/wan2.2-Fun-S2-5B-Q4_K_M.gguf" \
            "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/wan2.2-Fun-S2-5B-Q4_K_M.gguf"
    echo "[VidForge] Model downloaded successfully"
else
    echo "[VidForge] Wan model already present: $WAN_MODEL"
fi

# Also download CLIP if missing
CLIP_MODEL="$MODELS_DIR/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
if [ ! -f "$CLIP_MODEL" ]; then
    echo "[VidForge] Downloading Wan2.2 CLIP model..."
    mkdir -p "$MODELS_DIR/clip"
    curl -# -L -o "$CLIP_MODEL" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    echo "[VidForge] CLIP downloaded"
else
    echo "[VidForge] CLIP already present"
fi

echo "[VidForge] Model setup complete. Starting ComfyUI..."
echo "[VidForge] Note: First video generation may take longer as models are loaded."

# Start ComfyUI
exec python main.py --listen 0.0.0.0 --port 8188 "$@"
