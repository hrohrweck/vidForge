# AGENTS.md

This file provides guidance for AI agents working on the VidForge project.

## Project Overview

VidForge is a web application for automated social media video generation using local AI models. It targets AMD R9 AI HX470 hardware with Radeon 890M iGPU and 128GB RAM.

## Development Guidelines

- **Keep documentation current**: After any architectural change, new feature, or significant refactoring, update the relevant documentation in `docs/`. If a pattern introduced in your changes is reusable (e.g., a new provider interface, a sync function, a normalization utility), document it so future agents can follow the same pattern.

## Technology Stack

- **Frontend**: React + TypeScript + Vite
- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 16
- **Queue**: Redis + Celery (prefork pool, shared WorkerContext)
- **Video Generation**: ComfyUI with Wan2.2 model (848×480, 30 steps, 16fps)
- **Image Generation**: ComfyUI with Flux.1-schnell; Poe (GPT-Image, Wan 2.7 Image)
- **Audio Generation**: AudioCraft/MusicGen (CPU container)
- **TTS**: edge-tts for narration
- **LLM**: Ollama (Qwen 3.6, Llama 3.3) or Poe (GLM 5.1)
- **Providers**: comfyui_direct, runpod, poe, atlascloud, ollama (capability-based, extensible via registry)

## Code Style

### Python
- Use Python 3.11+ features (type hints, async/await)
- Follow PEP 8 with line length of 100 characters
- Use Pydantic v2 for data validation
- Use async database operations with asyncpg
- Organize imports: stdlib → third-party → local

### TypeScript/React
- Use functional components with hooks
- Use Zustand for state management
- Use React Query for server state
- Follow ESLint and Prettier configurations

## Commands

### Backend
```bash
# Install dependencies
cd backend && pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Run Celery worker
python -m celery -A app.workers worker --loglevel=info

# Run tests (unit only — default)
pytest

# Run integration tests (requires running PostgreSQL)
pytest -m integration

# Linting
ruff check app/ plugins/

# Format
ruff format app/ plugins/
```

### Frontend
```bash
# Install dependencies
cd frontend && npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run unit tests (vitest)
npx vitest run

# Run E2E tests (playwright)
npx playwright test

# Type checking
npx tsc --noEmit

# Linting
npm run lint
```

### Docker
```bash
# Start all services
cd docker && docker compose up -d

# Rebuild and restart containers
docker compose up -d --build

# View logs
docker compose logs -f backend

# Run backend command
docker compose exec backend alembic upgrade head
```

### Shortcuts
```bash
# From project root — quick dev startup
make dev          # or: scripts/dev.sh

# Run all linters + tests
make check
```

## Project Structure

```
vidforge/
├── frontend/           # React application
│   ├── src/
│   │   ├── api/        # API client and types
│   │   ├── components/ # React components
│   │   ├── pages/      # Page components
│   │   │   └── editor/ # Plugin-specific editor panels
│   │   ├── hooks/      # Custom hooks
│   │   └── stores/     # Zustand stores
│   ├── e2e/            # Playwright E2E tests
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/        # FastAPI routers
│   │   ├── comfyui/    # ComfyUI workflow JSON files
│   │   ├── database.py # SQLAlchemy models + engine
│   │   ├── plugins/    # Plugin registry and base class
│   │   │   ├── base.py    # PluginBase ABC
│   │   │   └── registry.py
│   │   ├── services/  # Business logic
│   │   │   ├── media_generator.py  # Image/video generation
│   │   │   ├── video_processor.py  # FFmpeg operations
│   │   │   ├── llm_service.py      # LLM client
│   │   │   ├── model_config.py     # Model preferences
│   │   │   └── providers/          # AI provider implementations (capability interfaces + registry)
│   │   ├── workers/    # Celery tasks + context
│   │   └── storage/    # Storage backends (local, S3, SSH)
│   ├── plugins/        # Template plugin packages
│   │   ├── music_video/
│   │   ├── prompt_to_video/
│   │   └── script_to_video/
│   ├── tests/          # Unit and integration tests
│   └── requirements.txt
├── docker/             # Docker configurations
│   ├── audiocraft/     # MusicGen container
│   ├── nginx/         # Reverse proxy config
│   └── docker-compose.yml
├── docs/               # Documentation
│   ├── CELERY_REFACTOR.md
│   ├── DEPLOYMENT.md
│   ├── PLUGIN_ARCHITECTURE.md
│   ├── WRITING_PLUGINS.md
│   └── WRITING_PROVIDERS.md
└── scripts/            # Utility scripts
```

