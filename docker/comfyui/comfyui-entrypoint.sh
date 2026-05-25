#!/bin/bash
set -e

MODELS_DIR="/workspace/ComfyUI/models"
VAE_DIR="$MODELS_DIR/vae"
CHECKPOINT_DIR="$MODELS_DIR/checkpoints"
CLIP_DIR="$MODELS_DIR/clip"
DIFFUSION_DIR="$MODELS_DIR/diffusion_models"
TEXT_ENCODERS_DIR="$MODELS_DIR/text_encoders"
UNET_DIR="$MODELS_DIR/unet"

mkdir -p "$VAE_DIR" "$CHECKPOINT_DIR" "$CLIP_DIR" "$DIFFUSION_DIR" "$TEXT_ENCODERS_DIR" "$UNET_DIR"

# Helper function to download with curl
download_file() {
    local url="$1"
    local output="$2"
    local desc="$3"
    local min_size="${4:-1000000}"
    
    if [ -f "$output" ] && [ $(stat -c%s "$output" 2>/dev/null) -gt $min_size ]; then
        echo "[VidForge] $desc already present"
        return 0
    fi
    
    rm -f "$output"
    echo "[VidForge] Downloading $desc..."
    curl -# -L -o "$output" "$url" || {
        echo "[VidForge] WARNING: Failed to download $desc"
        rm -f "$output"
        return 1
    }
    
    if [ -f "$output" ] && [ $(stat -c%s "$output" 2>/dev/null) -gt $min_size ]; then
        echo "[VidForge] $desc downloaded successfully"
        return 0
    else
        echo "[VidForge] WARNING: Downloaded file too small, removing..."
        rm -f "$output"
        return 1
    fi
}

echo "[VidForge] ==========================================="
echo "[VidForge] VidForge ComfyUI Model Setup"
echo "[VidForge] ==========================================="

# ============================================
# FLUX.1-schnell (Default Image Generation)
# ============================================
echo "[VidForge] Checking for FLUX.1-schnell models..."

# FLUX FP8 model (~17GB) - smaller, faster, from Comfy-Org
if [ ! -f "$UNET_DIR/flux1-schnell-fp8.safetensors" ]; then
    echo "[VidForge] Downloading FLUX.1-schnell FP8 model (~17GB)..."
    echo "[VidForge] This is the default image generation model..."
    download_file \
        "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors" \
        "$UNET_DIR/flux1-schnell-fp8.safetensors" \
        "FLUX.1-schnell FP8 model"
fi

# FLUX VAE - download from camenduru (ungated, works with FLUX FP8)
if [ ! -f "$VAE_DIR/ae.safetensors" ] || [ $(stat -c%s "$VAE_DIR/ae.safetensors" 2>/dev/null) -lt 1000000 ]; then
    echo "[VidForge] Downloading FLUX VAE (~335MB)..."
    download_file \
        "https://huggingface.co/camenduru/FLUX.1-dev-ungated/resolve/main/ae.safetensors" \
        "$VAE_DIR/ae.safetensors" \
        "FLUX VAE" || echo "[VidForge] VAE download failed - will use default VAE"
fi

# FLUX CLIP models
if [ ! -f "$CLIP_DIR/clip_l.safetensors" ]; then
    download_file \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" \
        "$CLIP_DIR/clip_l.safetensors" \
        "CLIP-L text encoder"
fi

if [ ! -f "$TEXT_ENCODERS_DIR/t5xxl_fp8_e4m3fn.safetensors" ]; then
    download_file \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" \
        "$TEXT_ENCODERS_DIR/t5xxl_fp8_e4m3fn.safetensors" \
        "T5-XXL text encoder"
fi

# ============================================
# Wan2.2 5B (Video Generation)
# ============================================
echo "[VidForge] Checking for Wan2.2 5B models..."

download_file \
    "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors" \
    "$VAE_DIR/wan2.2_vae.safetensors" \
    "Wan2.2 VAE"

