# Docker Compose Setup Summary

## ✅ Configuration Complete

Your ClaudeVN platform has been configured with Docker Compose using local bind mounts.

## What Was Done

### 1. Updated docker-compose.yml
- ✅ Converted from Docker-managed volumes to local bind mounts
- ✅ Added second compute instance (compute-2)
- ✅ Configured unique ports for each service
- ✅ Set unique instance IDs for compute instances
- ✅ Ensured UIs are exposed externally

### 2. Created Data Directory Structure
```
data/
├── marketplace/
│   ├── data/          # Registry data (bind mount)
│   └── logs/          # Service logs (bind mount)
├── serving/
│   ├── data/          # Serving storage (bind mount)
│   ├── logs/          # Service logs (bind mount)
│   └── db/            # Database files (bind mount)
├── compute-1/
│   ├── data/          # Instance 1 data (bind mount)
│   └── logs/          # Instance 1 logs (bind mount)
└── compute-2/
    ├── data/          # Instance 2 data (bind mount)
    └── logs/          # Instance 2 logs (bind mount)
```

### 3. Created Documentation
- ✅ `data/README.md` - Data directory management guide
- ✅ `DOCKER_COMPOSE_GUIDE.md` - Comprehensive usage guide
- ✅ `SETUP_SUMMARY.md` - This file

## Services Configured

| Service | Container Name | Host Port | Internal Port | UI/API Access |
|---------|----------------|-----------|---------------|---------------|
| Marketplace | claudevn-marketplace | 8001 | 8001 | ✅ UI + API |
| Serving | claudevn-serving | 8002 | 8002 | ✅ UI + API |
| Compute 1 | claudevn-compute-1 | 8003 | 8003 | API only |
| Compute 2 | claudevn-compute-2 | 8004 | 8003 | API only |

## Access URLs

### User Interfaces (Externally Accessible)
- **Marketplace UI**: http://localhost:8001
- **Serving UI**: http://localhost:8002

### API Endpoints
- **Marketplace API**: http://localhost:8001/api/v1
- **Marketplace Docs**: http://localhost:8001/docs
- **Serving API**: http://localhost:8002/api/v1
- **Serving Docs**: http://localhost:8002/docs
- **Compute 1 API**: http://localhost:8003
- **Compute 1 Docs**: http://localhost:8003/docs
- **Compute 2 API**: http://localhost:8004
- **Compute 2 Docs**: http://localhost:8004/docs

## Quick Start

### 1. Configure Environment Variables

```bash
# Copy the example file
cp docker.env.example .env

# Edit and add your API keys
nano .env  # or use your preferred editor
```

Required in `.env`:
```
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=your-key-here
```

### 2. Start All Services

```bash
# Build and start all services
docker-compose up --build

# Or start in background
docker-compose up -d --build
```

### 3. Verify Services

```bash
# Check all services are running
docker-compose ps

# Test health endpoints
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

### 4. Access the UIs

Open in your browser:
- Marketplace: http://localhost:8001
- Serving Dashboard: http://localhost:8002

### 5. Verify Compute Instances Registered

```bash
# Check compute instances registered with serving
curl http://localhost:8002/api/v1/compute/instances

# Expected: Both compute-01 and compute-02 should be listed
```

## Data Access

### View Logs Directly

```bash
# Marketplace logs
tail -f data/marketplace/logs/*.log

# Serving logs
tail -f data/serving/logs/*.log

# Compute instance logs
tail -f data/compute-1/logs/*.log
tail -f data/compute-2/logs/*.log

# All logs
tail -f data/*/logs/*.log
```

### Access Data Files

```bash
# Marketplace data
ls -la data/marketplace/data/

# Serving database
ls -la data/serving/db/

# Compute data
ls -la data/compute-1/data/
ls -la data/compute-2/data/
```

## Key Features

### ✅ Two Compute Instances
- Independent instances running on different ports
- Both register with the same Serving component
- Separate data directories for isolation
- Unique instance IDs (compute-01, compute-02)

### ✅ Local Bind Mounts
- Direct filesystem access to all data
- Easy backups (just copy `data/` folder)
- Real-time log monitoring
- No Docker volume commands needed

### ✅ UI Exposure
- Marketplace UI fully accessible at port 8001
- Serving UI fully accessible at port 8002
- CORS configured for local development
- OpenAPI documentation for all services

### ✅ Service Communication
- All services on same Docker network
- Compute instances auto-register with Serving
- Marketplace registers with Serving
- Inter-service DNS resolution

## Important Notes

### ⚠️ Data Directory
- Already added to .gitignore
- Will persist between container restarts
- Manual cleanup required for fresh start

### ⚠️ Environment Variables
- `.env` file required for API keys
- Copy from `docker.env.example`
- Never commit `.env` to git

### ⚠️ Port Conflicts
- Ensure ports 8001-8004 are available
- Stop local services if needed: `./stop_all.sh`

## Common Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart a service
docker-compose restart compute-1

# Rebuild after code changes
docker-compose up -d --build

# Check status
docker-compose ps
```

## Troubleshooting

### Services won't start
```bash
# Check logs
docker-compose logs

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Can't access data directory
```bash
# Fix permissions
chmod -R 755 data/
```

### Compute instances not registering
```bash
# Check serving is up first
curl http://localhost:8002/api/v1/health

# Check compute logs
docker-compose logs compute-1
docker-compose logs compute-2
```

## Next Steps

1. ✅ Configuration complete
2. 📝 Add API keys to `.env` file
3. 🚀 Run `docker-compose up --build`
4. 🌐 Access http://localhost:8001 and http://localhost:8002
5. 🔍 Verify compute instances at http://localhost:8002/api/v1/compute/instances

## Additional Documentation

- [Docker Compose Guide](DOCKER_COMPOSE_GUIDE.md) - Detailed usage guide
- [Data Directory Guide](data/README.md) - Data management
- [Docker README](DOCKER_README.md) - Quick start
- [Main README](README.md) - Project overview

---

**Status**: Ready to deploy  
**Configuration**: 1 Marketplace + 1 Serving + 2 Compute  
**Data Storage**: Local bind mounts (`./data/`)  
**Date**: 2024-11-24  
**Version**: 0.1.7