## Key Patterns

### Plugin Pattern
Every template type is a plugin in `backend/plugins/`. Plugins extend
`PluginBase` (in `app/plugins/base.py`) and implement pipeline stages:

```python
class PluginBase(ABC):
    async def enrich_inputs(self, db, job, context) -> dict: ...
    async def plan_scenes(self, db, job, context) -> dict: ...
    async def generate_images(self, db, job, scenes, context) -> dict: ...
    async def generate_videos(self, db, job, scenes, context) -> dict: ...
    async def render(self, db, job, scenes, context) -> dict: ...
```

Sensible defaults are provided — plugins only need to implement
`plan_scenes()` and `get_template_definition()`. See
[docs/WRITING_PLUGINS.md](docs/WRITING_PLUGINS.md).

### Celery Task Pattern
All tasks use `ctx.run()` to execute async code on the shared WorkerContext:

```python
@celery_app.task(bind=True, time_limit=TASK_TIME_LIMIT)
def my_task(self, job_id: str):
    return ctx.run(_my_task(job_id))

async def _my_task(job_id: str):
    async with ctx.session_factory() as db:
        ...  # use shared engine/redis
```

Never use `asyncio.run()` in tasks. See [docs/CELERY_REFACTOR.md](docs/CELERY_REFACTOR.md).

### Provider Pattern
AI providers extend `ProviderBase` and implement capability interfaces
(`ImageProvider`, `VideoProvider`, `LLMProvider`) in
`app/services/providers/`:

```python
from app.services.model_capabilities import ModelCapability

class YourProvider(ProviderBase, ImageProvider, VideoProvider):
    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_image=True, supports_video=True,
            capabilities=[ModelCapability.TEXT_TO_IMAGE, ModelCapability.IMAGE_TO_IMAGE]
        )

    async def generate_image(
        self, prompt: str, model: str, aspect_ratio: str, **kwargs
    ) -> tuple[str, bytes]:
        # Read optional reference image for img2img
        image_path: str | None = kwargs.get("image_path")
        reference_strength: float = kwargs.get("reference_image_strength", 0.75)
        ...
        return (model_id, image_bytes)

    async def generate_video(
        self, prompt: str, model: str, duration: int,
        aspect_ratio: str, **kwargs
    ) -> tuple[str, bytes]:
        # Read optional reference image for I2V
        reference_image_path: str | None = kwargs.get("reference_image_path")
        ...
        return (model_id, video_bytes)
```

Providers register themselves through the `ProviderRegistry`:

```python
from app.services.providers import registry

registry.register("your_type", YourProvider)
```

See [docs/WRITING_PROVIDERS.md](docs/WRITING_PROVIDERS.md).

### Model Capability System

Models have structured capability metadata stored in `ModelConfig.capabilities`
(JSONB). See `app/services/model_capabilities.py` for the enum and utilities:

```python
from app.services.model_capabilities import (
    ModelCapability, GenerationType,
    build_model_capabilities_context, normalize_capabilities
)

# Capability enums
class ModelCapability(str, Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_TO_VIDEO = "image_to_video"
    FRAME_TO_VIDEO = "frame_to_video"
    MULTI_REF_TO_VIDEO = "multi_ref_to_video"
    TEXT_TO_VIDEO = "text_to_video"
    ...

# Generate planner context from model configs
context = build_model_capabilities_context(
    video_model_config=video_config_dict,
    image_model_config=image_config_dict
)
```

Filter models by capability: `GET /api/models?capability=accepts_image`

Newly synced models default to `is_active=False` — admin must explicitly enable
them on the `/admin/models` page.

### Storage Backend Pattern
```python
class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, path: str, data: bytes) -> str: ...
    @abstractmethod
    async def download(self, path: str) -> bytes: ...
    @abstractmethod
    async def delete(self, path: str) -> None: ...
    @abstractmethod
    async def list_files(self, prefix: str) -> list[str]: ...
```