if [ ! -f "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" ]; then
    echo "[VidForge] Downloading Wan2.2 5B diffusion model (~10GB)..."
    echo "[VidForge] This will take a while..."
    # Use curl instead of huggingface-cli for reliability
    download_file \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors" \
        "$DIFFUSION_DIR/wan2.2_ti2v_5B_fp16.safetensors" \
        "Wan2.2 diffusion model"
fi

download_file \
    "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
    "$CLIP_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
    "Wan2.2 CLIP model"

# ============================================
# LTX 2.3 (Video Generation - Optional)
# ============================================
echo "[VidForge] Checking for LTX 2.3 models..."

LTX_CHECKPOINT_DIR="$MODELS_DIR/checkpoints"
LTX_TEXT_ENC_DIR="$MODELS_DIR/text_encoders"

# LTX models are very large - only download if explicitly enabled
if [ "${VIDFORGE_DOWNLOAD_LTX:-false}" = "true" ]; then
    download_file \
        "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-dev.safetensors" \
        "$LTX_CHECKPOINT_DIR/ltx-2.3-22b-dev.safetensors" \
        "LTX 2.3 dev checkpoint"
    
    download_file \
        "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-1.1.safetensors" \
        "$LTX_CHECKPOINT_DIR/ltx-2.3-22b-distilled-1.1.safetensors" \
        "LTX 2.3 distilled checkpoint"
else
    echo "[VidForge] LTX 2.3 download skipped (set VIDFORGE_DOWNLOAD_LTX=true to enable)"
fi

# ============================================
# LTXVideo Gemma Text Encoder
# ============================================
GEMMA_DIR="$TEXT_ENCODERS_DIR/gemma-3-12b-it"
mkdir -p "$GEMMA_DIR"

# Only download Gemma if LTX is enabled
if [ "${VIDFORGE_DOWNLOAD_LTX:-false}" = "true" ]; then
    GEMMA_BASE_URL="https://huggingface.co/lightricks/gemma-3-12b-it-qat-q4_0-unquantized/resolve/main"
    
    # Small config/tokenizer files
    for f in .gitattributes README.md added_tokens.json chat_template.json config.json \
             generation_config.json preprocessor_config.json processor_config.json \
             special_tokens_map.json tokenizer.json tokenizer.model \
             tokenizer_config.json model.safetensors.index.json; do
        download_file "$GEMMA_BASE_URL/$f" "$GEMMA_DIR/$f" "gemma/$f"
    done
    
    # Model shards (large files ~5GB each)
    download_file "$GEMMA_BASE_URL/model-00001-of-00005.safetensors" \
        "$GEMMA_DIR/model-00001-of-00005.safetensors" "gemma/shard-1"
    download_file "$GEMMA_BASE_URL/model-00002-of-00005.safetensors" \
        "$GEMMA_DIR/model-00002-of-00005.safetensors" "gemma/shard-2"
    download_file "$GEMMA_BASE_URL/model-00003-of-00005.safetensors" \
        "$GEMMA_DIR/model-00003-of-00005.safetensors" "gemma/shard-3"
    download_file "$GEMMA_BASE_URL/model-00004-of-00005.safetensors" \
        "$GEMMA_DIR/model-00004-of-00005.safetensors" "gemma/shard-4"
    download_file "$GEMMA_BASE_URL/model-00005-of-00005.safetensors" \
        "$GEMMA_DIR/model-00005-of-00005.safetensors" "gemma/shard-5"
fi

# ============================================
# UMT5 text encoder symlink (needed by LTXVideo)
# ============================================
if [ -f "$CLIP_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors" ] && [ ! -f "$TEXT_ENCODERS_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors" ]; then
    ln -s "$CLIP_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
        "$TEXT_ENCODERS_DIR/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    echo "[VidForge] Created umt5 symlink in text_encoders/"
fi

echo "[VidForge] ==========================================="
echo "[VidForge] Model setup complete!"
echo "[VidForge] Starting ComfyUI..."
echo "[VidForge] ==========================================="

exec /opt/venv/bin/python main.py --listen 0.0.0.0 --port 8188 "$@"
