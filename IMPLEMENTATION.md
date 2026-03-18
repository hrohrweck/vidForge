# VidForge - Implementation Plan

A web application for automated social media video generation using local AI models, targeting AMD R9 AI HX470 hardware (Radeon 890M iGPU, 128GB RAM).

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Frontend** | React + TypeScript + Vite | Modern SPA, good DX |
| **Backend** | FastAPI (Python) | Async support, easy AI integration |
| **Video Model** | Wan2.2 (via ComfyUI) | Official AMD ROCm support, audio-driven generation (S2V) |
| **LLM** | Ollama or lemonade-server | Both work with ROCm |
| **Audio** | AudioCraft/MusicGen | Open-source, works on CPU |
| **Database** | PostgreSQL + Redis | Jobs queue, user data |
| **Storage** | Abstract backend (Local/S3/SSH) | Configurable multi-backend |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ Dashboard│ │ Templates│ │ Jobs View│ │ Settings/Users   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST API / WebSocket
┌───────────────────────────▼─────────────────────────────────────┐
│                     BACKEND (FastAPI)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │Auth API  │ │ Jobs API │ │Templates │ │ Storage/Settings │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     WORKER LAYER (Celery)                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐    │
│  │ Script Gen   │ │ Video Gen    │ │ Audio Gen / Merge    │    │
│  │ (LLM)        │ │ (ComfyUI)    │ │ (MusicGen/FFmpeg)    │    │
│  └──────────────┘ └──────────────┘ └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     INFRASTRUCTURE                              │
│  ┌────────┐ ┌────────┐ ┌────────────┐ ┌────────────────────┐   │
│  │PostgreSQL│ │ Redis  │ │ ComfyUI    │ │ Storage Backends   │   │
│  │         │ │(Queue) │ │ (Wan2.2)   │ │ Local/S3/SSH       │   │
│  └────────┘ └────────┘ └────────────┘ └────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
vidforge/
├── frontend/                 # React + Vite
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── stores/          # Zustand state
│   │   └── api/             # API client
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/             # REST endpoints
│   │   ├── models/          # SQLAlchemy models
│   │   ├── services/        # Business logic
│   │   ├── workers/         # Celery tasks
│   │   └── storage/         # Storage backends
│   ├── templates/           # Video templates
│   └── styles/              # Style presets
├── comfyui/                  # ComfyUI custom nodes/workflows
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── Dockerfile.worker
│   └── docker-compose.yml
├── docs/
└── scripts/
```

## Phase Overview

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Foundation | Week 1-2 | Project skeleton, auth, basic API |
| 2. Job System | Week 3-4 | Queue, storage backends, model manager |
| 3. Templates | Week 5-7 | Template engine, styles, revid.ai parser |
| 4. AI Integration | Week 8-10 | ComfyUI/Wan2.2, LLM, AudioGen |
| 5. Polish | Week 11-12 | UI refinements, docs, deployment |

## Docker Architecture

```yaml
# docker-compose.yml (conceptual)
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
  
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
  
  worker:
    build: ./backend
    command: celery -A app.workers worker
    depends_on: [backend, redis]
  
  comfyui:
    image: comfyanonymous/comfyui:latest-rocm
    ports: ["8188:8188"]
    volumes: ["models:/app/models", "output:/app/output"]
    devices: ["/dev/kfd", "/dev/dri"]
  
  postgres:
    image: postgres:16
  
  redis:
    image: redis:7
```

## Job Queue Flow (FIFO)

```
┌─────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐
│ Submit  │───▶│ Pending │───▶│Processing│───▶│Complete │
└─────────┘    └─────────┘    └──────────┘    └─────────┘
                    │               │
                    │               ▼
                    │         ┌──────────┐
                    └────────▶│  Failed  │
                              └──────────┘

FIFO Processing:
[Job1] → [Job2] → [Job3] → ...
  ↓
Wait for completion before next
```

## Preview Strategy

| Render Type | Preview |
|-------------|---------|
| Full render | Low-res preview generated first (480p, 15fps) |
| Test/preview mode | Direct low-res output |
| Final render | Full resolution, no separate preview |

## Database Schema

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP
);

-- Jobs
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    template_id UUID REFERENCES templates(id),
    status VARCHAR DEFAULT 'pending',
    progress INT DEFAULT 0,
    input_data JSONB,
    output_path VARCHAR,
    preview_path VARCHAR,
    error_message TEXT,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Templates
CREATE TABLE templates (
    id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    description TEXT,
    config YAMLTEXT,
    is_builtin BOOLEAN DEFAULT false,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP
);

-- Styles
CREATE TABLE styles (
    id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    category VARCHAR,
    params JSONB,
    created_at TIMESTAMP
);

-- Settings
CREATE TABLE settings (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    default_style_id UUID REFERENCES styles(id),
    storage_backend VARCHAR DEFAULT 'local',
    storage_config JSONB,
    preferences JSONB
);
```

