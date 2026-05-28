# Poe (by Quora) — Image & Video Model Parameters Reference

> **Version:** 2025-05 | **Last updated:** 2025-05-28
> This document is structured for LLM consumption as a comprehensive reference for all controllable parameters across image and video generation models available on the Poe platform.

---

## Table of Contents

1. [API Architecture Overview](#1-api-architecture-overview)
2. [How to Pass Parameters](#2-how-to-pass-parameters)
3. [Image Generation Parameters](#3-image-generation-parameters)
4. [Video Generation Parameters](#4-video-generation-parameters)
5. [Model-Specific Image Parameters](#5-model-specific-image-parameters)
6. [Model-Specific Video Parameters](#6-model-specific-video-parameters)
7. [Bot Configuration — Parameter Controls System](#7-bot-configuration--parameter-controls-system)
8. [Video Model Compute Points Reference](#8-video-model-compute-points-reference)
9. [Key Findings & Caveats](#9-key-findings--caveats)
10. [Sources](#10-sources)

---

## 1. API Architecture Overview

Poe provides three main API surfaces for accessing image and video generation models:

| API Surface | Base URL / Method | Description |
|---|---|---|
| **OpenAI-Compatible API** | `https://api.poe.com/v1/chat/completions` | Chat Completions format. Primary way to call image/video bots. |
| **OpenAI Responses API** | `https://api.poe.com/v1/responses` | OpenAI Responses format. Also supports image/video bots. |
| **Python SDK (fastapi_poe)** | `pip install fastapi-poe` | Server bot protocol for bot creators; `ProtocolMessage.parameters`. |
| **Bots REST API** | `https://api.poe.com/bots` | Create/manage bots with `api_bot_settings` and `parameter_controls`. |
| **Dedicated Video Endpoint** | `POST https://api.poe.com/v1/videos` | Dedicated video generation endpoint (confirmed from bot API pages). |

### Key Standard Parameters (Chat Completions)

| Parameter | Supported | Notes |
|---|---|---|
| `model` | Yes | Use Poe bot names (e.g., `GPT-Image-2`, `Imagen-4`, `FLUX-pro-1.1`, `Sora-2`) |
| `stream` | Yes | **Use `stream=False` for image/video bots** (strongly recommended) |
| `temperature` | Yes | Between 0 and 2 |
| `max_tokens` | Yes | Fully supported |
| `extra_body` | Yes | **Key mechanism** for passing custom bot-specific parameters |
| `response_format` / `json_schema` | **No** | Structured outputs are NOT supported |

### Rate Limit

- **500 requests per minute** per API key.

### Important

- **No dedicated `/v1/images/generations` endpoint** exists. Image generation goes through Chat Completions with `stream=False`.
- **Private bots are NOT accessible** via the API — only public bots can be queried.

---

## 2. How to Pass Parameters

### 2.1 OpenAI-Compatible API (extra_body)

Custom parameters are passed via the `extra_body` dictionary. This is the primary method for external API consumers.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.poe.com/v1",
    api_key="YOUR_POE_API_KEY"
)

# Image generation with aspect ratio
response = client.chat.completions.create(
    model="Imagen-4",
    messages=[{"role": "user", "content": "A cat in a hat"}],
    stream=False,
    extra_body={"aspect_ratio": "4:3"}
)

# GPT-Image-2 with size
response = client.chat.completions.create(
    model="GPT-Image-2",
    messages=[{"role": "user", "content": "A cat"}],
    stream=False,
    extra_body={"size": "1024x1024"}  # also: "1024x1536", "1536x1024"
)

# Sora-2 video with aspect
response = client.chat.completions.create(
    model="Sora-2",
    messages=[{"role": "user", "content": "Ocean waves"}],
    stream=False,
    extra_body={"aspect": "1280x720"}
)
```

### 2.2 Python SDK (fastapi_poe) — ProtocolMessage.parameters

When using the `fastapi_poe` library, parameters go in the `ProtocolMessage.parameters` field:

```python
import fastapi_poe as fp

message = fp.ProtocolMessage(
    role="user",
    content="A cat in a hat",
    parameters={"aspect_ratio": "4:3"}
)
for partial in fp.get_bot_response_sync(
    messages=[message],
    bot_name="Imagen-4",
    api_key=api_key
):
    print(partial)
```

### 2.3 Poe Client UI (flag-based)

In the Poe web/chat UI, users pass parameters using double-dash flags in the prompt text:

```
--aspect_ratio 9:16
--quality high
--duration 10
```

**WARNING:** These `--flag value` pairs only work in the Poe client UI. They do NOT work when calling the API. For API calls, use `extra_body` or `ProtocolMessage.parameters` instead.

### 2.4 Dedicated Video Endpoint

```python
import requests

response = requests.post(
    "https://api.poe.com/v1/videos",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": "grok-imagine-video",
        "prompt": "Hello world",
        # Additional parameters can be included here
    },
)
print(response.json())
```

---

## 3. Image Generation Parameters

### Universal Parameter Names

The following parameter names are commonly used across Poe's image generation bots. Note that **exact parameter names can differ by bot** — always check the specific bot's documentation.

| Parameter Name | Type | Description | Common Values |
|---|---|---|---|
| `aspect_ratio` | string | Image aspect ratio | `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3` |
| `size` | string | Exact resolution (alternative to aspect_ratio) | `1024x1024`, `1024x1536`, `1536x1024` |
| `quality` | string | Image quality level | `low`, `medium`, `high` |
| `style` | string | Generation style | Varies by bot (e.g., `GENERAL`, `REALISTIC`, `ANIME`) |
| `use_mask` | boolean | Enable masking for inpainting | `true`, `false` |

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

> **Note:** Exact pixel resolutions are typically handled internally by the model. When using `aspect_ratio`, the resolution is computed automatically. When using `size`, you specify exact pixel dimensions (GPT-Image-2 style).

---

## 4. Video Generation Parameters

### Universal Parameter Names

| Parameter Name | Type | Description | Common Values |
|---|---|---|---|
| `aspect_ratio` | string | Video aspect ratio | `16:9`, `9:16`, `1:1`, `4:3`, `3:4` |
| `aspect` | string | Video dimensions (alternative, model-specific) | `1280x720`, `720x1280` |
| `duration` | number/integer | Video length in seconds | `5`, `10`, `9` |
| `resolution` | string | Video resolution | `540p`, `720p`, `768p`, `1080p` |
| `ingredient_mode` | string | Advanced control mode (Pika-specific) | `precise` |
| `quality` | string | Output quality | Varies by model |

### Video Input Modes

Most video bots on Poe support multiple input modes:

| Mode | Description | Input Format |
|---|---|---|
| Text-to-Video (T2V) | Generate video from text prompt | Text only |
| Image-to-Video (I2V) | Animate a still image | Single JPEG/PNG/WEBP attachment |
| Video Editing | Edit/modify an existing video | Single MP4/MOV/WEBM attachment |
| Reference-to-Video | Generate using a reference image | Image attachment + text prompt |

### Video Input Constraints (General)

| Constraint | Limit |
|---|---|
| Image input formats | JPEG, PNG, WEBP |
| Image max size | ~10 MB |
| Image min resolution (auto-upscale) | Below ~300x300 px |
| Image aspect ratio range (auto-crop) | Outside 1:2.5 to 2.5:1 |
| Video input formats | MP4, MOV, WEBM |
| Video auto-trim | Videos longer than ~10s are trimmed |
| Video resolution range (auto-resize) | Outside 720-2160px |
| Video minimum duration | ~3 seconds |

---

## 5. Model-Specific Image Parameters

### 5.1 GPT-Image-2 (OpenAI)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `size` | `1024x1024`, `1024x1536`, `1536x1024` | `1024x1024` | Exact pixel dimensions |
| `aspect_ratio` | `3:2`, `1:1`, `2:3` | `1:1` | Alternative to size |
| `quality` | `low`, `medium`, `high` | Unknown | Quality level |
| `use_mask` | `true` / `false` | `false` | Toggle or type to enable (inpainting) |

### 5.2 Imagen-4-Fast (Google DeepMind)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect_ratio` | `1:1`, `16:9`, `9:16`, `4:3`, `3:4` | Unknown | Auto-determines resolution |
| Non-English input | Auto-translated to English | — | Transparent to user |

### 5.3 FLUX-schnell (Black Forest Labs)

| Parameter | Values | Default |
|---|---|---|
| `aspect_ratio` | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | `1:1` |

### 5.4 FLUX-dev (Black Forest Labs)

| Parameter | Values | Default |
|---|---|---|
| `aspect_ratio` | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | `1:1` |

### 5.5 FLUX-pro-1.1 (Black Forest Labs)

| Parameter | Values | Default |
|---|---|---|
| `aspect_ratio` | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | `1:1` |

### 5.6 FLUX-2-Dev (Black Forest Labs)

| Parameter | Values | Default |
|---|---|---|
| `aspect_ratio` | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | `1:1` |

### 5.7 Flux-Kontext-Max (Black Forest Labs)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect_ratio` | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | Unknown | Image editing focused |

### 5.8 fal (Multiple Models via fal.ai)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect_ratio` | `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | — | Up to 3 images per generation |

---

## 6. Model-Specific Video Parameters

### 6.1 Sora-2 (OpenAI)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect` | e.g., `1280x720` | Model-determined | Passed via `extra_body` |
| Duration | Model-determined | Model-determined | Not user-configurable via API |

### 6.2 Grok-Imagine-Video (xAI)

| Parameter | Values | Notes |
|---|---|---|
| `aspect_ratio` | Configurable | Various options |
| `duration` | Configurable | Video length in seconds |
| `resolution` | Configurable | Video resolution |
| Input modes | T2V, I2V, Video Editing | Single image or video attachment |

```python
import requests

response = requests.post(
    "https://api.poe.com/v1/videos",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": "grok-imagine-video",
        "prompt": "Hello world",
    },
)
```

### 6.3 Kling-O3 (Kuaishou)

| Parameter | Values/Details | Notes |
|---|---|---|
| Mode | Standard, Pro | Affects resolution and quality |
| `aspect_ratio` | Varies by mode | Resolution varies by aspect ratio |
| Duration | Configurable | Seconds |
| Resolution | Varies by aspect ratio | Determined by mode + ratio |
| Multi-scene | Separate scenes with `\|` in prompt | Max 6 scenes |
| Per-scene duration | e.g., `5s: Scene one \| 3s: Scene two` | Time-prefixed syntax |
| Native sound | Supported | Audio output included |
| Prompt limits | 3–2,500 characters | Text length constraint |

**Input constraints:**
- Image inputs: JPEG, PNG, WEBP; max 10 MB; auto-upscaled below 300x300; auto-cropped outside 1:2.5–2.5:1
- Video inputs: MP4, MOV, WEBM; auto-trimmed >10s; auto-resized outside 720–2160px; min 3s
- Video edit duration: Capped at 10 seconds when video input is used

### 6.4 Kling-v3-Motion-Ctrl (Kuaishou)

| Parameter | Values/Details | Notes |
|---|---|---|
| `aspect_ratio` | Configurable | Various options |
| Duration | Configurable | Seconds |
| Resolution | Configurable | Depends on aspect ratio |
| Motion control | Configurable | Optional parameters for motion customization |

### 6.5 Pika 2.0 / 2.1 / 2.2

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect_ratio` | Various | Varies | Available on v2.1+ |
| `duration` | 5 seconds | 5s | Fixed duration |
| Resolution | 720p | 720p | Fixed resolution |
| `ingredient_mode` | `precise` | — | Advanced control mode |

### 6.6 Runway Gen-4 Turbo

| Parameter | Values | Default | Notes |
|---|---|---|---|
| Duration | 5s, 10s | — | Two duration options |
| Resolution | Configurable | — | Various options |

### 6.7 Ray 2

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `resolution` | `540p`, `720p`, `1080p` | — | Three quality tiers |
| `aspect_ratio` | Various (e.g., `16:9`) | — | Configurable |
| `duration` | 5s, 9s | — | Two duration options |

### 6.8 VEO-2 (Google DeepMind)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect_ratio` | Configurable | — | Various options |
| Duration | Configurable | — | Variable |
| Resolution | Configurable | — | High quality |
| Compute cost | ~92,000 points | — | Most expensive video model |

### 6.9 Dream Machine (Luma AI)

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `aspect_ratio` | `16:9` | `16:9` | Primary landscape format |
| Duration | ~5s | ~5s | Fixed duration |
| Compute cost | ~12,000 points | — | Moderate cost |

### 6.10 Hailuo AI

| Parameter | Values | Default | Notes |
|---|---|---|---|
| Duration | 6s | 6s | Fixed duration |
| Resolution | 768p | 768p | Fixed resolution |
| Compute cost | ~14,000 points | — | Moderate cost |

### 6.11 Hailuo Live

| Parameter | Values | Default | Notes |
|---|---|---|---|
| Duration | Per-clip | — | Variable per generation |
| Compute cost | ~14,167 points | — | Per clip |

---

## 7. Bot Configuration — Parameter Controls System

Poe's **Parameter Controls** system allows server bot creators to add custom UI elements (dropdowns, sliders, toggles) to their bot's interface. These UI elements let users configure generation parameters visually without needing to type flags.

### 7.1 JSON Structure

```json
{
  "api_version": "2",
  "sections": [
    {
      "name": "Generation",
      "collapsed_by_default": false,
      "controls": [
        {
          "control": "drop_down",
          "label": "Style",
          "parameter_name": "style",
          "default_value": "GENERAL",
          "options": [
            {"name": "General", "value": "GENERAL"},
            {"name": "Realistic", "value": "REALISTIC"},
            {"name": "Design", "value": "DESIGN"},
            {"name": "3D render", "value": "RENDER_3D"},
            {"name": "Anime", "value": "ANIME"}
          ]
        },
        {
          "control": "drop_down",
          "label": "Aspect ratio",
          "parameter_name": "aspect",
          "default_value": "1:1",
          "options": [
            {"name": "16:9 (Horizontal)", "value": "16:9"},
            {"name": "16:10", "value": "16:10"},
            {"name": "3:2", "value": "3:2"},
            {"name": "4:3", "value": "4:3"},
            {"name": "1:1 (Square)", "value": "1:1"},
            {"name": "9:16 (Vertical)", "value": "9:16"},
            {"name": "10:16", "value": "10:16"},
            {"name": "2:3", "value": "2:3"},
            {"name": "3:4", "value": "3:4"}
          ]
        },
        {
          "control": "slider",
          "label": "Duration (seconds)",
          "parameter_name": "duration",
          "default_value": 5,
          "min_value": 1,
          "max_value": 10,
          "step": 1
        },
        {
          "control": "toggle",
          "label": "Use reference mask",
          "parameter_name": "use_mask",
          "default_value": false
        }
      ]
    }
  ]
}
```

### 7.2 Control Types

| Control Type | UI Element | Use Case | Config Properties |
|---|---|---|---|
| `drop_down` | Dropdown menu | Aspect ratio, style, quality | `options` array |
| `slider` | Range slider | Duration, numeric values | `min_value`, `max_value`, `step` |
| `toggle` | Boolean switch | Enable/disable features | `default_value` (bool) |

### 7.3 How Parameter Values Flow

When a user sends a message with parameter controls configured, the selected values arrive in the bot's request:

**For Server Bots (fastapi_poe):**
```python
# Values available in:
request.query[-1].parameters
# Returns a dict like: {"style": "REALISTIC", "aspect": "16:9", "duration": 5}
```

**For API Bots (External Endpoint Proxies):**
Parameters defined in `api_bot_settings.param_definitions` are forwarded as `extra_body` to the upstream API endpoint:

```json
{
  "api_bot_settings": {
    "param_definitions": [
      {
        "param_name": "aspect_ratio",
        "param_dest": "extra_body",
        "default_value": "1:1"
      },
      {
        "param_name": "duration",
        "param_dest": "extra_body",
        "default_value": 5
      }
    ]
  }
}
```

### 7.4 Recommended Bot Settings for Media Bots

| Setting | Recommended Value | Purpose |
|---|---|---|
| `allow_attachments` | `True` | Enable image/video input for I2V, video editing |
| `expand_text_attachments` | `True` | Parse text from attached files |
| `enable_image_comprehension` | `True` | Vision-based understanding of input images |
| `stream` | `False` | Optimal for media generation (no partial chunks) |

---

## 8. Video Model Compute Points Reference

> Approximate compute point costs on Poe (August 2025 reference). Actual costs may vary.

| Model | Compute Points | Duration | Resolution | Notes |
|---|---|---|---|---|
| Pika Turbo | ~5,000 | 5s | 720p | Cheapest video option |
| Pika v2.1/2.2 | ~5,834 | 5s | 720p | |
| Pika v2.2 + Ingredients | ~7,084 | 5s | 720p | Higher with ingredient mode |
| Dream Machine | ~12,000 | ~5s | Variable | Moderate cost |
| Ray 2 (540p) | ~6,000 | 5s | 540p | Low quality tier |
| Ray 2 (720p) | ~11,750 | 5s | 720p | Medium quality tier |
| Ray 2 (1080p) | ~26,250 | 5s | 1080p | High quality tier |
| Kling Pro v1.5 | ~12,670 | ~5s | Variable | ~2,534 pts/sec |
| Kling 2.0 Master | ~30,000 | ~5s | Variable | ~6,000 pts/sec |
| Hailuo AI | ~14,000 | 6s | 768p | |
| Hailuo Live | ~14,167 | Per clip | Variable | |
| Runway Gen-4 Turbo | ~21,334 | 10s | Variable | |
| VEO-2 | ~92,000 | Variable | Variable | Most expensive; highest quality |

---

## 9. Key Findings & Caveats

1. **No dedicated Images API endpoint.** Poe does NOT have a `/v1/images/generations` endpoint like OpenAI does. All image generation goes through the Chat Completions API with `stream=False`.

2. **Dedicated Video endpoint exists.** `POST https://api.poe.com/v1/videos` is available for video generation.

3. **`extra_body` is the key mechanism** for passing custom parameters via the OpenAI-compatible API. The exact parameter names depend on the specific bot.

4. **`stream=False` is strongly recommended** for image/video bots for optimal performance and reliability.

5. **Parameter names differ between UI and API.** In the Poe client UI, use `--aspect_ratio 9:16` text flags. In the API, use `extra_body={"aspect_ratio": "4:3"}` or `ProtocolMessage.parameters`. Do NOT mix these approaches.

6. **Parameter names are NOT standardized across bots.** `GPT-Image-2` uses `size`, while `Imagen-4` and FLUX models use `aspect_ratio`. `Sora-2` uses `aspect`. Always check the specific bot's documentation.

7. **Structured outputs are NOT supported.** The `response_format` and `json_schema` options from OpenAI's API are not available on Poe.

8. **Private bots are NOT accessible via API.** Only public bots can be queried through the API.

9. **Resolution is usually auto-determined by aspect ratio** for most models (except GPT-Image-2 which accepts explicit `size` strings).

10. **Video duration ranges are limited.** Most video models offer only 2-3 discrete duration options (e.g., 5s vs 10s), not arbitrary durations.

11. **The `parameters` field on `ProtocolMessage`** is the authoritative way to pass custom parameters via the Python SDK (fastapi_poe) when building server bots.

---

## 10. Sources

| # | URL | Type |
|---|---|---|
| 1 | https://creator.poe.com/docs/external-applications/openai-compatible-api | Official Documentation |
| 2 | https://creator.poe.com/docs/external-applications/external-application-guide | Official Documentation |
| 3 | https://creator.poe.com/docs/server-bots/server-bots-functional-guides | Official Documentation |
| 4 | https://creator.poe.com/docs/server-bots/parameter-controls | Official Documentation |
| 5 | https://creator.poe.com/docs/api-bots/overview | Official Documentation |
| 6 | https://creator.poe.com/api-reference/getBot | API Reference |
| 7 | https://creator.poe.com/api-reference/updateBot | API Reference |
| 8 | https://poe-for-creators.readme.io/docs/adding-parameter-controls-to-your-bots | Official Documentation |
| 9 | https://poe-for-creators.readme.io/docs/poe-protocol-specification | Protocol Specification |
| 10 | https://poe.com/blog/introducing-the-poe-api | Blog Post |
| 11 | https://poe.com/GPT-Image-2 | Bot Page |
| 12 | https://poe.com/Imagen-4-Fast | Bot Page |
| 13 | https://poe.com/flux-dev | Bot Page |
| 14 | https://poe.com/flux-schnell | Bot Page |
| 15 | https://poe.com/FLUX-2-Dev | Bot Page |
| 16 | https://poe.com/Flux-Kontext-Max | Bot Page |
| 17 | https://poe.com/Grok-Imagine-Video/api | Bot API Page |
| 18 | https://poe.com/Kling-O3 | Bot Page |
| 19 | https://poe.com/Kling-v3-Motion-Ctrl | Bot Page |
| 20 | https://poe.com/fal | Bot Page |
| 21 | https://carletontorpin.com/ai/best-ai-video-generators-in-poe-ai | Blog / Research |
| 22 | https://docs.litellm.ai/docs/providers/poe | Third-Party Documentation |
| 23 | https://github.com/poe-platform/server-bot-quick-start | GitHub Repository |
