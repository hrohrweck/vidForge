#!/bin/bash
set -e

MODELS_DIR="/workspace/ComfyUI/models"
VAE_DIR="$MODELS_DIR/vae"
CHECKPOINT_DIR="$MODELS_DIR/checkpoints"
CLIP_DIR="$MODELS_DIR/clip"
DIFFUSION_DIR="$MODELS_DIR/diffusion_models"

mkdir -p "$VAE_DIR" "$CHECKPOINT_DIR" "$CLIP_DIR" "$DIFFUSION_DIR"

echo "[VidForge] Checking for Wan2.2 5B models..."

# Download Wan2.2 VAE (for 5B model)
if [ ! -f "$VAE_DIR/wan2.2_vae.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 VAE (~254MB)..."
    curl -# -L -o "$VAE_DIR/wan2.2_vae.safetensors" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors"
    echo "[VidForge] VAE downloaded successfully"
else
    echo "[VidForge] VAE already present"
fi

# Download 5B diffusion model
if [ ! -f "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 5B diffusion model (~10GB)..."
    /opt/venv/bin/huggingface-cli download Comfy-Org/Wan_2.2_ComfyUI_Repackaged \
        split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors \
        --local-dir "$MODELS_DIR" \
        --local-dir-use-symlinks False \
        || curl -# -L -o "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" \
            "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"
    echo "[VidForge] Diffusion model downloaded successfully"
else
    echo "[VidForge] Diffusion model already present"
fi

# Download Wan2.2 VAE (for 5B model)
if [ ! -f "$VAE_DIR/wan2.2_vae.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 VAE (~254MB)..."
    curl -# -L -o "$VAE_DIR/wan2.2_vae.safetensors" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors"
    echo "[VidForge] VAE downloaded successfully"
else
    echo "[VidForge] VAE already present"
fi

# Download 5B diffusion model
if [ ! -f "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 5B diffusion model (~10GB)..."
    echo "[VidForge] This may ~10GB, please wait..."
    curl -# -L -o "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"
    echo "[VidForge] Diffusion model downloaded successfully"
else
    echo "[VidForge] Diffusion model already present"
fi

#!/bin/bash
set -e

MODELS_DIR="/workspace/ComfyUI/models"
VAE_DIR="$MODELS_DIR/vae"
CHECKPOINT_DIR="$MODELS_DIR/checkpoints"
CLIP_DIR="$MODELS_DIR/clip"
DIFFUSION_DIR="$MODELS_DIR/diffusion_models"

mkdir -p "$VAE_DIR" "$CHECKPOINT_DIR" "$CLIP_DIR" "$DIFFUSION_DIR"

echo "[VidForge] Checking for Wan2.2 5B models..."

# Download VAE (for 5B model)
if [ ! -f "$VAE_DIR/wan2.2_vae.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 VAE (~254MB)..."
    curl -# -L -o "$VAE_DIR/wan2.2_vae.safetensors" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors"
    echo "[VidForge] VAE downloaded successfully"
else
    echo "[VidForge] VAE already present"
fi

# Download 5B diffusion model to diffusion_models (not checkpoints)
if [ ! -f "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 5B diffusion model (~10GB)..."
    echo "[VidForge] This will take a while..."
    /opt/venv/bin/huggingface-cli download Comfy-Org/Wan_2.2_ComfyUI_Repackaged \
        split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors \
        --local-dir "$MODELS_DIR" \
        --local-dir-use-symlinks False \
    echo "[VidForge] Diffusion model downloaded successfully"
else
    echo "[VidForge] Diffusion model already present"
fi

# Download CLIP model to clip directory (flat, not nested)
if [ ! -f "$CLIP_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 CLIP model (~6.7GB)..."
    curl -# -L -o "$CLIP_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    echo "[VidForge] CLIP downloaded successfully"
else
    echo "[VidForge] CLIP already present"
fi

# Download additional CLIP if needed
if [ ! -f "$CLIP_DIR/clip_l.safetensors" ]; then
    echo "[VidForge] Downloading CLIP-L model..."
    curl -# -L -o "$CLIP_DIR/clip_l.safetensors" \
        "https://huggingface.co/openai/clip-vit-large-patch14/resolve/main/model.safetensors"
    echo "[VidForge] CLIP-L downloaded"
else
    echo "[VidForge] CLIP-L already present"
fi

echo "[VidForge] Model setup complete. Starting ComfyUI..."
echo "[VidForge] Note: First video generation may take longer as models are loaded."

# Start ComfyUI
exec /opt/venv/bin/python main.py --listen 0.0.0.0 --port 8188 "$@"