## API Endpoints

```
Auth:
  POST   /api/auth/register
  POST   /api/auth/login
  POST   /api/auth/refresh
  GET    /api/auth/me

Jobs:
  GET    /api/jobs
  POST   /api/jobs
  GET    /api/jobs/{id}
  DELETE /api/jobs/{id}
  GET    /api/jobs/{id}/preview
  GET    /api/jobs/{id}/download
  WS     /api/jobs/{id}/ws

Templates:
  GET    /api/templates
  POST   /api/templates
  GET    /api/templates/{id}
  PUT    /api/templates/{id}
  DELETE /api/templates/{id}

Styles:
  GET    /api/styles
  POST   /api/styles
  GET    /api/styles/{id}
  PUT    /api/styles/{id}

Storage:
  GET    /api/storage/config
  PUT    /api/storage/config
  GET    /api/storage/files
  DELETE /api/storage/files/{path}
```

## Template System

### Template Definition

```yaml
# templates/music_video.yaml
name: "Music Video"
description: "Create video from music file"
inputs:
  - name: audio_file
    type: file
    accept: [".mp3", ".wav"]
  - name: style
    type: select
    options: [realistic, anime, manga]
  - name: duration
    type: number
    default: 30
    min: 5
    max: 300
pipeline:
  - step: analyze_audio
    model: audio_analyzer
  - step: generate_scenes
    model: llm
  - step: generate_video
    model: wan2.2_s2v
    params:
      audio_driven: true
  - step: merge_audio
    tool: ffmpeg
```

### Style Presets

```yaml
# styles/realistic.yaml
name: "Realistic"
category: video
params:
  guidance_scale: 7.5
  num_inference_steps: 50
  fps: 24
  prompt_prefix: "photorealistic, 4k, detailed"
  negative_prompt: "anime, cartoon, illustration"

# styles/anime.yaml
name: "Anime"
category: video
params:
  guidance_scale: 8.0
  num_inference_steps: 40
  fps: 24
  prompt_prefix: "anime style, vibrant colors, clean lines"
  negative_prompt: "photorealistic, realistic, photograph"

# styles/manga.yaml
name: "Manga"
category: video
params:
  guidance_scale: 8.0
  num_inference_steps: 40
  fps: 24
  prompt_prefix: "manga style, black and white, ink drawing"
  negative_prompt: "color, photorealistic"
```

### revid.ai Annotation Parser

Scripts support bracketed annotations for visual directives:

```
This is narration text. [Show a sunset over mountains] 
More narration here. [Camera zooms into forest]
```

Parser extracts:
- Narration segments for TTS
- Visual annotations for scene generation
- Timing information from audio analysis

## Dependencies

### Backend (requirements.txt)
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.0
alembic>=1.13.0
asyncpg>=0.29.0
celery>=5.3.0
redis>=5.0.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6
boto3>=1.34.0
paramiko>=3.4.0
httpx>=0.26.0
websockets>=12.0
pyyaml>=6.0.1
ffmpeg-python>=0.2.0
pydub>=0.25.1
librosa>=0.10.1
```

### Frontend (package.json)
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.0",
    "zustand": "^4.4.0",
    "@tanstack/react-query": "^5.17.0",
    "axios": "^1.6.0",
    "socket.io-client": "^4.6.0",
    "tailwindcss": "^3.4.0",
    "@radix-ui/react-*": "latest",
    "lucide-react": "^0.303.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "@types/react": "^18.2.0",
    "eslint": "^8.56.0",
    "prettier": "^3.2.0"
  }
}
```

## Memory Management

```python
class ModelOrchestrator:
    def __init__(self, max_memory_gb: float = 100):
        self.loaded_models = {}
        self.max_memory = max_memory_gb
    
    async def load_model(self, model_id: str):
        if self.current_usage + model.size > self.max_memory:
            await self.unload_lru()
        # Load model...
    
    async def unload_lru(self):
        # Unload least recently used model
        pass
```

## Long Video Handling

```python
async def generate_long_video(duration: int, max_segment: int = 10):
    segments = []
    for i in range(0, duration, max_segment):
        segment_duration = min(max_segment, duration - i)
        segment = await generate_segment(
            start_time=i,
            duration=segment_duration
        )
        segments.append(segment)
    return await merge_videos(segments)
```

## Implementation Priority

1. **Week 1-2**: Docker setup + Backend auth + Frontend skeleton
2. **Week 3-4**: Job queue + Redis + Storage backends
3. **Week 5**: Template system + revid.ai parser
4. **Week 6**: Style presets + preview generation
5. **Week 7**: Frontend template/style editors
6. **Week 8**: ComfyUI integration (Wan2.2)
7. **Week 9**: LLM integration (script generation)
8. **Week 10**: Audio generation (MusicGen)
9. **Week 11**: Long video splitting + merging
10. **Week 12**: Documentation + deployment
