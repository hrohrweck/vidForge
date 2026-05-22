# Production Deployment Guide

This guide covers deploying VidForge to production.

## Prerequisites

- Docker and Docker Compose v2+
- 128GB RAM recommended (for local AI models)
- (Optional) AMD GPU with ROCm support for ComfyUI
- (Optional) External AI API keys (Poe, Replicate, etc.)
- Reverse proxy (nginx, Traefik, or Caddy) for SSL termination

## Architecture

VidForge runs as 9 Docker containers:

| Service | Port | Purpose |
|---|---|---|
| `nginx` | 80 | Reverse proxy (frontend + backend) |
| `frontend` | 3000 | React app (built by Vite) |
| `backend` | 8000 | FastAPI REST API |
| `worker` | — | Celery task processor |
| `postgres` | 5432 | PostgreSQL 16 database |
| `redis` | 6379 | Task queue + WebSocket pub/sub |
| `comfyui` | 8188 | ComfyUI image/video generation |
| `ollama` | 11434 | LLM inference (Qwen, Llama) |
| `audiocraft` | 5000 | MusicGen audio generation (CPU) |

## Environment Configuration

### Backend (`backend/.env`)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://vidforge:SECURE_PASSWORD@postgres:5432/vidforge

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=your-very-secure-secret-key-at-least-32-chars

# ComfyUI
COMFYUI_URL=http://comfyui:8188

# Storage
STORAGE_BACKEND=local  # or s3, ssh
STORAGE_PATH=/app/storage

# LLM Service
# Match OLLAMA_PORT in docker/.env (default 11435; use 11434 for native install)
OLLAMA_URL=http://ollama:11434

# AudioCraft (MusicGen)
AUDIOCRAFT_URL=http://audiocraft:5000

# Optional: S3 storage
S3_ENDPOINT=https://s3.amazonaws.com
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_BUCKET=vidforge-storage
S3_REGION=us-east-1

# Optional: SSH storage
SSH_HOST=your-server.com
SSH_USER=vidforge
SSH_KEY_PATH=/app/ssh_key
SSH_REMOTE_PATH=/var/lib/vidforge/storage

# Optional
DEBUG=false
ALLOWED_ORIGINS=https://yourdomain.com
```

### Frontend (`frontend/.env`)

```bash
VITE_API_URL=https://api.yourdomain.com
VITE_WS_URL=wss://api.yourdomain.com
```

### Docker (`docker/.env`)

```bash
COMFYUI_MODELS_PATH=../models/comfyui
COMFYUI_OUTPUT_PATH=../models/comfyui-output
OLLAMA_MODELS_PATH=../models/ollama
OLLAMA_PORT=11435
```

## Deployment Steps

### 1. Prepare Environment

```bash
git clone <your-repo-url>
cd vidforge

cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Edit both .env files with production values
```

### 2. Build and Start

```bash
cd docker

# Build all containers
docker-compose build

# Start services
docker-compose up -d

# Verify all services are healthy
docker-compose ps
```

### 3. Initialize Database

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Create superuser (first time only)
docker-compose exec backend python -m app.cli createsuperuser
```

### 4. Configure AI Models

1. **ComfyUI**: Download model files to the path specified in `COMFYUI_MODELS_PATH`:
   - Wan 2.2 ti2v model (video generation)
   - Flux.1-schnell (image generation)
   - UMT5 CLIP, VAE

2. **Ollama**: Models are auto-pulled on first use, or pre-download:
   ```bash
   docker-compose exec ollama ollama pull qwen3:32b
   ```

3. **Poe** (optional): Add a Poe provider via Admin → Providers with your
   API key. Configure Poe models in the provider settings.

### 5. Configure Reverse Proxy

#### Nginx Example

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    client_max_body_size 500M;  # Video uploads can be large

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $http_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Uploaded media (direct file access)
    location /uploads {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
}
```

### 6. SSL Certificates

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
sudo certbot renew --dry-run
```

## Scaling

### Workers

Scale Celery workers based on CPU cores:

```bash
docker-compose up -d --scale worker=4
```

### External Services

For production, consider external managed services:

- **PostgreSQL**: AWS RDS, Cloud SQL, or managed Postgres
- **Redis**: AWS ElastiCache or Redis Cloud
- Update `DATABASE_URL` and `REDIS_URL` accordingly

### GPU Support

```bash
# Start with ComfyUI ROCm support
docker-compose --profile rocm up -d
```

## Monitoring

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f worker

# Check container health
docker-compose ps

# Monitor resource usage
docker stats

# Health checks
curl http://localhost:8000/api/health
docker-compose exec postgres pg_isready -U vidforge
docker-compose exec redis redis-cli ping
```

## Backup and Recovery

### Database

```bash
# Backup
docker-compose exec postgres pg_dump -U vidforge vidforge > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20240101.sql | docker-compose exec -T postgres psql -U vidforge vidforge
```

### Storage

```bash
# Backup storage volume
docker run --rm \
  -v vidforge-storage:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/storage_backup.tar.gz /data
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|---|---|
| Database connection errors | Check PostgreSQL is running; verify `DATABASE_URL` |
| Worker not processing | Check Redis: `redis-cli ping`; check worker logs |
| GPU not detected | Verify ROCm installed; check `/dev/kfd /dev/dri` permissions |
| Videos too short | Check scene durations; Wan 2.2 maxes at ~5s per clip (auto-chained for longer scenes) |
| Poe models not showing | Add Poe provider in Admin; configure models; check API key |
| Out of memory | Reduce `wan_video_steps` in provider config; use shorter scenes |

## Security Checklist

- [ ] Change all default passwords
- [ ] Generate secure `SECRET_KEY` (32+ characters)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Configure firewall rules
- [ ] Set up database backups
- [ ] Review CORS settings (`ALLOWED_ORIGINS`)
- [ ] Set `DEBUG=false` in production
- [ ] Configure log rotation
- [ ] Regular security updates
