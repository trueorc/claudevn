# Docker Compose Configuration Guide

## Overview

Your ClaudeVN platform is now configured with:
- ✅ **1 Marketplace** instance (UI + API)
- ✅ **1 Serving** component (UI + API)
- ✅ **2 Compute** instances (APIs)
- ✅ Local bind mounts for direct data access

## Service Access

| Service | URL | Description |
|---------|-----|-------------|
| **Marketplace UI** | http://localhost:8001 | Browse agents and tools |
| **Marketplace API** | http://localhost:8001/api/v1 | REST API |
| **Marketplace Docs** | http://localhost:8001/docs | OpenAPI/Swagger |
| **Serving UI** | http://localhost:8002 | Orchestration dashboard |
| **Serving API** | http://localhost:8002/api/v1 | REST API |
| **Serving Docs** | http://localhost:8002/docs | OpenAPI/Swagger |
| **Compute 1 API** | http://localhost:8003 | Instance 1 API |
| **Compute 1 Docs** | http://localhost:8003/docs | OpenAPI/Swagger |
| **Compute 2 API** | http://localhost:8004 | Instance 2 API |
| **Compute 2 Docs** | http://localhost:8004/docs | OpenAPI/Swagger |

## Quick Start

```bash
# 1. Ensure you have a .env file with API keys
cp docker.env.example .env
# Edit .env and add your OPENAI_API_KEY and ANTHROPIC_API_KEY

# 2. Start all services
docker-compose up --build

# 3. Access the UIs
# Marketplace: http://localhost:8001
# Serving:     http://localhost:8002

# 4. View logs (in another terminal)
docker-compose logs -f

# 5. Stop all services
docker-compose down
```

## Data Storage

All data is stored in the `./data/` directory with bind mounts:

```
data/
├── marketplace/data/    # Agent/tool registry
├── marketplace/logs/    # Marketplace logs
├── serving/data/        # Session data
├── serving/logs/        # Serving logs
├── serving/db/          # Database files
├── compute-1/data/      # Instance 1 data
├── compute-1/logs/      # Instance 1 logs
├── compute-2/data/      # Instance 2 data
└── compute-2/logs/      # Instance 2 logs
```

**Benefits:**
- Direct file system access
- Easy backups
- Real-time log viewing
- No need for `docker volume` commands

## Common Commands

### Start Services

```bash
# Start all services (foreground with logs)
docker-compose up

# Start in background (detached)
docker-compose up -d

# Rebuild and start (after code changes)
docker-compose up --build

# Start specific services
docker-compose up marketplace serving
docker-compose up compute-1 compute-2
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f marketplace
docker-compose logs -f serving
docker-compose logs -f compute-1
docker-compose logs -f compute-2

# Last 100 lines
docker-compose logs --tail=100

# Or access logs directly from data directory
tail -f data/marketplace/logs/*.log
tail -f data/compute-1/logs/*.log
```

### Stop Services

```bash
# Stop all services (keeps data)
docker-compose down

# Stop and remove everything including images
docker-compose down --rmi all

# Note: Data in ./data/ directory persists!
```

### Check Status

```bash
# Service status
docker-compose ps

# Health checks
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/health
curl http://localhost:8004/health

# Check registered compute instances
curl http://localhost:8002/api/v1/compute/instances
```

### Restart Individual Services

```bash
# Restart a specific service
docker-compose restart marketplace
docker-compose restart serving
docker-compose restart compute-1
docker-compose restart compute-2

# Rebuild and restart
docker-compose up -d --build compute-1
```

## Two Compute Instances

Your setup includes two compute instances that:
- ✅ Run independently on different ports (8003 and 8004)
- ✅ Register with the same Serving component
- ✅ Share the same LLM API keys
- ✅ Have separate data directories
- ✅ Have unique instance IDs (compute-01 and compute-02)

### Verify Both Instances

```bash
# Check both are running
curl http://localhost:8003/info
curl http://localhost:8004/info

# Verify registration with Serving
curl http://localhost:8002/api/v1/compute/instances | jq '.instances[] | {id: .instance_id, name: .name, status: .status}'
```

