# VidForge

AI-powered video generation platform for social media using local AI models.

## Features

- **Music Video Generation** - Create videos from audio with AI-generated visuals
- **Scene-Based Planning** - Automatic scene planning from lyrics with visual descriptions
- **Image Generation** - Seed image generation using FLUX.1-schnell or SDXL
- **Video Generation** - Per-scene video generation using Wan2.2 or LTX
- **Model Preferences** - User-configurable AI models via Settings page
- **Template System** - Extensible video generation pipelines

## Supported Models

### Image Generation
- FLUX.1-schnell (default, local ComfyUI)
- Stable Diffusion XL (local ComfyUI)
- GPT-Image-1 (Poe cloud)

### Video Generation
- Wan 2.2 T2V (default, local ComfyUI)
- LTX 2.3 T2V (local ComfyUI, requires `VIDFORGE_DOWNLOAD_LTX=true`)
- Veo-3.1 (Poe cloud)

### Text Generation
- Qwen 3.6 (default, local Ollama)
- Llama 3.3 (local Ollama)
- Various Ollama models

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) AMD GPU with ROCm support for ComfyUI

### Development Setup

1. Clone the repository

```bash
cd vidforge
```

2. Copy environment files

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

3. Start services

```bash
cd docker
docker-compose up -d
```

4. Run database migrations

```bash
docker exec -it docker-backend-1 alembic upgrade head
```

5. Create your first admin user

```bash
docker exec -it docker-backend-1 python -m app.cli createsuperuser
```

6. Access the application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8001
- API Docs: http://localhost:8001/docs

Login with the admin user you created in step 5.

### Model Downloads

ComfyUI automatically downloads models on first start:
- FLUX.1-schnell FP8 (~17GB) - default image model
- Wan2.2 (~10GB) - default video model
- Optional: LTX 2.3 (~43GB) - set `VIDFORGE_DOWNLOAD_LTX=true`

### Without Docker

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.cli createsuperuser
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

#### Worker

```bash
cd backend
celery -A app.workers worker --loglevel=info
```

## Usage

### Creating a Music Video

1. Go to the Jobs page and create a new job
2. Select "Music Video (Scene-Based)" template
3. Upload an audio file or provide lyrics
4. Choose visual style (cinematic, anime, etc.)
5. Generate scene plan from lyrics
6. Review and modify scene prompts
7. Generate seed images for each scene
8. Generate videos for each scene
9. Render final merged video

### Configuring AI Models

1. Go to Settings > AI Models
2. Select preferred models for each modality:
   - Image Generation
   - Video Generation
   - Text Generation
3. Settings are saved per-user and applied to all jobs

## Project Structure

```
vidforge/
├── frontend/           # React + TypeScript application
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── api/        # REST endpoints
│   │   ├── models/     # Database models
│   │   ├── services/   # Business logic
│   │   ├── workers/    # Celery tasks
│   │   └── storage/    # Storage backends
│   ├── templates/      # Video templates (YAML)
│   └── styles/         # Style presets (YAML)
├── docker/             # Docker configurations
└── docs/               # Documentation
```

## Environment Variables

### Backend (.env)

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/vidforge
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
COMFYUI_URL=http://comfyui:8188
OLLAMA_URL=http://ollama:11434
STORAGE_BACKEND=local
# Optional: Download LTX model
VIDFORGE_DOWNLOAD_LTX=true
```

### Frontend (.env)

```
VITE_API_URL=http://localhost:8001
VITE_WS_URL=ws://localhost:8001
```

## Testing

### Backend Tests

```bash
cd backend
pytest
```

### Frontend Tests

```bash
cd frontend
npm run test
```

## License

MIT