## Video Generation Pipeline

### Scene Constraints
- **Minimum scene duration**: 2 seconds
- **Maximum scene duration**: 15 seconds (enforced by planner prompts)
- **Per-clip max**: ~5 seconds (Wan 2.2 hardware limit)

### Sub-Clip Chaining
Scenes longer than 5s are automatically decomposed:
1. Split into N 5s sub-clips
2. LLM generates evolving prompts for each sub-clip
3. Sub-clip 1 uses the image model's seed image
4. Sub-clips 2+ use the ~80% frame of the previous clip as I2V seed
5. Merged with 0.3s crossfade transitions

### Retry Behavior
All `generate_image` and `generate_video` calls retry up to 4 times with
exponential backoff (10s → 20s → 40s → 80s) on recoverable errors:
- Engine overloaded, capacity, queue full
- Rate limiting (429), server errors (502, 503)
- Timeouts, connection failures, empty responses

Non-recoverable errors (invalid prompts, auth failures) fail immediately.
After retries exhausted, the scene is marked `failed` and the pipeline
continues to the next scene.

## Environment Variables

### Backend (.env)
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/vidforge
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
COMFYUI_URL=http://comfyui:8188
OLLAMA_URL=http://ollama:11434
AUDIOCRAFT_URL=http://audiocraft:5000
STORAGE_BACKEND=local|s3|ssh
# S3 config (if STORAGE_BACKEND=s3)
S3_ENDPOINT=...
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BUCKET=...
# SSH config (if STORAGE_BACKEND=ssh)
SSH_HOST=...
SSH_USER=...
SSH_KEY_PATH=...
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## Common Tasks

### Adding a New Template Plugin
1. Create plugin package in `backend/plugins/my_template/`
2. Implement `MyTemplatePlugin(PluginBase)` with `plugin_id`, `display_name`, `get_template_definition()`, `plan_scenes()`
3. Add `create_plugin()` to `__init__.py`
4. (Optional) Add frontend panel in `frontend/src/pages/editor/`
5. Restart backend — plugin is auto-discovered
6. Test end-to-end: create job → plan scenes → generate media → export
See [docs/WRITING_PLUGINS.md](docs/WRITING_PLUGINS.md) for full guide.

### Adding a New AI Provider
1. Create provider class in `backend/app/services/providers/your_provider.py`
2. Extend `ProviderBase`, implement the appropriate capability interfaces (`ImageProvider`, `VideoProvider`, `LLMProvider`)
3. Register in `providers/__init__.py` using `registry.register("your_type", YourProvider)`
4. Add provider via Admin UI, configure models
5. Test by selecting your model in Settings → AI Models
See [docs/WRITING_PROVIDERS.md](docs/WRITING_PROVIDERS.md) for full guide.

### Adding a New Storage Backend
1. Create new class in `backend/app/storage/` extending `StorageBackend`
2. Register in storage factory
3. Add configuration schema to settings
4. Update frontend settings page
5. Write unit tests (upload, download, delete, list operations)

### Adding a New API Endpoint
1. Create or update router in `backend/app/api/`
2. Define Pydantic schemas for request/response
3. Implement service logic
4. Write tests for business logic or complex validation
5. Test authentication/authorization requirements

### Adding a New Frontend Page
1. Create component in `frontend/src/pages/`
2. Add route in router configuration (`App.tsx`)
3. Add navigation item if needed
4. Implement API integration with React Query
5. Write component tests for complex interactions

## Testing

### Testing Philosophy
- **Write tests for new features when they add value**, not just for the sake of coverage
- Focus on testing business logic, API endpoints, and critical user flows
- Avoid testing trivial code (simple getters/setters, pure configuration)
- Mock external dependencies (ComfyUI, Ollama, storage backends) to ensure fast, reliable tests

### When to Write Tests

**Write tests for:**
- API endpoints (request/response validation, authentication, authorization)
- Business logic in services (video generation pipeline, script parsing, audio analysis)
- Complex data transformations (template processing, style merging)
- Error handling and edge cases
- Database operations (CRUD, constraints, relationships)
- Integration points (WebSocket connections, Celery tasks)