### Scale to More Instances

To add a third instance, add to docker-compose.yml:

```yaml
  compute-3:
    build:
      context: .
      dockerfile: compute/Dockerfile
    container_name: claudevn-compute-3
    ports:
      - "8005:8003"  # Next available port
    environment:
      - COMPUTE_HOST=0.0.0.0
      - COMPUTE_PORT=8003
      - INSTANCE_ID=compute-03  # Unique ID
      - INSTANCE_NAME=Compute-Instance-03
      - STORAGE_PATH=/app/data/compute
      - LOG_LEVEL=INFO
      - REGISTER_ON_STARTUP=true
      - SERVING_URL=http://serving:8002
      - HEARTBEAT_INTERVAL=30
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - ENABLE_GPU=false
    volumes:
      - ./data/compute-3/data:/app/data/compute
      - ./data/compute-3/logs:/app/logs
    networks:
      - claudevn-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    depends_on:
      - serving
```

Then create the directory: `mkdir -p data/compute-3/{data,logs}`

## Data Management

### Backup All Data

```bash
# Create timestamped backup
tar czf claudevn-backup-$(date +%Y%m%d-%H%M%S).tar.gz data/

# Backup to specific location
tar czf /backup/claudevn-data.tar.gz data/
```

### Restore Data

```bash
# Stop services first
docker-compose down

# Restore from backup
tar xzf claudevn-backup-20241124-120000.tar.gz

# Start services
docker-compose up -d
```

### Clean Up Data

```bash
# Stop services
docker-compose down

# Remove all data (fresh start)
rm -rf data/*/data/* data/*/logs/* data/*/db/*

# Or remove specific service data
rm -rf data/compute-1/data/*
rm -rf data/marketplace/logs/*

# Start services
docker-compose up -d
```

## Troubleshooting

### Port Already in Use

```bash
# Check what's using the port
lsof -i :8001
lsof -i :8002
lsof -i :8003
lsof -i :8004

# Kill the process
kill -9 <PID>

# Or stop local services
./stop_all.sh
```

### Permission Denied on Data Directory

```bash
# Fix permissions
chmod -R 755 data/
sudo chown -R $(id -u):$(id -g) data/
```

### Service Won't Start

```bash
# Check logs
docker-compose logs marketplace
docker-compose logs serving
docker-compose logs compute-1

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Compute Instance Not Registering

```bash
# Check serving is running first
curl http://localhost:8002/api/v1/health

# Check compute can reach serving
docker-compose exec compute-1 curl http://serving:8002/api/v1/health

# View compute logs
docker-compose logs compute-1
docker-compose logs compute-2
```

## Environment Variables

Create a `.env` file in the project root:

```bash
# Required for Compute instances
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here

# Optional overrides
LOG_LEVEL=INFO
CORS_ORIGINS=*
```

## Development Workflow

### Edit Code and Reload

```bash
# 1. Make code changes
# 2. Rebuild and restart specific service
docker-compose up -d --build marketplace

# 3. View logs to verify
docker-compose logs -f marketplace
```

### Test with Fresh Data

```bash
# Stop services
docker-compose down

# Clear data
rm -rf data/*/data/*

# Restart (will load seed data)
docker-compose up
```

## Production Considerations

For production use:
1. Set specific CORS origins (not `*`)
2. Use proper secrets management
3. Set resource limits in docker-compose.yml
4. Use reverse proxy (nginx/traefik) for SSL
5. Implement proper backup strategies
6. Monitor health endpoints
7. Use Docker Swarm or Kubernetes for orchestration

See [Docker Deployment Guide](docs/deployment/DOCKER_GUIDE.md) for details.

## Additional Resources

- [Docker README](DOCKER_README.md) - Quick start guide
- [Docker Deployment Guide](docs/deployment/DOCKER_GUIDE.md) - Comprehensive guide
- [Data Directory README](data/README.md) - Data management details
- [Main README](README.md) - Project overview

---

**Configuration:** 1 Marketplace + 1 Serving + 2 Compute instances  
**Data Storage:** Local bind mounts in `./data/`  
**Version:** 0.1.7

