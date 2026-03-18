# VidForge

AI-powered video generation platform for social media.

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
docker-compose exec backend alembic upgrade head
```

5. Access the application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Without Docker

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
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

## Project Structure

```
vidforge/
├── frontend/           # React application
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── api/        # REST endpoints
│   │   ├── models/     # Database models
│   │   ├── services/   # Business logic
│   │   ├── workers/    # Celery tasks
│   │   └── storage/    # Storage backends
│   ├── templates/      # Video templates
│   └── styles/         # Style presets
├── docker/             # Docker configurations
└── docs/               # Documentation
```

## License

MIT
