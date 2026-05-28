# MuAPI.ai — Image & Video Model Parameters Reference

> **Version:** 2025-05 | **Last updated:** 2025-05-28
> This document is structured for LLM consumption as a comprehensive reference for all controllable parameters across image and video generation models available on the MuAPI platform.

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [API Endpoints & Authentication](#2-api-endpoints--authentication)
3. [Async Task Pattern](#3-async-task-pattern)
4. [Image Generation — Universal Parameters](#4-image-generation--universal-parameters)
5. [Video Generation — Universal Parameters](#5-video-generation--universal-parameters)
6. [Model-Specific Image Parameters](#6-model-specific-image-parameters)
7. [Model-Specific Video Parameters](#7-model-specific-video-parameters)
8. [AI Video Effects & VFX](#8-ai-video-effects--vfx)
9. [Audio, Music & Lipsync Models](#9-audio-music--lipsync-models)
10. [Complete Model Catalog](#10-complete-model-catalog)
11. [Workflow & Agent System](#11-workflow--agent-system)
12. [Pricing Reference](#12-pricing-reference)
13. [SDK & Client Integrations](#13-sdk--client-integrations)
14. [Key Findings & Caveats](#14-key-findings--caveats)
15. [Sources](#15-sources)

---

## 1. Platform Overview

**MuAPI** is a **high-performance, serverless AI API aggregator** operated by **Vadoo.tv**. It provides unified access to **100+ state-of-the-art generative AI models** for image, video, audio, and enhancement through a single RESTful API. Its unique differentiator is an **Agentic Orchestration layer** — Workflows, AI Agents, and Storyboarding on top of raw API access.

| Property | Value |
|---|---|
| **Website** | https://muapi.ai |
| **API Base URL** | `https://api.muapi.ai` |
| **Documentation** | https://muapi.ai/docs |
| **Playground** | https://muapi.ai/playground |
| **GitHub** | https://github.com/SamurAIGPT (muapi-cli, muapi-comfyui) |
| **Discord** | https://discord.com/invite/zpnuBRXhKg |
| **Operator** | Vadoo.tv (support@vadoo.tv) |
| **Model Count** | 100+ models (142+ listed) |
| **Billing** | Pay-as-you-go credits, no subscription, credits never expire |
| **Claim** | "40% cheaper than official model costs" |

### Platform Differentiators

| Feature | Description |
|---|---|
| **Workflows** | Visual node-based pipeline editor + natural language creation |
| **Agents** | AI agents with customizable skills and persistent memory |
| **Agent Skills** | Public recipe system for agent specialization |
| **Storyboarding** | Generate consistent episodic content with character/scene persistence |
| **Sandbox Keys** | Free API keys that return mock data for integration testing |
| **Cost Transparency** | Every response includes exact USD cost charged; cost estimation API |

### Model Categories

| Category | Description |
|---|---|
| Text-to-Image (T2I) | 30+ models |
| Image-to-Image (I2I) | 20+ models |
| Text-to-Video (T2V) | 20+ models |
| Image-to-Video (I2V) | 20+ models |
| Video-to-Video (V2V) | 5+ models |
| Audio-to-Video / Lipsync | 5+ models |
| Music Generation | 4 models (Suno V5) |
| LoRA Training | 4 models |
| AI Effects & VFX | 2 endpoints |

---

## 2. API Endpoints & Authentication

### Authentication

All requests use the `x-api-key` header (NOT `Authorization: Bearer`):

```
x-api-key: <YOUR_MUAPIAPP_API_KEY>
```

| Property | Value |
|---|---|
| **Header name** | `x-api-key` |
| **Key prefix** | `sk-` |
| **Obtain from** | MuAPI Dashboard → API Keys section |
| **Key types** | Production (consumes credits) / Sandbox (free mock data) |

### Key Types

| Type | Behavior |
|---|---|
| **Production Key** | Consumes credits, processes real generation tasks |
| **Sandbox Key** | Free testing — returns mock data instantly, marked with Sandbox badge |

> **Security note:** Keys are shown only once at creation. Store securely in environment variables. Rotate periodically.

### Core Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/{model-endpoint}` | POST | Yes | Submit a generation task |
| `/api/v1/predictions/{id}/result` | GET | Yes | Poll async task result |
| `/api/v1/models` | GET | **No** | List all models with pricing (public) |
| `/api/v1/models/{name}` | GET | **No** | Single model details with input/output schemas (public) |
| `/api/v1/models/{name}/estimate-cost` | POST | **No** | Estimate cost for specific request payload (public) |
| `/api/v1/account/balance` | GET | Yes | Get credit balance |
| `/api/v1/account/topup` | POST | Yes | Initiate Stripe checkout for top-up |

### Endpoint Naming Convention

Each model has a unique endpoint path. Examples:

```
/api/v1/flux-dev-image              # Flux Dev text-to-image
/api/v1/flux_dev_lora_image         # Flux Dev LoRA
/api/v1/flux-kontext-dev-i2i        # Flux Kontext image-to-image
/api/v1/veo3-fast                   # Veo 3 Fast text-to-video
/api/v1/generate_wan_ai_effects     # AI Video Effects & VFX
/api/v1/suno-create-music           # Suno V5 music creation
/api/v1/ai-image-face-swap          # Face swap
/api/v1/ai-background-remover       # Background removal
```

---

## 3. Async Task Pattern

### Synchronous Pattern (Most Image Models)

Most image models return results directly in the submit response:

```python
import requests

response = requests.post(
    "https://api.muapi.ai/api/v1/flux-dev-image",
    headers={"x-api-key": "YOUR_KEY", "Content-Type": "application/json"},
    json={
        "prompt": "A sunset over mountains",
        "size": "1024*1024",
        "num_images": 1
    }
)
data = response.json()
image_url = data["data"]["outputs"][0]
```

### Async Pattern (Video, Audio, Long-Running Tasks)

1. **Submit** — returns `request_id`
2. **Poll** — check status until completed
3. **Retrieve** — get output URLs

```python
# Step 1: Submit
response = requests.post(
    "https://api.muapi.ai/api/v1/veo3-fast",
    headers={"x-api-key": "YOUR_KEY", "Content-Type": "application/json"},
    json={"prompt": "A drone flyover of mountains", "duration": 8}
)
request_id = response.json()["data"]["id"]

# Step 2: Poll
import time
while True:
    result = requests.get(
        f"https://api.muapi.ai/api/v1/predictions/{request_id}/result",
        headers={"x-api-key": "YOUR_KEY"}
    ).json()
    status = result["data"]["status"]
    if status in ("completed", "succeeded"):
        break
    elif status == "failed":
        print("Failed:", result)
        break
    time.sleep(0.5)  # ~500ms recommended

# Step 3: Retrieve
video_url = result["video"]["url"]
```

### Webhook Alternative

Append `webhook_url` to avoid polling:

```python
response = requests.post(
    "https://api.muapi.ai/api/v1/veo3-fast",
    headers={"x-api-key": "YOUR_KEY", "Content-Type": "application/json"},
    json={
        "prompt": "A drone flyover",
        "duration": 8,
        "webhook_url": "https://your.app/callback"
    }
)
```

MuAPI will POST to your callback URL when the task completes.

### Polling Configuration

| Parameter | Default | Description |
|---|---|---|
| `maxAttempts` | 60 (video: 120) | Maximum poll attempts |
| `interval` | 2000ms (recommended: 500ms) | Poll interval in milliseconds |

### Response Structure

**Submit Response:**
```json
{
  "request_id": "abc123",
  "status": "processing",
  "cost": {
    "amount_usd": 0.0042,
    "amount_credits": 1,
    "bonus_credits_used": 0,
    "refunded": false
  },
  "data": {
    "id": "abc123",
    "model": "flux-dev",
    "outputs": [],
    "urls": {"get": "/api/v1/predictions/abc123/result"},
    "status": "processing",
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

**Completed Result Response:**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "abc123",
    "model": "flux-dev",
    "outputs": ["https://cdn.muapi.ai/output1.jpg"],
    "has_nsfw_contents": [false],
    "status": "completed",
    "created_at": "2025-01-01T12:00:00Z",
    "timings": {"inference": 3200}
  }
}
```

**Video Model Result (additional field):**
```json
{
  "data": { "status": "completed" },
  "video": { "url": "https://cdn.muapi.ai/video.mp4" }
}
```

### Per-Request Cost Headers

Every API response includes cost information in headers:

| Header | Example | Description |
|---|---|---|
| `X-MuAPI-Cost-USD` | `0.0042` | USD cost of this request |
| `X-MuAPI-Cost-Credits` | `1` | Credits consumed |
| `X-MuAPI-Cost-Bonus-Credits` | `0` | Bonus credits used |
| `X-Account-Balance` | `45.67` | Remaining account balance |

---

## 4. Image Generation — Universal Parameters

These parameters are commonly available across most image generation models on MuAPI. **Parameter names and allowed values differ by model** — always check the model's input schema via `GET /api/v1/models/{name}`.

### Common Parameters

| Parameter | Type | Required | Description | Common Values |
|---|---|---|---|---|
| `prompt` | string | **YES** | Text prompt for generation | Any string |
| `image` | string | no | Input image for I2I or inpainting | URL string |
| `image_url` | string | no | Alternative input image URL | URL string |
| `mask_image` | string | no | Mask for inpainting (white=new, black=preserve) | URL string |
| `strength` | number | no | Transformation extent for reference image | `0.0`–`1.0` (default: `0.8`) |
| `size` | string | no | Output dimensions | `"1024*1024"`, `"1536*1024"`, etc. |
| `aspect_ratio` | string | no | Output aspect ratio | `"1:1"`, `"16:9"`, `"9:16"`, `"4:3"`, `"3:4"` |
| `resolution` | string | no | Output resolution tier | `"1k"`, `"2k"`, `"4k"` (model-dependent) |
| `quality` | string | no | Quality setting | `"basic"`, `"medium"`, `"high"` (model-dependent) |
| `seed` | integer | no | Reproducibility seed | `-1` (random) to `9999999999` |
| `num_images` | integer | no | Number of images to generate | `1`–`4` (model-dependent) |
| `num_inference_steps` | integer | no | Number of inference steps | `1`–`50` (model-dependent) |
| `guidance_scale` | number | no | CFG scale — prompt adherence | `1.0`–`20.0` (model-dependent) |
| `enable_base64_output` | boolean | no | Return base64 instead of URL | `true`, `false` |
| `enable_safety_checker` | boolean | no | Enable NSFW content filter | `true`, `false` |
| `images_list` | array | no | Multiple reference images for I2I | Array of URLs |

### Size Format

MuAPI uses `*` (asterisk) as the separator for dimensions, not `x`:
- Correct: `"1024*1024"`, `"1536*1024"`
- **Not** `"1024x1024"` (this is Poe/Atlas Cloud format)

### How Aspect Ratios Map to Resolutions

| Aspect Ratio | Orientation | Typical Resolution |
|---|---|---|
| `1:1` | Square | 1024*1024 |
| `16:9` | Landscape | 1536*864 or similar |
| `9:16` | Portrait | 864*1536 or similar |
| `4:3` | Landscape | 1024*768 or similar |
| `3:4` | Portrait | 768*1024 or similar |
| `3:2` | Landscape | 1536*1024 |
| `21:9` | Ultrawide | 1920*824 or similar |

---

## 5. Video Generation — Universal Parameters

### Common Parameters

| Parameter | Type | Required | Description | Common Values |
|---|---|---|---|---|
| `prompt` | string | **YES** | Text description of video | String (limits vary by model) |
| `image_url` | string | No* | Starting frame for I2V (*required for I2V models) | URL string |
| `aspect_ratio` | string | no | Output aspect ratio | `"16:9"`, `"9:16"`, `"1:1"`, `"4:3"`, `"3:2"`, `"21:9"` |
| `resolution` | string | no | Output resolution | `"480p"`, `"720p"`, `"1080p"` |
| `quality` | string | no | Video quality tier | `"basic"`, `"medium"`, `"high"` |
| `duration` | number | no | Video length in seconds | Model-dependent: `4`–`15` |
| `seed` | number | no | Reproducibility seed | `-1` (random) or integer |
| `webhook_url` | string | no | Webhook callback URL | URL string |

### Image-to-Video Extra Parameters

| Parameter | Type | Description |
|---|---|---|
| `image_url` | string | URL of the source/starting frame image |
| `last_image_url` | string | URL of the desired last frame (start-end control) |
| `reference_images` | array | Array of reference image URLs |
| `driving_video_url` | string | Driving video for expression transfer (Act Two) |

### Video-to-Video Extra Parameters

| Parameter | Type | Description |
|---|---|---|
| `video_url` | string | URL of the source video |
| `audio_url` | string | URL of audio for lipsync/soundtrack |

### Video Input Modes

| Mode | Description | Required Input |
|---|---|---|
| Text-to-Video (T2V) | Generate video from text prompt | `prompt` |
| Image-to-Video (I2V) | Animate a still image | `prompt` + `image_url` |
| Reference-to-Video | Generate using reference images | `prompt` + `reference_images` |
| Start-End-to-Video | Control first and last frame | `prompt` + `image_url` + `last_image_url` |
| Video Editing (V2V) | Transform existing video | `prompt` + `video_url` |
| Expression Transfer | Transfer facial expressions | `image_url` + `driving_video_url` |

---

## 6. Model-Specific Image Parameters

### 6.1 Flux Dev

**Endpoint:** `POST /api/v1/flux-dev-image`

| Parameter | Type | Required | Default | Range | Description |
|---|---|---|---|---|---|
| `prompt` | string | **YES** | — | — | Text prompt for generation |
| `image` | string | no | — | — | Input image for I2I or inpainting |
| `mask_image` | string | no | — | — | Mask (white=generate, black=preserve) |
| `strength` | number | no | `0.8` | `0.00`–`1.00` | Transform extent for reference image |
| `size` | string | no | `"1024*1024"` | 512–1536 per dim | Output dimensions (W*H format) |
| `num_inference_steps` | integer | no | `28` | `1`–`50` | Number of inference steps |
| `seed` | integer | no | `-1` | `-1`–`9999999999` | Reproducibility seed (-1=random) |
| `guidance_scale` | number | no | `3.5` | `1.0`–`20.0` | CFG scale — prompt adherence |
| `num_images` | integer | no | `1` | `1`–`4` | Number of images |
| `enable_base64_output` | boolean | no | `false` | — | Return base64 instead of URL |
| `enable_safety_checker` | boolean | no | `true` | — | Enable NSFW content filter |

**Cost:** $0.025 per generation

### 6.2 Flux Dev LoRA

**Endpoint:** `POST /api/v1/flux_dev_lora_image`

| Parameter | Type | Required | Default | Range | Description |
|---|---|---|---|---|---|
| `prompt` | string | **YES** | — | 2–3000 chars | Text prompt |
| `model_id` | string | **YES** | — | — | LoRA model identifier |
| `weight` | number | no | `1.0` | `0`–`4` | LoRA weight/strength |
| `num_images` | integer | no | `1` | `1`–`4` | Number of images |
| `seed` | integer | no | `-1` | — | Reproducibility seed |

Up to 3 LoRAs can be combined in a single request.

**Cost:** $0.015 per generation

### 6.3 Flux Schnell

**Endpoint:** `POST /api/v1/flux-schnell-image`

Lightning-fast variant for rapid iteration. Parameters similar to Flux Dev but optimized for speed over quality.

### 6.4 Flux Kontext (I2I)

**Endpoints:**
- `POST /api/v1/flux-kontext-dev-i2i`
- `POST /api/v1/flux-kontext-pro-i2i`
- `POST /api/v1/flux-kontext-max-i2i`

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | **YES** | — | Edit/generation prompt |
| `image` | string | **YES** | — | Input image URL |
| `aspect_ratio` | string | no | `"1:1"` | `"1:1"`, `"16:9"`, `"9:16"` |
| `num_images` | integer | no | `1` | `1`–`4` |

Tiers: Dev (fast), Pro (balanced), Max (highest quality, photorealistic/cinematic).

### 6.5 Flux Pulid (Face Consistency)

**Endpoint:** `POST /api/v1/flux-pulid-image`

Consistent face rendering without fine-tuning. Uses reference face images.

### 6.6 Midjourney (v7)

**Endpoint:** `POST /api/v1/midjourney-v7-text-to-image`

Industry-leading aesthetic quality. Parameters follow MuAPI common image parameters.

### 6.7 GPT-4o Image Generation

**Endpoints:**
- `POST /api/v1/gpt4o-text-to-image` — Text-to-image
- `POST /api/v1/gpt4o-image-to-image` — Image editing
- `POST /api/v1/gpt4o-edit` — Natural language image editing

### 6.8 Google Imagen 4

**Endpoints:**
- `POST /api/v1/google-imagen4` — Standard
- `POST /api/v1/google-imagen4-fast` — Speed-optimized
- `POST /api/v1/google-imagen4-ultra` — Flagship, maximum quality

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `prompt` | string | **YES** | — | Text prompt |
| `aspect_ratio` | string | no | `"1:1"` | `"16:9"`, `"9:16"`, `"1:1"`, `"4:3"`, `"3:4"` |
| `num_images` | integer | no | `1` | `1`–`4` |
| `resolution` | string | no | — | Up to 2K |

Features: Photorealistic output, SynthID watermarks.

### 6.9 Ideogram v3

**Endpoints:**
- `POST /api/v1/ideogram-v3-t2i` — Text-to-image with strong text rendering
- `POST /api/v1/ideogram-character` — Consistent character generation from reference

### 6.10 HiDream

**Endpoints:**
- `POST /api/v1/hidream-fast-image`
- `POST /api/v1/hidream-dev-image`
- `POST /api/v1/hidream-full-image` ($0.04/gen)
- `POST /api/v1/hidream-i1-full-image` — Most advanced, high-resolution

### 6.11 Seedream (ByteDance)

**Endpoint:** `POST /api/v1/seedream-image` (also known as `bytedance-seedream-v3`)

Visually rich/artistic — fantasy, anime, surrealism, vibrant color.

### 6.12 Nano Banana (Google Gemini)

**Endpoints:**
- `POST /api/v1/nano-banana-image` — Text-to-image
- `POST /api/v1/nano-banana-edit` — Natural language editing, character preservation

Hyper-realistic, physics-aware visuals, natural language editing.

### 6.13 Qwen Image (Alibaba)

**Endpoints:**
- `POST /api/v1/qwen-image` — Text-to-image
- `POST /api/v1/qwen-image-edit` — Image editing/modification

### 6.14 Wan 2.1 Text-to-Image

**Endpoint:** `POST /api/v1/wan2.1-text-to-image`

High-resolution, photorealistic.

### 6.15 Specialized Image Tools

| Model ID | Endpoint | Description | Cost |
|---|---|---|---|
| `ai-background-remover` | `/api/v1/ai-background-remover` | Remove backgrounds | Included |
| `ai-image-face-swap` | `/api/v1/ai-image-face-swap` | Face swap (supports `target_index`) | $0.02/gen |
| `ai-image-upscaler` | `/api/v1/ai-image-upscaler` | Upscale images | Varies |
| `ai-ghibli-style` | `/api/v1/ai-ghibli-style` | Ghibli style transfer | Included |
| `ai-color-photo` | `/api/v1/ai-color-photo` | B&W to color | Included |
| `ai-skin-enhancer` | `/api/v1/ai-skin-enhancer` | Skin smoothing | Varies |
| `ai-product-photography` | `/api/v1/ai-product-photography` | Product shots with backgrounds | Varies |
| `ai-product-shot` | `/api/v1/ai-product-shot` | Studio-quality product images | Varies |
| `portrait-stylist` | `/api/v1/portrait-stylist` | Professional portrait styles | Varies |
| `photo-pack` | `/api/v1/photo-pack` | Multi-style professional portraits | Varies |
| `ai-dress-change` | `/api/v1/ai-dress-change` | Change outfits | Varies |
| `ai-object-eraser` | `/api/v1/ai-object-eraser` | Remove objects | Varies |
| `ai-image-extension` | `/api/v1/ai-image-extension` | Outpainting | Varies |

### 6.16 Kling O3 Image Edit

**Endpoint:** `POST /api/v1/kling-o3-image-edit`

Natural language image editing with up to 10 reference images, 1K–4K resolution, up to 9 output images.

### 6.17 MiniMax Image Subject Reference

**Endpoint:** `POST /api/v1/minimax-image-01-subject-reference`

Subject reference for character consistency across generations.

---

## 7. Model-Specific Video Parameters

### 7.1 Google Veo 3

**Endpoints:**
- `POST /api/v1/veo3-text-to-video` — Full quality
- `POST /api/v1/veo3-fast-text-to-video` — Quick prototyping
- `POST /api/v1/veo3-image-to-video` — I2V
- `POST /api/v1/veo3-fast-image-to-video` — Fast I2V

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `prompt` | string | **YES** | — | Text description |
| `aspect_ratio` | string | no | `"16:9"` | `"16:9"`, `"9:16"` |
| `duration` | number | no | varies | Seconds |
| `resolution` | string | no | varies | Video resolution |
| `image_url` | string | No* | — | Source image (*required for I2V) |

**Pricing:** Dynamic — scales with duration, resolution, and model tier. Veo 3 Fast base cost ~$0.40+.

### 7.2 Kling v2.1

**Endpoints:**
- `POST /api/v1/kling-v2.1-master-t2v` — Master quality T2V
- `POST /api/v1/kling-v2.1-master-i2v` — Master quality I2V
- `POST /api/v1/kling-v2.1-standard-i2v` — Standard I2V
- `POST /api/v1/kling-v2.1-pro-i2v` — Pro I2V

Three quality tiers: Standard (fastest), Pro (balanced), Master (highest quality, vivid, cinematic).

### 7.3 Wan 2.1 / 2.2 (Alibaba)

**Endpoints:**
- `POST /api/v1/wan2.1-text-to-video` — T2V
- `POST /api/v1/wan2.2-text-to-video` — T2V (stylized, anime/cinematic)
- `POST /api/v1/wan2.2-5b-fast-t2v` — Lightweight/fast variant
- `POST /api/v1/wan2.1-reference-video` — Reference-based I2V
- `POST /api/v1/wan2.1-lora-i2v` — LoRA I2V (identity consistency)
- `POST /api/v1/wan2.2-image-to-video` — Standard I2V
- `POST /api/v1/wan2.1-lora-t2v` — LoRA T2V

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `prompt` | string | **YES** | — | Text description |
| `image_url` | string | No* | — | Source image (*required for I2V) |
| `aspect_ratio` | string | no | `"16:9"` | `"16:9"`, `"9:16"`, `"1:1"`, `"4:3"` |
| `resolution` | string | no | `"480p"` | `"480p"`, `"720p"` |
| `quality` | string | no | `"medium"` | `"medium"`, `"high"` |
| `duration` | number | no | `5` | `5`–`10` seconds |

**LoRA variants** support up to 3 LoRA modules with configurable weight for identity/style consistency.

### 7.4 ByteDance Seedance

**Endpoints:**
- `POST /api/v1/seedance-pro-t2v` — Pro quality
- `POST /api/v1/seedance-lite-t2v` — Lite quality
- `POST /api/v1/seedance-pro-i2v` — Pro I2V
- `POST /api/v1/seedance-lite-i2v` — Lite I2V

Two quality tiers: Lite (fast, basic motion) and Pro (high-end, cinematic).

### 7.5 Runway

**Endpoints:**
- `POST /api/v1/runway-text-to-video` — T2V
- `POST /api/v1/runway-image-to-video` — I2V
- `POST /api/v1/runway-act-two-i2v` — Expression transfer from driving video
- `POST /api/v1/runway-act-two-v2v` — V2V expression transfer
- `POST /api/v1/runway-aleph-v2v` — Transform video into new visual style

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `prompt` | string | **YES** | — | Text description |
| `image_url` | string | No* | — | Source image |
| `resolution` | string | no | `"720p"` | `"720p"`, `"1080p"` |
| `duration` | number | no | `5` | `5`, `8` seconds |

**Act Two** requires `driving_video_url` for facial expression transfer.

### 7.6 Hunyuan (Tencent)

**Endpoints:**
- `POST /api/v1/hunyuan-text-to-video` — T2V
- `POST /api/v1/hunyuan-fast-text-to-video` — Fast T2V
- `POST /api/v1/hunyuan-image-to-video` — I2V

Detailed, dynamic video generation. Fast variant for accelerated prototyping.

**Pricing:** Hunyuan I2V $0.15 per generation.

### 7.7 PixVerse

**Endpoints:**
- `POST /api/v1/pixverse-v4.5-t2v` — v4.5 T2V
- `POST /api/v1/pixverse-v5-t2v` — v5 T2V (ultra-high resolution)
- `POST /api/v1/pixverse-v4.5-i2v` — v4.5 I2V
- `POST /api/v1/pixverse-v5-i2v` — v5 I2V

### 7.8 Vidu

**Endpoints:**
- `POST /api/v1/vidu-v2.0-t2v` — v2.0 T2V
- `POST /api/v1/vidu-v2.0-i2v` — v2.0 I2V
- `POST /api/v1/vidu-q3-pro-image-to-video` — Q3 Pro I2V (1080p)
- `POST /api/v1/vidu-q1-reference` — Multi-reference I2V (up to 7 images)

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `resolution` | string | no | `"720p"` | `"360p"`, `"720p"`, `"1080p"` |
| `duration` | number | no | `4` | `4` seconds (fixed) |

### 7.9 MiniMax Hailuo 02

**Endpoints:**
- `POST /api/v1/minimax-hailuo-02-standard-t2v` — Standard T2V
- `POST /api/v1/minimax-hailuo-02-pro-t2v` — Pro T2V
- `POST /api/v1/minimax-hailuo-02-standard-i2v` — Standard I2V
- `POST /api/v1/minimax-hailuo-02-pro-i2v` — Pro I2V

### 7.10 OpenAI Sora 2

**Endpoints:**
- `POST /api/v1/openai-sora-2-image-to-video` — I2V

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `duration` | number | no | `10` | `10`, `15` seconds |

**Limitation:** No realistic portraits.

### 7.11 Luma

**Endpoints:**
- `POST /api/v1/luma-modify-video` — Transform video scenes while keeping motion/timing
- `POST /api/v1/luma-flash-reframe` — Adjust aspect ratio, add consistent content to edges

### 7.12 InfiniteTalk (Talking Head)

**Endpoints:**
- `POST /api/v1/infinitetalk-image-to-video` — Image + dialogue script to video
- `POST /api/v1/infinitetalk-video-to-video` — Re-animate lip movements

### 7.13 Lipsync Models

| Model ID | Endpoint | Description |
|---|---|---|
| `sync-lipsync` | `/api/v1/sync-lipsync` | Standard lipsync from audio |
| `latent-sync` | `/api/v1/latentsync-video` | LatentSync V2V lipsync |
| `creatify-lipsync` | `/api/v1/creatify-lipsync` | Optimized for speed and consistency |
| `veed-lipsync` | `/api/v1/veed-lipsync` | VEED lipsync model |

### 7.14 ByteDance SD 2 (VIP)

**Endpoint:** `POST /api/v1/sd-2-vip-text-to-video-1080p`

| Parameter | Type | Required | Default | Values |
|---|---|---|---|---|
| `resolution` | string | no | `"1080p"` | `"1080p"` |
| `duration` | number | no | `5` | `4`–`15` seconds |

Features: Audio-visual sync, 1080p output.

### 7.15 Wan 2.2 Speech-to-Video

**Endpoint:** `POST /api/v1/wan2.2-speech-to-video`

Talking video from static image + speech audio.

---

## 8. AI Video Effects & VFX

### AI Video Effects

**Endpoint:** `POST /api/v1/generate_wan_ai_effects`

| Parameter | Type | Required | Default | Values | Description |
|---|---|---|---|---|---|
| `prompt` | string | Yes | `""` | — | Description prompt |
| `image_url` | string | Yes | `""` | — | Input image URL |
| `name` | string | Yes | `""` | — | Effect preset name |
| `aspect_ratio` | string | no | `"16:9"` | `"1:1"`, `"9:16"`, `"16:9"` | Output aspect ratio |
| `resolution` | string | no | `"480p"` | `"480p"`, `"720p"` | Output resolution |
| `quality` | string | no | `"medium"` | `"medium"`, `"high"` | Quality level |
| `duration` | number | no | `5` | `5`–`10` | Video length in seconds |

**Pretrained Effect Presets:**

| Preset | Type |
|---|---|
| VHS Footage | Style transfer |
| Samurai It | Style transfer |
| Film Noir | Color grading |
| Inflate It | Distortion |
| Cakeify | Transformation |
| Building Explosion | VFX |
| Car Explosion | VFX |

Also supports prompt-driven custom effects: rotation, animal, assassin, angry, etc.

**Input formats:** MP4, MOV, WebM
**Duration:** Under 10 seconds (short-form content)

### VFX (Cinematic Visual Effects)

Shares the same endpoint: `POST /api/v1/generate_wan_ai_effects`

Features spatially-aware compositing and temporal control for cinematic effects (explosions, disintegration, lightning, etc.).

### Image Effects

**Endpoint:** `POST /api/v1/image-effects`

Visual transformations, color grading, and cinematic filters applied to images.

---

## 9. Audio, Music & Lipsync Models

### Suno V5 Music

| Endpoint | Description |
|---|---|
| `POST /api/v1/suno-create-music` | Create full songs with vocals, lyrics, instrumentation |
| `POST /api/v1/suno-remix-music` | Transform audio into new style while keeping melody |
| `POST /api/v1/suno-extend-music` | Extend audio tracks preserving style |

### MMAudio v2

| Endpoint | Description | Cost |
|---|---|---|
| `POST /api/v1/mmaudio-v2/text-to-audio` | Text-to-audio (Foley, SFX, speech) | $0.01/gen |
| `POST /api/v1/mmaudio-v2/video-to-video` | Sync audio with video motion | Varies |

---

## 10. Complete Model Catalog

### Text-to-Image

| Model ID | Endpoint Suffix | Provider | Notes |
|---|---|---|---|
| `flux-dev` | `flux-dev-image` | Black Forest Labs | $0.025/gen, 12B params |
| `flux-schnell` | `flux-schnell-image` | Black Forest Labs | Fast variant, ~$0.003/gen |
| `flux_dev_lora` | `flux_dev_lora_image` | Black Forest Labs | $0.015/gen, up to 3 LoRAs |
| `flux-kontext-pro-t2i` | `flux-kontext-pro-image` | Black Forest Labs | Contextual generation |
| `flux-kontext-max-t2i` | `flux-kontext-max-image` | Black Forest Labs | Photorealistic/cinematic |
| `hidream-fast` | `hidream-fast-image` | HiDream | Fast tier |
| `hidream-dev` | `hidream-dev-image` | HiDream | Balanced tier |
| `hidream-full` | `hidream-full-image` | HiDream | $0.04/gen |
| `hidream-i1-full` | `hidream-i1-full-image` | HiDream | Most advanced, high-res |
| `midjourney` | `midjourney-v7-text-to-image` | Midjourney | Industry-leading aesthetics |
| `gpt4o` | `gpt4o-text-to-image` | OpenAI | GPT-4o native image gen |
| `gpt4o-edit` | `gpt4o-edit` | OpenAI | Natural language editing |
| `seedream` | `seedream-image` | ByteDance | Artistic, vibrant color |
| `reve` | `reve-image` | Reve | — |
| `qwen-image` | `qwen-image` | Alibaba | — |
| `qwen-image-edit` | `qwen-image-edit` | Alibaba | — |
| `ideogram-v3-t2i` | `ideogram-v3-t2i` | Ideogram | Strong text rendering |
| `ideogram-character` | `ideogram-character` | Ideogram | Consistent characters |
| `google-imagen4` | `google-imagen4` | Google | Photorealistic, SynthID |
| `google-imagen4-fast` | `google-imagen4-fast` | Google | Speed-optimized |
| `google-imagen4-ultra` | `google-imagen4-ultra` | Google | Maximum quality |
| `nano-banana` | `nano-banana-image` | Google | Physics-aware, realistic |
| `nano-banana-edit` | `nano-banana-edit` | Google | Language-driven edits |
| `wan2.1-t2i` | `wan2.1-text-to-image` | Alibaba | High-resolution |
| `ai-anime-generator` | `ai-anime-generator` | — | Anime-style artwork |
| `sdxl-lora` | `sdxl-lora` | Stability AI | SDXL LoRA fine-tuning |

### Image-to-Image

| Model ID | Endpoint Suffix | Description |
|---|---|---|
| `flux-kontext-dev-i2i` | `flux-kontext-dev-i2i` | Transform with prompt guidance |
| `flux-kontext-pro-i2i` | `flux-kontext-pro-i2i` | Sketch refinement, style changes |
| `flux-kontext-max-i2i` | `flux-kontext-max-i2i` | Photo-to-art, concept refinement |
| `flux-pulid` | `flux-pulid-image` | Consistent face rendering |
| `gpt4o-i2i` | `gpt4o-image-to-image` | Transform based on new prompt |
| `seededit-v3` | `bytedance-seededit-v3` | Precise edits with masks |
| `kling-o3-image-edit` | `kling-o3-image-edit` | NL editing, 10 ref images, 1K-4K |
| `minimax-image-01-subject-reference` | `minimax-image-01-subject-reference` | Character consistency |

### Text-to-Video

| Model ID | Provider | Quality |
|---|---|---|
| `veo3` | Google | Photorealistic, cinematic |
| `veo3-fast` | Google | Quick prototyping |
| `kling-v2.1-master-t2v` | Kling | Master quality, vivid |
| `wan2.1-t2v` | Alibaba | Cinematic |
| `wan2.2-t2v` | Alibaba | Stylized, anime/cinematic |
| `wan2.2-5b-fast-t2v` | Alibaba | Lightweight/fast |
| `runway-t2v` | Runway | Professional |
| `seedance-pro-t2v` | ByteDance | High-end, cinematic |
| `seedance-lite-t2v` | ByteDance | Fast, basic motion |
| `hunyuan-t2v` | Tencent | Detailed, dynamic |
| `hunyuan-fast-t2v` | Tencent | Accelerated |
| `pixverse-v4.5-t2v` | PixVerse | Standard |
| `pixverse-v5-t2v` | PixVerse | Ultra-high resolution |
| `vidu-v2.0-t2v` | Vidu | Standard |
| `minimax-hailuo-02-std-t2v` | MiniMax | Standard |
| `minimax-hailuo-02-pro-t2v` | MiniMax | Pro |
| `sd-2-vip-t2v-1080p` | ByteDance | 1080p, audio-visual sync |
| `wan2.1-lora-t2v` | Alibaba | LoRA (custom style/character) |

### Image-to-Video

| Model ID | Provider | Notes |
|---|---|---|
| `veo3-i2v` | Google | Full quality |
| `veo3-fast-i2v` | Google | Fast variant |
| `kling-v2.1-master-i2v` | Kling | Master quality |
| `kling-v2.1-standard-i2v` | Kling | Standard |
| `kling-v2.1-pro-i2v` | Kling | Pro |
| `wan2.1-reference-video` | Alibaba | Reference-based |
| `wan2.1-lora-i2v` | Alibaba | LoRA identity consistency |
| `wan2.2-i2v` | Alibaba | Standard I2V |
| `runway-i2v` | Runway | Professional |
| `runway-act-two-i2v` | Runway | Expression transfer |
| `seedance-lite-i2v` | ByteDance | Fast, basic motion |
| `seedance-pro-i2v` | ByteDance | High-end, cinematic |
| `hunyuan-i2v` | Tencent | $0.15/gen |
| `vidu-v2.0-i2v` | Vidu | Standard |
| `vidu-q3-pro-i2v` | Vidu | 1080p |
| `vidu-q1-reference` | Vidu | Multi-ref (up to 7 images) |
| `minimax-hailuo-02-std-i2v` | MiniMax | Standard |
| `minimax-hailuo-02-pro-i2v` | MiniMax | Pro |
| `pixverse-v4.5-i2v` | PixVerse | Standard |
| `pixverse-v5-i2v` | PixVerse | Ultra-high resolution |
| `openai-sora-2-i2v` | OpenAI | 10s/15s, no realistic portraits |

---

## 11. Workflow & Agent System

### Workflows

MuAPI's **Workflow** system is a visual node-based pipeline editor for composing multi-step AI generation pipelines.

**Node Categories:**
| Category | Examples |
|---|---|
| **Text (LLM)** | Text generation, analysis |
| **Image** | T2I, I2I, enhancement |
| **Video** | T2V, I2V, effects |
| **Audio** | Music, speech, lipsync |
| **Utility** | Passthrough, Concatenator |
| **API** | Straico, WaveSpeed integration |

**Data Flow:** Connections with handles; Jinja2 syntax for dynamic references: `{{ node_id.outputs[0].value }}`

**API Execution:**
```
POST /api/workflow/{workflow_id}/run
Body: {"webhook_url": "https://your.app/callback"}  // optional
```

**CLI Integration:**
```bash
muapi workflow discover --output-json     # Catalog
muapi workflow get <id> --output-json     # Schema
muapi workflow run-interactive <id>       # Guided execution
muapi workflow create "prompt"            # AI-assisted creation
```

**Agentic Architect:** AI builds workflow graphs from natural language descriptions (e.g., "Design a marketing pipeline...").

### Agents

MuAPI's **Agent** system provides AI assistants with customizable skills and persistent conversation memory.

**Base URL:** `https://api.muapi.ai/agents`

| Endpoint | Method | Description |
|---|---|---|
| `/quick-create` | POST | Create agent from goal in one step |
| `/suggest` | POST | Get recommended config (name, prompt, skills) |
| `/skills` | GET | List all assignable skills |
| `/` | POST | Create agent (name, system_prompt, skill_ids) |
| `/user/agents` | GET | List user's agents |
| `/{agent_id}` | GET | Get agent details |
| `/{agent_id}` | PUT | Update agent |
| `/{agent_id}` | DELETE | Delete agent |
| `/{agent_id}/chat` | POST | Chat with agent |

**Quick Create:**
```json
POST /agents/quick-create
{"prompt": "I want an agent that creates minimalist brand assets"}
→ {"id": "agent_abc", "name": "Brand Guru", "skills": [...]}
```

**Chat with Memory:**
```json
POST /agents/{agent_id}/chat
{"message": "Design a logo", "conversation_id": "session-123"}
```
> Omitting `conversation_id` = no memory between messages.

**Public Agent Skills (no API key needed):**
```
GET /api/v1/agent-skills                    # List all recipes
GET /api/v1/agent-skills/{name}             # Full recipe body
```

### Storyboarding

Generate consistent episodic content with character/scene persistence across multiple frames/scenes.

---

## 12. Pricing Reference

### Billing Model

| Property | Value |
|---|---|
| System | Pay-as-you-go credit system |
| Subscription | None — no monthly fees |
| Credit expiry | **Never expire** |
| Purchase | Stripe (minimum ~$10) |
| Transparency | Every response includes exact USD cost |

### Sample Fixed Costs

| Model | Cost (USD) | Strategy |
|---|---|---|
| `flux-dev` | $0.025 | Fixed per request |
| `flux_dev_lora` | $0.015 | Fixed per request |
| `flux-schnell` | ~$0.003 | Fixed per request |
| `hidream-full` | $0.04 | Fixed per request |
| `ai-image-face-swap` | $0.02 | Fixed per request |
| `ai-background-remover` | Included | — |
| `ai-ghibli-style` | Included | — |
| `mmaudio-v2` | $0.01 | Fixed per request |
| `hunyuan-i2v` | $0.15 | Fixed per request |
| `nano-banana` | $0.03 | Fixed per request |

### Dynamic Pricing Models

Video/audio models use dynamic pricing based on:
- Output duration (5s vs 10s vs 15s)
- Resolution (480p vs 720p vs 1080p)
- Model tier (standard vs pro vs master/fast)

| Model | Base Cost | Strategy |
|---|---|---|
| `veo3-fast` | ~$0.40+ | Dynamic (duration + resolution) |
| Other video models | Varies | Dynamic (duration + resolution + quality) |

### Programmatic Pricing API (Public, No Auth)

**List all models with pricing:**
```
GET https://api.muapi.ai/api/v1/models
Filters: ?category=Text+to+Video, ?family=flux, ?group_of=image-generation
Returns: name, category, family, cost, cost_currency, cost_strategy, dynamic_pricing, endpoint
```

**Single model details with input/output schemas:**
```
GET https://api.muapi.ai/api/v1/models/{name}
```

**Estimate cost for a specific request configuration:**
```
POST https://api.muapi.ai/api/v1/models/{name}/estimate-cost
Body: {"prompt": "...", "duration": 8, "resolution": "720p"}
Returns: exact USD cost for that specific configuration
```

### Cost Transparency Features

Every API response includes:
```json
"cost": {
  "amount_usd": 0.0042,
  "amount_credits": 1,
  "bonus_credits_used": 0,
  "refunded": false
}
```

Plus response headers: `X-MuAPI-Cost-USD`, `X-MuAPI-Cost-Credits`, `X-Account-Balance`

---

## 13. SDK & Client Integrations

### REST API (Any Language)

Direct HTTP calls to `https://api.muapi.ai/api/v1/` with `x-api-key` header.

### MuAPI CLI

```bash
# Install (npm)
npm install -g muapi-cli
# Install (pip)
pip install muapi-cli

# Usage
muapi workflow discover --output-json
muapi workflow run-interactive <id>
muapi workflow create "Build a marketing pipeline"
```

### JavaScript SDK (MuapiClient)

```javascript
import { MuapiClient } from './lib/muapi.js';
const client = new MuapiClient();

// Text-to-Image
const result = await client.generateImage({
  model: 'flux-dev',
  prompt: 'A serene mountain landscape at sunset',
  aspect_ratio: '16:9',
  seed: 42
});

// Image-to-Video
const videoResult = await client.generateI2V({
  model: 'runway-image-to-video',
  image_url: 'https://example.com/start-frame.jpg',
  prompt: 'Camera slowly zooms in',
  duration: 5,
  aspect_ratio: '16:9'
});
```

### MCP Server

Model Context Protocol integration for Claude Code, Cursor, and other MCP-compatible tools.

### ComfyUI

```bash
# GitHub: https://github.com/SamurAIGPT/muapi-comfyui
```

11 dedicated ComfyUI nodes + generic passthrough. Access 100+ MuAPI models from within ComfyUI.

### n8n

```bash
# Package: n8n-nodes-muapi
```

2 community nodes (MuAPI + MuAPI Upload), 60+ models across 7 categories. Drag-and-drop workflow integration.

### LangChain

LangChain integration available for agent-based workflows.

---

## 14. Key Findings & Caveats

1. **Custom authentication header.** MuAPI uses `x-api-key` (not `Authorization: Bearer`). Key prefix is `sk-`.

2. **Size format uses `*` not `x`.** Dimensions are specified as `"1024*1024"` with an asterisk separator, unlike Poe (`"1024x1024"`) or Atlas Cloud (`"1024x1024"`).

3. **Dedicated endpoints per model.** Each model has its own unique endpoint path (e.g., `/api/v1/flux-dev-image`, `/api/v1/veo3-fast`). There is no single generic generation endpoint.

4. **Public model catalog API.** `GET /api/v1/models` is unauthenticated and returns full model list with pricing, endpoints, and input/output schemas. This is unique among the three platforms.

5. **Programmatic cost estimation.** `POST /api/v1/models/{name}/estimate-cost` lets you get exact pricing before submitting a request — no other platform offers this.

6. **Per-request cost transparency.** Every API response includes `cost` object and response headers with exact USD cost. Credits never expire.

7. **Sandbox keys for free testing.** Mock data API keys allow integration testing without consuming credits.

8. **Workflow and Agent systems.** MuAPI uniquely offers visual workflow composition, AI agents with persistent memory, and public agent skill recipes — features absent from Poe and Atlas Cloud.

9. **Image models are mostly synchronous.** Most image generation returns results directly. Video, audio, and long-running tasks use async submit+poll pattern.

10. **Webhook support.** Can append `webhook_url` to requests to receive automatic callbacks instead of polling.

11. **LoRA support for multiple models.** Flux Dev LoRA, Wan 2.1 LoRA T2V/I2V, SDXL LoRA — supports custom fine-tuning for style and identity consistency.

12. **Dynamic pricing for video.** Video model costs scale with duration, resolution, and quality tier. Always use the estimate-cost endpoint before production use.

13. **Comprehensive tool ecosystem.** CLI, MCP Server, ComfyUI nodes, n8n integration, LangChain support — more integration options than Poe or Atlas Cloud.

14. **VFX and AI Effects as first-class endpoints.** Dedicated endpoints for cinematic effects and video transformations (not just raw model access).

15. **Limited official documentation reliability.** Some doc pages (Quick Start, Webhooks, Credits) experienced 502 errors during research. Model-specific schemas should be verified via the public `/api/v1/models/{name}` endpoint.

---

## 15. Sources

| # | URL | Type |
|---|---|---|
| 1 | https://muapi.ai | Homepage |
| 2 | https://muapi.ai/docs/introduction | Official Documentation |
| 3 | https://muapi.ai/docs/authentication | Official Documentation |
| 4 | https://muapi.ai/docs/quick-start | Official Documentation |
| 5 | https://muapi.ai/docs/models | Official Documentation |
| 6 | https://muapi.ai/docs/pricing | Official Documentation |
| 7 | https://muapi.ai/docs/credits | Official Documentation |
| 8 | https://muapi.ai/docs/flux-dev | Official Documentation |
| 9 | https://muapi.ai/docs/ai-video-effects | Official Documentation |
| 10 | https://muapi.ai/docs/vfx | Official Documentation |
| 11 | https://muapi.ai/docs/music-and-speech | Official Documentation |
| 12 | https://muapi.ai/docs/webhooks | Official Documentation |
| 13 | https://muapi.ai/docs/workflows | Official Documentation |
| 14 | https://muapi.ai/docs/agents | Official Documentation |
| 15 | https://muapi.ai/docs/agent-skills | Official Documentation |
| 16 | https://muapi.ai/docs/cli | Official Documentation |
| 17 | https://muapi.ai/playground | Playground |
| 18 | https://muapi.ai/models | Model Catalog |
| 19 | https://muapi.ai/workflow | Workflows |
| 20 | https://muapi.ai/agents | Agents |
| 21 | https://muapi.ai/blog | Blog |
| 22 | https://discord.com/invite/zpnuBRXhKg | Discord |
| 23 | https://github.com/SamurAIGPT/muapi-cli | GitHub — CLI |
| 24 | https://github.com/SamurAIGPT/muapi-comfyui | GitHub — ComfyUI |
| 25 | https://github.com/topics/muapi | GitHub — All repos |
| 26 | https://anil-matcha-open-higgsfield-ai.mintlify.app/api/muapi-client | MuapiClient SDK Reference |
| 27 | https://thereisanaiforthat.com/ai/muapi/ | Third-Party Review |
| 28 | https://www.trustpilot.com/review/muapi.ai | Trustpilot Reviews |