**Skip tests for:**
- Simple CRUD endpoints with no business logic
- Configuration classes and settings
- Pure data models without methods
- One-time scripts or CLI tools
- Code that's likely to change frequently during prototyping

### Backend Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_jobs_api.py

# Run integration tests only
pytest tests/integration/

# Run with verbose output
pytest -v
```

**Test Structure:**
```
backend/tests/
├── unit/                    # Fast, isolated tests
│   ├── test_services.py     # Service layer tests
│   ├── test_api/            # API endpoint tests
│   │   ├── test_auth.py
│   │   ├── test_jobs.py
│   │   └── test_templates.py
│   └── test_storage.py      # Storage backend tests
├── integration/             # Database/API integration tests
│   ├── test_job_flow.py     # Full job processing flow
│   └── test_websocket.py    # WebSocket integration
└── conftest.py              # Shared fixtures
```

**Example Test:**
```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_create_job_requires_auth():
    """Test that job creation requires authentication."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/jobs", json={"template_id": "..."})
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_batch_job_creates_multiple_jobs(authenticated_client):
    """Test batch job creation."""
    response = await authenticated_client.post(
        "/api/jobs/batch",
        json={
            "template_id": "...",
            "jobs": [{"prompt": "test1"}, {"prompt": "test2"}],
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created_count"] == 2
    assert len(data["job_ids"]) == 2
```

### Frontend Tests
```bash
# Run component tests
npm run test

# Run E2E tests
npx playwright test

# Run tests in watch mode
npm run test -- --watch

# Generate coverage
npm run test -- --coverage
```

**Test Structure:**
```
frontend/src/
├── __tests__/
│   ├── components/
│   │   ├── JobCreateModal.test.tsx
│   │   └── BatchJobModal.test.tsx
│   └── pages/
│       └── Jobs.test.tsx
└── e2e/
    ├── job-creation.spec.ts
    └── batch-processing.spec.ts
```

**Example Component Test:**
```typescript
import { render, screen, fireEvent } from '@testing-library/react'
import { BatchJobModal } from '../components/BatchJobModal'

describe('BatchJobModal', () => {
  it('submits batch jobs from JSON input', async () => {
    const onClose = vi.fn()
    render(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    // Select manual mode
    fireEvent.click(screen.getByText('Manual Input'))
    
    // Enter JSON
    const textarea = screen.getByLabelText(/job inputs/i)
    fireEvent.change(textarea, {
      target: { value: '[{"prompt": "test"}]' }
    })
    
    // Submit
    fireEvent.click(screen.getByText('Create Jobs'))
    
    // Verify API call was made
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled()
    })
  })
})
```

### Test Coverage Goals
- **API Endpoints**: 80%+ coverage for business logic
- **Services**: 70%+ coverage for core business logic
- **Components**: Focus on user interactions, not implementation details
- **Integration**: Cover critical user flows end-to-end

### Continuous Integration
Tests run automatically via GitHub Actions on push to `main`
and on pull requests. See `.github/workflows/ci.yml`.

The CI pipeline runs:
1. `ruff check` — linting
2. `pytest -m "not integration"` — unit tests
3. `npx vitest run` — frontend unit tests
4. `npx tsc --noEmit` — TypeScript type checking

## Deployment Notes

- 9 Docker containers: nginx, frontend, backend, worker, postgres, redis, comfyui, ollama, audiocraft
- ComfyUI runs in a separate container with ROCm support
- Wan 2.2 generates ~5s clips at 848×480 16fps; scenes >5s are auto-split into chained sub-clips
- Jobs are processed FIFO by default; workers can be scaled horizontally
- All media generation has retry with exponential backoff (4 retries)
- Use nginx as reverse proxy in production
- Enable HTTPS with Let's Encrypt

## Known Limitations

- Single GPU constraint requires job queuing
- AMD ROCm support is evolving; check compatibility
- Wan 2.2 max ~5s per clip (mitigated by automatic sub-clip chaining)
- MusicGen runs on CPU — ~30-45s per 5s of audio
- Preview generation adds processing time
