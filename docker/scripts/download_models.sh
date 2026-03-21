#!/bin/bash
set -e

echo "Downloading Wan2.2 models for ComfyUI..."

# Wan2.2 VAE (required for video decoding)
echo "Downloading Wan2.2 VAE..."
wget -q -P /workspace/ComfyUI/models/vae/ \
    "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_vae.safetensors" \
    || echo "VAE download failed, trying alternative..."

# Wan2.2 5B Model (text-to-video, recommended for start)
echo "Downloading Wan2.2 5B model..."
wget -q -P /workspace/ComfyUI/models/checkpoints/ \
    "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/wan2.2-Fun-S2-5B-Q4_K_M.gguf" \
    || echo "Model download may take time..."

echo "Model download complete. Restart ComfyUI to use them."
