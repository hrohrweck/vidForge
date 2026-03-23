# VidForge Progress Summary

## Goal

Get the VidForge video generation system working, specifically the ComfyUI container that generates videos using Wan2.2 models on AMD ROCm (Radeon 890M - gfx1151).

## Completed Work

### 1. Model Downloads Fixed
- Corrected VAE filename: `wan2.2_vae.safetensors` (for 5B model)
- Corrected CLIP filename: `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (flat path)
- Using `huggingface-cli download` with `--local-dir` for flat directory structure
- Models download to flat directories (not nested paths)

### 2. ROCm Compatibility
- Updated Dockerfile to use ROCm 7.1.1 base image (`rocm/dev-ubuntu-22.04:7.1.1-complete`)
- Radeon 890M (gfx1151) requires ROCm 7.1.1

### 3. Workflow JSON Files
- `wan_t2v.json` - Correct workflow for Wan2.2 5B text-to-video
- `wan_s2v.json` - Updated to match correct structure with proper nodes:
  - CLIPLoader, CLIPTextEncode, VAELoader, UNETLoader, ModelSamplingSD3
  - Wan22ImageToVideoLatent, KSampler, VAEDecode, SaveVideo

### 4. Backend Code Fixed
- `video_generator.py` - Fixed all LSP errors:
  - Updated `_generate_segments` to use correct ComfyUI API methods
  - Updated `_generate_video_segments` to use correct ComfyUI API methods
  - Added missing methods: `_merge_segments`, `_add_audio`, `_generate_video`, `_generate_preview`
  - Fixed method calls: `wait_for_completion` + `get_output` instead of `wait_for_result`
  - Fixed method calls: `merge_videos` instead of `concatenate_videos`
  - Updated node class type: `Wan22ImageToVideoLatent` instead of `WanImageToVideo`
  - Updated CLIP model path to flat filename

## Model Directories (host-mounted)

```
/home/sysop/vidForge/models/comfyui/
├── clip/
│   └── umt5_xxl_fp8_e4m3fn_scaled.safetensors (~6.7GB)
├── vae/
│   └── wan2.2_vae.safetensors (~254MB)
└── diffusion_models/
    └── wan2.2_ti2v_5B_fp16.safetensors (~10GB)
```

## Next Steps

1. **Rebuild containers**:
   ```bash
   cd /home/sysop/vidForge/docker
   docker-compose up -d --build comfyui
   docker-compose up -d --build backend worker
   ```

2. **Verify model downloads** - Check that models downloaded correctly:
   ```bash
   ls -la /home/sysop/vidForge/models/comfyui/clip/
   ls -la /home/sysop/vidForge/models/comfyui/vae/
   ls -la /home/sysop/vidForge/models/comfyui/diffusion_models/
   ```

3. **Test video generation** - Create a new job and verify end-to-end

## Key Files Modified

- `docker/comfyui/Dockerfile` - ROCm 7.1.1 base image
- `docker/comfyui/comfyui-entrypoint.sh` - Model download commands
- `backend/app/services/video_generator.py` - Fixed all LSP errors
- `backend/app/comfyui/workflows/wan_t2v.json` - Correct workflow structure
- `backend/app/comfyui/workflows/wan_s2v.json` - Correct workflow structure
