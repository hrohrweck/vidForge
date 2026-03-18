# AGENTS.md

This file provides guidance for AI agents working on the VidForge project.

## Project Overview

VidForge is a web application for automated social media video generation using local AI models. It targets AMD R9 AI HX470 hardware with Radeon 890M iGPU and 128GB RAM.

## Technology Stack

- **Frontend**: React + TypeScript + Vite
- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 16
- **Queue**: Redis + Celery
- **Video Generation**: ComfyUI with Wan2.2 model
- **Audio Generation**: AudioCraft/MusicGen
- **LLM**: Ollama or lemonade-server

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
celery -A app.workers worker --loglevel=info

# Run tests
pytest

# Type checking
mypy app/

# Linting
ruff check app/
```

### Frontend
```bash
# Install dependencies
cd frontend && npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run tests
npm run test

# Type checking
npm run typecheck

# Linting
npm run lint
```

### Docker
```bash
# Start all services
docker-compose up -d

# Start development environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Rebuild containers
docker-compose up -d --build

# View logs
docker-compose logs -f backend

# Run backend command
docker-compose exec backend alembic upgrade head
```

## Project Structure

```
vidforge/
├── frontend/           # React application
│   ├── src/
│   │   ├── api/        # API client and types
│   │   ├── components/ # React components
│   │   ├── pages/      # Page components
│   │   ├── hooks/      # Custom hooks
│   │   └── stores/     # Zustand stores
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/        # FastAPI routers
│   │   ├── models/     # SQLAlchemy models
│   │   ├── services/   # Business logic
│   │   ├── workers/    # Celery tasks
│   │   └── storage/    # Storage backends
│   ├── templates/      # Video templates (YAML)
│   ├── styles/         # Style presets (YAML)
│   └── requirements.txt
├── docker/             # Docker configurations
├── docs/               # Documentation
└── scripts/            # Utility scripts
```

## Key Patterns

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

### Job Processing Pattern
```python
@celery_app.task(bind=True)
def process_video_job(self, job_id: str):
    job = Job.get(job_id)
    job.status = "processing"
    job.save()
    
    try:
        # Process steps
        for step in pipeline:
            self.update_state(state='PROGRESS', meta={'step': step.name})
            execute_step(step)
        
        job.status = "completed"
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
    finally:
        job.save()
```

### Template Definition Pattern
```yaml
name: Template Name
description: Template description
inputs:
  - name: input_name
    type: file|text|number|select
    required: true|false
    default: default_value
pipeline:
  - step: step_name
    model: model_id
    params:
      key: value
```

## Environment Variables

### Backend (.env)
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/vidforge
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
COMFYUI_URL=http://comfyui:8188
OLLAMA_URL=http://localhost:11434
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

### Adding a New Template
1. Create YAML file in `backend/templates/`
2. Define inputs, pipeline steps, and outputs
3. Register template in template service
4. Add any new step handlers in workers

### Adding a New Storage Backend
1. Create new class in `backend/app/storage/` extending `StorageBackend`
2. Register in storage factory
3. Add configuration schema to settings
4. Update frontend settings page

### Adding a New API Endpoint
1. Create or update router in `backend/app/api/`
2. Define Pydantic schemas for request/response
3. Implement service logic
4. Add tests

### Adding a New Frontend Page
1. Create component in `frontend/src/pages/`
2. Add route in router configuration
3. Add navigation item if needed
4. Implement API integration with React Query

## Testing

### Backend Tests
- Unit tests in `backend/tests/unit/`
- Integration tests in `backend/tests/integration/`
- Use pytest-asyncio for async tests
- Mock external services (ComfyUI, Ollama)

### Frontend Tests
- Component tests with Vitest
- E2E tests with Playwright
- Mock API responses with MSW

## Deployment Notes

- ComfyUI runs in a separate container with ROCm support
- Jobs are processed FIFO by default
- Previews are generated at 480p 15fps for full renders
- Use nginx as reverse proxy in production
- Enable HTTPS with Let's Encrypt

## Known Limitations

- Single GPU constraint requires job queuing
- AMD ROCm support is evolving; check compatibility
- Long videos require segment merging
- Preview generation adds processing time
