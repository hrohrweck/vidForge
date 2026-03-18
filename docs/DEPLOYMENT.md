# Production Deployment Guide

This guide covers deploying VidForge to production.

## Prerequisites

- Docker and Docker Compose v2+
- PostgreSQL 16 (or use the included Docker service)
- Redis 7 (or use the included Docker service)
- (Optional) AMD GPU with ROCm support for ComfyUI
- Reverse proxy (nginx, Traefik, or Caddy) for SSL termination

## Environment Configuration

### Backend Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://vidforge:SECURE_PASSWORD@postgres:5432/vidforge

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=your-very-secure-secret-key-at-least-32-chars

# ComfyUI
COMFYUI_URL=http://comfyui:8188

# Storage (choose one)
STORAGE_BACKEND=local  # or s3, ssh
STORAGE_PATH=/app/storage

# S3 Storage (if STORAGE_BACKEND=s3)
S3_ENDPOINT=https://s3.amazonaws.com
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_BUCKET=vidforge-storage
S3_REGION=us-east-1

# SSH Storage (if STORAGE_BACKEND=ssh)
SSH_HOST=your-server.com
SSH_USER=vidforge
SSH_KEY_PATH=/app/ssh_key
SSH_REMOTE_PATH=/var/lib/vidforge/storage

# LLM Service
OLLAMA_URL=http://localhost:11434

# Optional
DEBUG=false
ALLOWED_ORIGINS=https://yourdomain.com
```

### Frontend Environment Variables

Create a `.env` file in the `frontend/` directory:

```bash
VITE_API_URL=https://api.yourdomain.com
VITE_WS_URL=wss://api.yourdomain.com
```

### Docker Compose Production Override

Create `docker-compose.prod.yml`:

```yaml
services:
  backend:
    environment:
      - DEBUG=false
    restart: always
    
  worker:
    environment:
      - DEBUG=false
    restart: always
    deploy:
      replicas: 2  # Scale workers
      
  frontend:
    restart: always
    
  postgres:
    restart: always
    
  redis:
    restart: always
```

## Deployment Steps

### 1. Prepare Environment

```bash
# Clone repository
git clone <your-repo-url>
cd vidforge

# Create environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Edit environment files with production values
nano backend/.env
nano frontend/.env
```

### 2. Build and Start Services

```bash
cd docker

# Build all containers
docker-compose build

# Start services
docker-compose up -d

# Check status
docker-compose ps
```

### 3. Initialize Database

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Create superuser (first time only)
docker-compose exec backend python -m app.cli createsuperuser
```

### 4. Configure Reverse Proxy

#### Nginx Example

```nginx
# /etc/nginx/sites-available/vidforge
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
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # Uploads
    location /uploads {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 5. SSL Certificates (Let's Encrypt)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificates
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 6. Monitoring and Logs

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f worker

# Check container health
docker-compose ps

# Monitor resource usage
docker stats
```

## Scaling

### Horizontal Scaling

```bash
# Scale workers
docker-compose up -d --scale worker=4

# Use external PostgreSQL for better performance
# Update DATABASE_URL to point to external instance
```

### GPU Support

```bash
# Start with ComfyUI ROCm support
docker-compose --profile rocm up -d
```

## Backup and Recovery

### Database Backup

```bash
# Create backup
docker-compose exec postgres pg_dump -U vidforge vidforge > backup_$(date +%Y%m%d).sql

# Restore backup
cat backup_20240101.sql | docker-compose exec -T postgres psql -U vidforge vidforge
```

### Storage Backup

```bash
# Backup storage volume
docker run --rm -v vidforge-storage:/data -v $(pwd):/backup alpine tar czf /backup/storage_backup.tar.gz /data
```

## Troubleshooting

### Common Issues

1. **Database connection errors**
   - Check PostgreSQL is running: `docker-compose ps postgres`
   - Verify DATABASE_URL is correct
   - Check PostgreSQL logs: `docker-compose logs postgres`

2. **Worker not processing jobs**
   - Check Redis connection: `docker-compose exec redis redis-cli ping`
   - Check worker logs: `docker-compose logs worker`
   - Verify Celery is running: `docker-compose exec worker celery -A app.workers inspect active`

3. **GPU not detected**
   - Verify ROCm is installed on host
   - Check device permissions: `ls -la /dev/kfd /dev/dri`
   - Use `--profile rocm` flag when starting

### Health Checks

```bash
# Backend health
curl http://localhost:8000/api/health

# Database health
docker-compose exec postgres pg_isready -U vidforge

# Redis health
docker-compose exec redis redis-cli ping
```

## Security Checklist

- [ ] Change all default passwords
- [ ] Generate secure SECRET_KEY (32+ characters)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Configure firewall rules
- [ ] Set up database backups
- [ ] Review and update CORS settings
- [ ] Enable rate limiting
- [ ] Set up monitoring and alerts
- [ ] Configure log rotation
- [ ] Regular security updates

## Performance Tuning

### PostgreSQL

```sql
-- Recommended settings (adjust based on available RAM)
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = '0.9';
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = '100';
ALTER SYSTEM SET random_page_cost = '1.1';
ALTER SYSTEM SET effective_io_concurrency = '200';
ALTER SYSTEM SET work_mem = '2621kB';
ALTER SYSTEM SET min_wal_size = '1GB';
ALTER SYSTEM SET max_wal_size = '4GB';
```

### Redis

```bash
# /etc/redis/redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

### Celery Workers

```yaml
# Scale based on CPU cores
docker-compose up -d --scale worker=$(nproc)
```

## Maintenance

### Updates

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head
```

### Log Rotation

Docker automatically handles log rotation, but you can configure limits:

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```
