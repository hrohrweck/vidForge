# Atlas Cloud AI (atlascloud.ai) — Image & Video Model Parameters Reference

> **Version:** 2025-05 | **Last updated:** 2025-05-28
> This document is structured for LLM consumption as a comprehensive reference for all controllable parameters across image and video generation models available on the Atlas Cloud AI platform.

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [API Endpoints & Authentication](#2-api-endpoints--authentication)
3. [Async Task Pattern (Image & Video)](#3-async-task-pattern-image--video)
4. [Image Generation — Universal Parameters](#4-image-generation--universal-parameters)
5. [Video Generation — Universal Parameters](#5-video-generation--universal-parameters)
6. [Model-Specific Image Parameters](#6-model-specific-image-parameters)
7. [Model-Specific Video Parameters](#7-model-specific-video-parameters)
8. [Complete Model Catalog](#8-complete-model-catalog)
9. [Upload Media Endpoint](#9-upload-media-endpoint)
10. [Asset Library (Subject Reference)](#10-asset-library-subject-reference)
11. [SDK & Client Integrations](#11-sdk--client-integrations)
12. [Pricing Reference](#12-pricing-reference)
13. [Key Findings & Caveats](#13-key-findings--caveats)
14. [Sources](#14-sources)

---

## 1. Platform Overview

**Atlas Cloud** is a **full-modal AI API aggregation platform** that provides unified access to **300+ AI models** through a single API key and a single billing account. It aggregates models from major providers including OpenAI, Google, ByteDance, Alibaba (Qwen/Wan), Black Forest Labs (FLUX), Kling (Kuaishou), Vidu, MiniMax, and more.

| Property | Value |
|---|---|
| **Website** | https://www.atlascloud.ai |
| **API Base URL** | `https://api.atlascloud.ai` |
| **Documentation** | https://atlascloud.ai/docs/en |
| **GitHub** | https://github.com/AtlasCloudAI (18 repos, including MCP server) |
| **Discord** | https://discord.com/invite/kUCbEZn8js |
| **Model Count** | 300+ models (203 media models) |
| **Billing** | Pay-as-you-go, no subscriptions, no seat fees |
| **OpenAI-Compatible** | Yes (for LLM chat completions) |
| **Doc Languages** | 20 (EN, ZH, KO, ES, DE, FR, JA, IT, PT, AR, HI, NL, PL, TR, VI, TH, ID, SV, RU, and more) |

### Model Categories

| Category | Count |
|---|---|
| Text-to-Image | 34 |
| Image-to-Image | 27 |
| Text-to-Video | 38 |
| Image-to-Video | 88 |
| Video-to-Video | 9 |
| Audio-to-Video | 3 |
| LLM (Chat) | 100+ |

### Provider Breakdown

| Provider | Model Count |
|---|---|
| Qwen & Wan (Alibaba) | 57 |
| Kling (Kuaishou) | 35 |
| Google | 23 |
| Vidu | 25 |
| ByteDance | 31 |
| MiniMax | 12 |
| OpenAI | 8 |
| FLUX (Black Forest Labs) | 5 |
| Grok (xAI) | 2 |

---

## 2. API Endpoints & Authentication

### Authentication

All requests require the `Authorization` header with a Bearer token:

```
Authorization: Bearer <your-api-key>
```

API keys are generated from the Atlas Cloud dashboard at https://www.atlascloud.ai.

### Core Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/chat/completions` | POST | LLM / Chat (OpenAI-compatible) |
| `/api/v1/model/generateImage` | POST | Image generation (async) |
| `/api/v1/model/generateVideo` | POST | Video generation (async) |
| `/api/v1/model/uploadMedia` | POST | Upload files (multipart/form-data) |
| `/api/v1/model/prediction/{id}` | GET | Poll async generation task status & result |
| `/api/v1/model/getResult?predictionId={id}` | GET | Alternative result retrieval endpoint |

### Model ID Naming Convention

```
{provider}/{model-family}/{task-type}
```

Examples:
- `openai/gpt-image-2/text-to-image`
- `bytedance/seedance-2.0/image-to-video`
- `wan-2.7/text-to-image`
- `google/veo3.1-fast/text-to-video`
- `kling/kling-v3.0/text-to-video`
- `vidu/q3-pro/start-end-to-video`

---

## 3. Async Task Pattern (Image & Video)

All image and video generation on Atlas Cloud is **asynchronous**. The workflow follows a three-step pattern: submit, poll, retrieve.

### Step 1: Submit Generation Task

```python
import requests

url = "https://api.atlascloud.ai/api/v1/model/generateImage"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
body = {
    "model": "openai/gpt-image-2/text-to-image",
    "prompt": "a sunset over mountains",
    "size": "1024x1024",
    "quality": "high"
}
response = requests.post(url, headers=headers, json=body)
data = response.json()
prediction_id = data["data"]["id"]  # e.g., "pred_abc123"
```

**Submit Response:**
```json
{
  "code": 200,
  "data": {
    "id": "pred_abc123",
    "status": "processing",
    "model": "openai/gpt-image-2/text-to-image",
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

### Step 2: Poll for Completion

```python
import time

poll_url = f"https://api.atlascloud.ai/api/v1/model/prediction/{prediction_id}"
while True:
    result = requests.get(poll_url, headers=headers).json()
    status = result["data"]["status"]
    if status in ("completed", "succeeded"):
        break
    elif status in ("failed", "timeout"):
        print("Generation failed:", result)
        break
    time.sleep(3)  # Poll every 2-5 seconds
```

### Step 3: Retrieve Result

**Completed Response:**
```json
{
  "data": {
    "id": "pred_abc123",
    "status": "completed",
    "model": "openai/gpt-image-2/text-to-image",
    "outputs": [
      "https://storage.atlascloud.ai/outputs/result.png"
    ],
    "metrics": {
      "predict_time": 4.2
    },
    "created_at": "2025-01-01T00:00:00Z",
    "completed_at": "2025-01-01T00:00:04Z"
  }
}
```

### Status Values

| Status | Meaning |
|---|---|
| `processing` | Task is being executed |
| `completed` / `succeeded` | Task finished successfully; `outputs` contains URLs |
| `failed` | Task failed; check for error details |
| `timeout` | Task timed out |

### Response Nesting Note

The actual prediction object is nested under `data`:
- Status: `response["data"]["status"]`
- Outputs: `response["data"]["outputs"][0]`
- Predict time: `response["data"]["metrics"]["predict_time"]`

---

## 4. Image Generation — Universal Parameters

These parameters are commonly available across most image generation models on Atlas Cloud. However, **parameter names and allowed values can differ by model** — always check the specific model's detail page.

### Common Parameters

| Parameter | Type | Required | Description | Common Values |
|---|---|---|---|---|
| `model` | string | **YES** | Model identifier | e.g., `"openai/gpt-image-2/text-to-image"` |
| `prompt` | string | **YES** | Text prompt for generation | Any string |
| `negative_prompt` | string | no | What to avoid in generation | Any string |
| `aspect_ratio` | string | no | Output aspect ratio | `"1:1"`, `"16:9"`, `"9:16"`, `"4:3"`, `"3:4"`, `"3:2"`, `"2:3"` |
| `size` | string | no | Explicit resolution (WxH) | e.g., `"1024x1024"`, `"1536x1024"` |
| `width` | integer | no | Explicit width in pixels | Integer (overrides aspect_ratio) |
| `height` | integer | no | Explicit height in pixels | Integer (overrides aspect_ratio) |
| `quality` | string | no | Image quality level | `"low"`, `"medium"`, `"high"` |
| `output_format` | string | no | Output file format | `"jpeg"`, `"png"` |
| `seed` | integer | no | Reproducibility seed | Any integer |
| `num_images` | integer | no | Number of images to generate | Integer (model-dependent) |
| `image_url` | string | no | Input image URL (for I2I models) | URL string |
| `moderation` | string | no | Content moderation level | Model-specific values |
| `enable_base64_output` | boolean | no | Return base64 instead of URL | `true`, `false` (API-only) |
| `enable_sync_mode` | boolean | no | Wait synchronously for result | `true`, `false` (API-only) |

### How Aspect Ratios Map to Resolutions

| Aspect Ratio | Orientation | Typical Resolution |
|---|---|---|
| `1:1` | Square | 1024x1024 |
| `16:9` | Landscape | 1536x864 or similar |
| `9:16` | Portrait | 864x1536 or similar |
| `4:3` | Landscape | 1024x768 or similar |
| `3:4` | Portrait | 768x1024 or similar |
| `3:2` | Landscape | 1536x1024 |
| `2:3` | Portrait | 1024x1536 |
| `21:9` | Ultrawide | 1920x824 or similar |

> **Note:** When using `size`, exact pixel dimensions are specified. When using `aspect_ratio`, resolution is computed automatically. For models supporting `size`, arbitrary WxH dimensions may be supported (divisible by 16, aspect ratio between 1:3 and 3:1).

---

## 5. Video Generation — Universal Parameters

### Common Parameters

| Parameter | Type | Required | Description | Common Values |
|---|---|---|---|---|
| `model` | string | **YES** | Model identifier | e.g., `"bytedance/seedance-2.0/text-to-video"` |
| `prompt` | string | **YES** | Text description of video | String (limits vary by model) |
| `duration` | integer | no | Video length in seconds | Model-dependent: `4`–`15` (varies widely) |
| `resolution` | string | no | Output resolution | `"480p"`, `"720p"`, `"720p-SR"`, `"1080p"`, `"1080p-SR"`, `"1440p-SR"` |
| `ratio` | string | no | Output aspect ratio | `"16:9"`, `"4:3"`, `"1:1"`, `"3:4"`, `"9:16"`, `"21:9"`, `"adaptive"` |
| `generate_audio` | boolean | no | Generate audio/sound effects | `true`, `false` |
| `watermark` | boolean | no | Add watermark to output | `true`, `false` |
| `return_last_frame` | boolean | no | Return last frame as image | `true`, `false` |
| `seed` | integer | no | Reproducibility seed | Any integer |

### Image-to-Video Extra Parameters

For image-to-video (I2V) models, add these to the request body:

| Parameter | Type | Description |
|---|---|---|
| `image_url` | string | URL of the source image (from uploadMedia or external URL) |
| `last_image_url` | string | URL of the desired last frame (for start+end frame control) |
| `reference_images` | array | Array of reference image URLs (for reference-to-video models) |

### Video-to-Video Extra Parameters

| Parameter | Type | Description |
|---|---|---|
| `video_url` | string | URL of the source video |
| `audio_url` | string | URL of audio for lip-sync or soundtrack |

### Resolution Tier Explanation

| Resolution | Description |
|---|---|
| `480p` | Standard definition (854x480 or similar) |
| `720p` | HD (1280x720 or similar) |
| `720p-SR` | HD with Super Resolution (enhanced quality) |
| `1080p` | Full HD (1920x1080 or similar) |
| `1080p-SR` | Full HD with Super Resolution |
| `1440p-SR` | QHD with Super Resolution |

> **SR = Super Resolution**: Models with SR variants apply an additional upscaling/enhancement pass to improve output quality beyond the native resolution.

### Video Input Modes

| Mode | Description | Required Input |
|---|---|---|
| Text-to-Video (T2V) | Generate video from text prompt | `prompt` |
| Image-to-Video (I2V) | Animate a still image | `prompt` + `image_url` |
| Reference-to-Video | Generate using reference images | `prompt` + `reference_images` (array) |
| Start-End-to-Video | Control first and last frame | `prompt` + `image_url` + `last_image_url` |
| Video Editing | Edit/modify existing video | `prompt` + `video_url` |

---

## 6. Model-Specific Image Parameters

### 6.1 GPT Image 2 (OpenAI)

**Model IDs:**
- `openai/gpt-image-2/text-to-image` ($0.009/PIC)
- `openai/gpt-image-2/edit` ($0.01/PIC)

| Parameter | Type | Required | Default | Allowed Values |
|---|---|---|---|---|
| `model` | string | **YES** | — | `"openai/gpt-image-2/text-to-image"` or `"openai/gpt-image-2/edit"` |
| `prompt` | string | **YES** | — | Positive prompt text |
| `quality` | string | no | `"medium"` | `"low"`, `"medium"`, `"high"` |
| `size` | string | no | `"1024x1024"` | `"auto"`, `"1024x768"`, `"768x1024"`, `"1024x1024"`, `"1024x1536"`, `"1536x1024"`, `"2560x1440"`, `"1440x2560"`, `"3840x2160"`, `"2160x3840"`, or arbitrary `WxH` (divisible by 16, aspect 1:3–3:1) |
| `output_format` | string | no | `"jpeg"` | `"jpeg"`, `"png"` |
| `moderation` | string | no | `"low"` | Content moderation level |
| `enable_base64_output` | boolean | no | `false` | `true`, `false` |
| `enable_sync_mode` | boolean | no | `false` | `true`, `false` |

### 6.2 GPT Image 1.5 (OpenAI)

**Model ID:** `openai/gpt-image-1.5/text-to-image` ($0.009/PIC)

Parameters follow the same schema as GPT Image 2.

### 6.3 ERNIE Image Turbo (Baidu)

**Model ID:** `baidu/ernie-image-turbo/text-to-image` (**FREE**)

Basic text-to-image with standard parameters. Limited customization compared to paid models.

### 6.4 Wan 2.7 (Alibaba Qwen&Wan)

**Model IDs:**
- `wan-2.7/text-to-image` ($0.03/PIC)
- `wan-2.7/image-to-image` ($0.03/PIC)
- `wan-2.7-pro/text-to-image` ($0.075/PIC)
- `wan-2.7-pro/image-to-image` ($0.075/PIC)

Both standard and Pro variants available. Pro variant produces higher quality at higher cost.

### 6.5 Qwen Image 2.0 (Alibaba)

**Model IDs:**
- `qwen-image-2.0/text-to-image` ($0.035/PIC)
- `qwen-image-2.0/edit` ($0.035/PIC)
- `qwen-image-2.0-pro/text-to-image` ($0.075/PIC)
- `qwen-image-2.0-pro/edit` ($0.075/PIC)

### 6.6 Seedream v5.0 Lite (ByteDance)

**Model IDs:**
- `seedream-v5.0-lite` ($0.035/PIC) — text-to-image
- `seedream-v5.0-lite/edit` ($0.035/PIC) — image-to-image
- `seedream-v5.0-lite/edit-sequential` ($0.035/PIC) — sequential image-to-image
- `seedream-v5.0-lite/sequential` ($0.035/PIC) — sequential text-to-image

### 6.7 Nano Banana 2 (Google)

**Model IDs:**
- `nano-banana-2/text-to-image` ($0.08/PIC)
- `nano-banana-2/edit` ($0.08/PIC)

### 6.8 Grok Imagine Image Quality (xAI)

**Model ID:** `xai/grok-imagine-image-quality/text-to-image` (from $0.06/gen)

| Parameter | Type | Required | Default | Allowed Values |
|---|---|---|---|---|
| `model` | string | **YES** | — | `"xai/grok-imagine-image-quality/text-to-image"` |
| `prompt` | string | **YES** | — | Text prompt |
| `aspect_ratio` | string | no | `"1:1"` | `"1:1"`, `"16:9"`, `"9:16"`, `"4:3"`, `"3:4"`, `"3:2"`, `"2:3"` |

### 6.9 Ideogram v3

**Model IDs:**
- Ideogram v3 text-to-image and image-to-image variants available.
- Known for strong text rendering in images.

---

## 7. Model-Specific Video Parameters

### 7.1 Seedance 2.0 (ByteDance)

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `bytedance/seedance-2.0/text-to-video` | Text-to-Video | ~$0.112/SEC |
| `bytedance/seedance-2.0/image-to-video` | Image-to-Video | ~$0.112/SEC |
| `bytedance/seedance-2.0/reference-to-video` | Reference-to-Video | ~$0.112/SEC |
| `bytedance/seedance-2.0-fast/text-to-video` | Text-to-Video (fast) | ~$0.09/SEC |
| `bytedance/seedance-2.0-fast/image-to-video` | Image-to-Video (fast) | ~$0.09/SEC |
| `bytedance/seedance-2.0-fast/reference-to-video` | Reference-to-Video (fast) | ~$0.09/SEC |

**Parameters:**

| Parameter | Type | Required | Default | Allowed Values |
|---|---|---|---|---|
| `model` | string | **YES** | — | See model IDs above |
| `prompt` | string | **YES** | — | Chinese <500 chars, English <1000 words |
| `duration` | integer | no | `5` | `-1` (auto), `4`–`15` (seconds) |
| `resolution` | string | no | `"720p"` | `"480p"`, `"720p"`, `"720p-SR"`, `"1080p"`, `"1080p-SR"`, `"1440p-SR"` |
| `ratio` | string | no | `"adaptive"` | `"16:9"`, `"4:3"`, `"1:1"`, `"3:4"`, `"9:16"`, `"21:9"`, `"adaptive"` |
| `generate_audio` | boolean | no | `true` | `true`, `false` |
| `watermark` | boolean | no | `false` | `true`, `false` |
| `return_last_frame` | boolean | no | `false` | `true`, `false` |
| `image_url` | string | no* | — | URL of source image (*required for I2V) |
| `last_image_url` | string | no | — | URL of desired last frame |
| `reference_images` | array | no* | — | Array of image URLs (*required for reference-to-video) |

**Features:** First-frame + optional last-frame input, native audio generation, real human face support, auto aspect ratio mode.

### 7.2 Wan 2.7 (Alibaba Qwen&Wan)

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `wan-2.7/text-to-video` | Text-to-Video | $0.1/SEC |
| `wan-2.7/image-to-video` | Image-to-Video | $0.1/SEC |
| `wan-2.7/reference-to-video` | Reference-to-Video | $0.1/SEC |
| `wan-2.7/video-edit` | Video Editing | $0.1/SEC |

Multi-shot video support, up to 15 seconds. Supports various aspect ratios and resolutions.

### 7.3 Wan 2.2 Turbo (Alibaba)

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `wan-2.2-turbo/image-to-video` | Image-to-Video | $0.02/SEC |
| `wan-2.2-turbo-infinite/image-to-video` | Image-to-Video (infinite) | $0.02/SEC |
| `wan-2.2-turbo-infinite/image-to-video-lora` | Image-to-Video + LoRA | $0.026/SEC |
| `wan-2.2-turbo-spicy/image-to-video` | Image-to-Video (enhanced) | $0.02/SEC |
| `wan-2.2-turbo-spicy/image-to-video-lora` | Image-to-Video + LoRA | $0.026/SEC |

Budget-friendly video generation. LoRA support for style/persona customization. "Infinite" variant for extended generation.

### 7.4 Google Veo 3.1

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `google/veo3.1/text-to-video` | Text-to-Video | $0.2/SEC |
| `google/veo3.1/image-to-video` | Image-to-Video | $0.2/SEC |
| `google/veo3.1/reference-to-video` | Reference-to-Video | $0.2/SEC |
| `google/veo3.1-fast/text-to-video` | Text-to-Video (fast) | $0.08/SEC |
| `google/veo3.1-fast/image-to-video` | Image-to-Video (fast) | $0.08/SEC |
| `google/veo3.1-lite/text-to-video` | Text-to-Video (lite) | $0.05/SEC |
| `google/veo3.1-lite/start-end-frame-to-video` | Start-End-to-Video | $0.05/SEC |
| `google/veo3.1-lite/image-to-video` | Image-to-Video (lite) | $0.05/SEC |

Three quality tiers: full quality (highest cost, best quality), fast (balanced), and lite (budget). Lite tier supports start+end frame control.

### 7.5 Google Gemini Omni Flash

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `google/gemini-omni-flash/text-to-video` | Text-to-Video | $0.15/SEC |
| `google/gemini-omni-flash/image-to-video` | Image-to-Video | $0.15/SEC |

### 7.6 Kling v2.5 / v3.0 (Kuaishou)

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `kling/kling-v2.5/text-to-video` | Text-to-Video | Varies |
| `kling/kling-v3.0/text-to-video` | Text-to-Video | Varies |
| `kling/kling-v3.0/image-to-video` | Image-to-Video | Varies |
| `kling/kling-v3.0-m ctrl/...` | Motion Control | Varies |

35 Kling models available. Parameters vary by specific model. Known for high-quality facial animation and multi-scene support.

### 7.7 Vidu Q3 / Q3 Pro / Q3 Mix

**Model IDs:**
| Model ID | Type | Price |
|---|---|---|
| `vidu/q3/start-end-to-video` | Start-End-to-Video | Varies |
| `vidu/q3/reference-to-video` | Reference-to-Video | $0.05/SEC |
| `vidu/q3-pro/start-end-to-video` | Start-End-to-Video (Pro) | Varies |
| `vidu/q3-mix/reference-to-video` | Reference-to-Video (Mix) | $0.125/SEC |
| `vidu/image-to-video-2.0` | Image-to-Video | Varies |

**Vidu Q3 Pro Specifications:**
- Duration: Up to **16 seconds** continuous
- Resolution: **1080p**
- FPS: **24 fps** (longest continuous video at this quality)
- Features: Audio generation, BGM, start/end frame input, intelligent camera switching

**Vidu Image-to-Video 2.0:**
- Resolution: Up to 1280x720
- Frames: 80–160 frames (4s–8s)
- Strengths: Facial animation, artistic + photorealistic

### 7.8 HappyHorse 1.0

**Model ID:** `happyhorse-1.0/text-to-video` ($0.14/SEC)

### 7.9 InfiniteTalk (Talking Head)

**Model ID:** `atlascloud/infinitetalk`

Special purpose model: generates a lip-synced talking head video from a portrait image + audio input.

| Feature | Details |
|---|---|
| Duration | Up to **10 minutes** |
| Languages | Any language |
| Dual-person | Supported |
| Upscaling | Up to 720p |
| Input | Portrait image + audio file |

---

## 8. Complete Model Catalog

### Text-to-Image Models

| Model ID | Provider | Price |
|---|---|---|
| `openai/gpt-image-2/text-to-image` | OpenAI | $0.009/PIC |
| `openai/gpt-image-1.5/text-to-image` | OpenAI | $0.009/PIC |
| `baidu/ernie-image-turbo/text-to-image` | Baidu | **FREE** |
| `wan-2.7/text-to-image` | Qwen&Wan | $0.03/PIC |
| `wan-2.7-pro/text-to-image` | Qwen&Wan | $0.075/PIC |
| `nano-banana-2/text-to-image` | Google | $0.08/PIC |
| `qwen-image-2.0/text-to-image` | Qwen&Wan | $0.035/PIC |
| `qwen-image-2.0-pro/text-to-image` | Qwen&Wan | $0.075/PIC |
| `seedream-v5.0-lite` | ByteDance | $0.035/PIC |
| `seedream-v5.0-lite/sequential` | ByteDance | $0.035/PIC |
| `xai/grok-imagine-image-quality/text-to-image` | xAI | ~$0.06/PIC |

### Image-to-Image Models

| Model ID | Provider | Price |
|---|---|---|
| `openai/gpt-image-2/edit` | OpenAI | $0.01/PIC |
| `wan-2.7/image-to-image` | Qwen&Wan | $0.03/PIC |
| `wan-2.7-pro/image-to-image` | Qwen&Wan | $0.075/PIC |
| `nano-banana-2/edit` | Google | $0.08/PIC |
| `qwen-image-2.0/edit` | Qwen&Wan | $0.035/PIC |
| `qwen-image-2.0-pro/edit` | Qwen&Wan | $0.075/PIC |
| `seedream-v5.0-lite/edit` | ByteDance | $0.035/PIC |
| `seedream-v5.0-lite/edit-sequential` | ByteDance | $0.035/PIC |

### Text-to-Video Models

| Model ID | Provider | Price |
|---|---|---|
| `bytedance/seedance-2.0/text-to-video` | ByteDance | ~$0.112/SEC |
| `bytedance/seedance-2.0-fast/text-to-video` | ByteDance | ~$0.09/SEC |
| `wan-2.7/text-to-video` | Qwen&Wan | $0.1/SEC |
| `google/veo3.1/text-to-video` | Google | $0.2/SEC |
| `google/veo3.1-fast/text-to-video` | Google | $0.08/SEC |
| `google/veo3.1-lite/text-to-video` | Google | $0.05/SEC |
| `google/gemini-omni-flash/text-to-video` | Google | $0.15/SEC |
| `kling/kling-v2.5/text-to-video` | Kling | Varies |
| `kling/kling-v3.0/text-to-video` | Kling | Varies |
| `happyhorse-1.0/text-to-video` | — | $0.14/SEC |

### Image-to-Video Models

| Model ID | Provider | Price |
|---|---|---|
| `bytedance/seedance-2.0/image-to-video` | ByteDance | ~$0.112/SEC |
| `bytedance/seedance-2.0-fast/image-to-video` | ByteDance | ~$0.09/SEC |
| `wan-2.7/image-to-video` | Qwen&Wan | $0.1/SEC |
| `wan-2.2-turbo/image-to-video` | Qwen&Wan | $0.02/SEC |
| `wan-2.2-turbo-infinite/image-to-video` | Qwen&Wan | $0.02/SEC |
| `wan-2.2-turbo-spicy/image-to-video` | Qwen&Wan | $0.02/SEC |
| `google/veo3.1/image-to-video` | Google | $0.2/SEC |
| `google/veo3.1-fast/image-to-video` | Google | $0.08/SEC |
| `google/veo3.1-lite/image-to-video` | Google | $0.05/SEC |
| `google/veo3.1-lite/start-end-frame-to-video` | Google | $0.05/SEC |
| `google/gemini-omni-flash/image-to-video` | Google | $0.15/SEC |
| `vidu/q3/reference-to-video` | Vidu | $0.05/SEC |
| `vidu/q3-mix/reference-to-video` | Vidu | $0.125/SEC |
| `vidu/q3-pro/start-end-to-video` | Vidu | Varies |
| `vidu/image-to-video-2.0` | Vidu | Varies |
| `kling/kling-v3.0/image-to-video` | Kling | Varies |

> **Note:** This is a partial catalog. The platform hosts 300+ total models. For the complete list, visit https://www.atlascloud.ai/models/list.

---

## 9. Upload Media Endpoint

For image-to-video and image-to-image workflows, you must upload media files first.

**Endpoint:** `POST /api/v1/model/uploadMedia`
**Content-Type:** `multipart/form-data`

```python
import requests

url = "https://api.atlascloud.ai/api/v1/model/uploadMedia"
headers = {"Authorization": "Bearer YOUR_API_KEY"}
files = {"file": open("my_image.png", "rb")}
response = requests.post(url, headers=headers, files=files)
data = response.json()
image_url = data["data"]["download_url"]
# Use image_url in generation requests as `image_url` parameter
```

**Response:**
```json
{
  "data": {
    "download_url": "https://storage.atlascloud.ai/uploads/abc123/image.png",
    "file_name": "image.png",
    "content_type": "image/png",
    "size": 1024000
  }
}
```

**Important:** Uploaded files are **temporary** and may be periodically cleaned up. Use the Asset Library (Section 10) for persistent storage.

---

## 10. Asset Library (Subject Reference)

The Asset Library provides persistent storage for reference images used in generation workflows.

**Base URL:** `https://console.atlascloud.ai/api/v1/sd/assets`

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/sd/assets` | Create asset |
| GET | `/api/v1/sd/assets` | List assets |
| GET | `/api/v1/sd/assets/{id}` | Get asset details |
| PUT | `/api/v1/sd/assets/{id}` | Rename asset |
| DELETE | `/api/v1/sd/assets/{id}` | Move to trash |
| POST | `/api/v1/sd/assets/{id}/restore` | Restore from trash |

### Asset Image Requirements

| Requirement | Limit |
|---|---|
| Formats | JPEG, PNG, WebP, BMP, TIFF, GIF, HEIC |
| Resolution | 300–6000 px |
| Aspect ratio | 0.4–2.5 |
| Max file size | 30 MB |

### Referencing Assets in Generation

Once an asset is created and its status is `Active`, reference it in generation requests using the `asset://` protocol:

```json
{
  "model": "wan-2.2-turbo/image-to-video",
  "prompt": "A woman walking through a garden",
  "image_url": "asset://atlas_asset_id_here",
  "duration": 5
}
```

---

## 11. SDK & Client Integrations

### OpenAI-Compatible SDK (for LLMs)

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-atlas-cloud-api-key",
    base_url="https://api.atlascloud.ai/v1"
)

response = client.chat.completions.create(
    model="openai/gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### CLI Tool

```bash
# macOS / Linux
brew install AtlasCloudAI/tap/atlascloud
```

### MCP Server

- GitHub: `github.com/AtlasCloudAI/mcp-server`
- 100+ supported MCP clients
- Tools: `atlas_generate_image`, `atlas_generate_video`, `atlas_chat`, `atlas_list_models`, `atlas_quick_generate`, `atlas_upload_media`

### Skills Package (Claude Code / IDE Integration)

```bash
npm install -g @atlascloudai/skills
atlas-cloud-skills install
```

Supports: Claude Code, Cursor, Windsurf, VS Code, GitHub Copilot, Cline, Roo Code, Amp, Goose, Replit, and 40+ more tools.

### Third-Party Tool Configuration

| Tool | Configuration |
|---|---|
| Chatbox / Cherry Studio | Set API Host to `https://api.atlascloud.ai/v1` |
| OpenWebUI | Configure as OpenAI-compatible provider |
| OpenRouter | Available as provider "atlas-cloud" |

---

## 12. Pricing Reference

### Billing Model

| Type | Billing Unit | Notes |
|---|---|---|
| LLM (Chat) | Per million tokens | Input + output token count |
| Image Generation | Per generation (PIC) | Varies by model, resolution, quality |
| Video Generation | Per second (SEC) | Varies by model, duration, resolution |
| Image Tools | Per operation | Background removal, upscaling, face swap |

### Image Generation Pricing (Sample)

| Price Tier | Examples |
|---|---|
| **FREE** | Baidu ERNIE Turbo |
| $0.003–$0.01/PIC | Z-Image Turbo, GPT Image 2 |
| $0.03–$0.04/PIC | Wan 2.7, Qwen Image 2.0, Seedream v5.0 Lite |
| $0.06–$0.08/PIC | Grok Imagine, Nano Banana 2, Qwen Image Pro |

### Video Generation Pricing (Sample)

| Price Tier | Examples |
|---|---|
| $0.02/SEC | Wan 2.2 Turbo (cheapest) |
| $0.05/SEC | Veo 3.1 Lite, Vidu Q3 |
| $0.08–$0.09/SEC | Veo 3.1 Fast, Seedance 2.0 Fast |
| $0.1–$0.112/SEC | Wan 2.7, Seedance 2.0 |
| $0.15/SEC | Gemini Omni Flash |
| $0.2/SEC | Veo 3.1 (premium) |

### Account Details

| Detail | Value |
|---|---|
| Minimum top-up | $10 |
| Credits expire | 365 days from purchase |
| New user bonus | 20% on first top-up |
| Referral bonus | 25% (up to $100) |
| Payment methods | Credit card, WeChat Pay, Alipay, cryptocurrency |
| Volume discounts | Contact sales@atlascloud.ai |

---

## 13. Key Findings & Caveats

1. **Dedicated endpoints for image/video.** Unlike Poe (which routes everything through Chat Completions), Atlas Cloud has dedicated `/api/v1/model/generateImage` and `/api/v1/model/generateVideo` endpoints.

2. **All image/video generation is asynchronous.** You must implement a submit → poll → retrieve pattern. Use `enable_sync_mode: true` (where supported) for synchronous waiting.

3. **Model-specific parameters vary significantly.** Each model has its own parameter schema with different allowed values and defaults. Always consult the model's detail page before integrating.

4. **Parameter names are not fully standardized.** Different models may use `aspect_ratio` vs `ratio` vs `size` for controlling output dimensions. The `size` parameter (GPT Image 2) supports arbitrary WxH, while `ratio` (Seedance) uses preset values.

5. **Super Resolution (SR) variants** are available for many video models as a resolution option, providing enhanced quality at the same nominal resolution.

6. **`duration` ranges vary widely** between models — from 4s to 16s. Some models support `-1` for automatic duration. Always check the model's constraints.

7. **Upload is required for I2V workflows.** Use `/api/v1/model/uploadMedia` to upload images, then pass the returned URL as `image_url`. For persistent references, use the Asset Library (`asset://` protocol).

8. **Prediction response is nested under `data`.** The actual prediction object is at `response["data"]`, and outputs are at `response["data"]["outputs"][0]`.

9. **LoRA support is available** for select models (e.g., `wan-2.2-turbo-infinite/image-to-video-lora`). See the LoRA guide for details.

10. **API-only parameters** like `enable_sync_mode`, `enable_base64_output`, and `moderation` are not exposed in the playground UI — they are exclusive to the API.

11. **Image generation is fast** — most models complete in under 5 seconds. Video generation times vary from 10s to several minutes depending on duration and resolution.

12. **No `/v1/images/generations` endpoint.** Atlas Cloud uses its own custom endpoints, not the OpenAI Images API format. Only the LLM chat endpoint follows OpenAI conventions.

13. **Uploaded files are temporary.** Use the Asset Library for persistent reference images. The `asset://<id>` protocol allows referencing stored assets directly in generation requests.

---

## 14. Sources

| # | URL | Type |
|---|---|---|
| 1 | https://atlascloud.ai/docs/en | Official Documentation |
| 2 | https://atlascloud.ai/docs/en/get-started | Quick Start Guide |
| 3 | https://atlascloud.ai/docs/en/models/get-start | Models API Getting Started |
| 4 | https://atlascloud.ai/docs/en/models/image | Image Generation Docs |
| 5 | https://atlascloud.ai/docs/en/models/video | Video Generation Docs |
| 6 | https://atlascloud.ai/docs/en/models/price | API Pricing |
| 7 | https://atlascloud.ai/docs/en/billing | Billing Details |
| 8 | https://atlascloud.ai/docs/en/skills | Skills / SDK Reference |
| 9 | https://www.atlascloud.ai/models/list | Full Model Catalog |
| 10 | https://www.atlascloud.ai/models/media | Image & Video Model Listing |
| 11 | https://www.atlascloud.ai/models/explore | Model Explorer |
| 12 | https://www.atlascloud.ai/developer | Developer Portal |
| 13 | https://www.atlascloud.ai/models/xai/grok-imagine-image-quality/text-to-image | Grok Imagine Model Page |
| 14 | https://www.atlascloud.ai/models/openai/gpt-image-2/text-to-image | GPT Image 2 Model Page |
| 15 | https://www.atlascloud.ai/models/alibaba/qwen-image/text-to-image-plus | Qwen Image Model Page |
| 16 | https://www.atlascloud.ai/models/bytedance/seedance-2.0/image-to-video | Seedance 2.0 Model Page |
| 17 | https://www.atlascloud.ai/models/vidu/q3-pro/start-end-to-video | Vidu Q3 Pro Model Page |
| 18 | https://www.atlascloud.ai/models/atlascloud/wan-2.2/image-to-video | Wan 2.2 Model Page |
| 19 | https://www.atlascloud.ai/models/atlascloud/infinitetalk | InfiniteTalk Model Page |
| 20 | https://www.atlascloud.ai/blog/guides/atlas-cloud-image-generation-api-guide | Image API Guide Blog |
| 21 | https://www.atlascloud.ai/blog/guides/beyond-the-prompt-building-custom-workflows-with-the-atlas-cloud-ai-video-api | Video API Guide Blog |
| 22 | https://www.atlascloud.ai/blog/guides/cheapest-ai-video-generation-api-2026 | Video Pricing Comparison Blog |
| 23 | https://github.com/AtlasCloudAI | GitHub Organization |
| 24 | https://github.com/AtlasCloudAI/mcp-server | MCP Server Repository |
| 25 | https://openrouter.ai/provider/atlas-cloud | OpenRouter Listing |
