# ClaudeVN Docker Quick Start

Run the entire ClaudeVN platform with Docker in minutes.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+

## Quick Start

```bash
# 1. Clone the repository
git clone <repository-url>
cd claudevn

# 2. (Optional) Set up environment variables for API keys
cp .env.example .env
# Edit .env and add your API keys

# 3. Build and start all services
docker-compose up --build

# 4. Access the services
# Marketplace: http://localhost:8001
# Serving:     http://localhost:8002
# Compute:     http://localhost:8003
```

## Common Commands

```bash
# Start all services (detached mode)
docker-compose up -d

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f marketplace

# Check service status
docker-compose ps

# Stop all services
docker-compose down

# Stop and remove all data (clean slate)
docker-compose down -v

# Rebuild after code changes
docker-compose up --build
```

## Environment Configuration

Create a `.env` file in the project root:

```bash
# LLM API Keys (required for Compute service)
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here

# Service Configuration (optional)
LOG_LEVEL=INFO
CORS_ORIGINS=*

# Compute Instance (optional)
INSTANCE_ID=compute-01
INSTANCE_NAME=My-Compute-Instance
```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Marketplace | http://localhost:8001 | Frontend and API |
| Marketplace API Docs | http://localhost:8001/docs | OpenAPI documentation |
| Serving | http://localhost:8002 | Frontend and API |
| Serving API Docs | http://localhost:8002/docs | OpenAPI documentation |
| Compute | http://localhost:8003 | API only |
| Compute API Docs | http://localhost:8003/docs | OpenAPI documentation |

## Architecture

The Docker setup includes:

- **Marketplace Container**: Agent discovery service with React frontend
- **Serving Container**: Orchestration hub with React frontend
- **Compute Container**: Agent runtime environment
- **Shared Network**: `claudevn-network` for inter-service communication
- **Persistent Volumes**: Data, logs, and database storage

## Health Checks

Each service includes automatic health checks:

```bash
# Check health status
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/health
```

## Data Persistence

Data is stored in Docker volumes:

```bash
# List volumes
docker volume ls | grep claudevn

# Backup data
docker run --rm \
  -v claudevn_marketplace_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/marketplace_backup.tar.gz -C /data .

# Restore data
docker run --rm \
  -v claudevn_marketplace_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/marketplace_backup.tar.gz -C /data
```

## Troubleshooting

### Ports Already in Use

```bash
# Check what's using the ports
lsof -i :8001
lsof -i :8002
lsof -i :8003

# Stop local services if running
./stop_all.sh

# Then start Docker services
docker-compose up
```

### Build Failures

```bash
# Clean build without cache
docker-compose build --no-cache

# Remove old images and containers
docker system prune -a
```

### View Detailed Logs

```bash
# All services with timestamps
docker-compose logs -f --timestamps

# Last 100 lines from marketplace
docker-compose logs --tail=100 marketplace
```

## Development vs Production

This setup is designed for **development and testing**. For production:

1. Use specific image tags, not `latest`
2. Set up proper SSL/TLS with reverse proxy
3. Use Docker secrets for API keys
4. Implement proper backup strategies
5. Configure resource limits
6. Set specific CORS origins
7. Use container orchestration (Kubernetes, Docker Swarm)

See the full [Docker Deployment Guide](docs/deployment/DOCKER_GUIDE.md) for production recommendations.

## Individual Services

You can run services individually:

```bash
# Just marketplace
docker-compose up marketplace

# Marketplace and serving (without compute)
docker-compose up marketplace serving

# Scale compute instances
docker-compose up --scale compute=3
```

## Hybrid Development

Run some services in Docker, others locally:

```bash
# Start serving in Docker
docker-compose up serving

# Run marketplace locally (in another terminal)
cd marketplace
./start.sh

# Marketplace will connect to Docker serving at http://localhost:8002
```

## Next Steps

1. ✅ Services running? Access http://localhost:8001
2. 📖 Read the [Docker Deployment Guide](docs/deployment/DOCKER_GUIDE.md)
3. 📚 Explore [Full Documentation](docs/README.md)
4. 🔧 Check [Configuration Guide](docs/guides/CONFIGURATION_GUIDE.md)

## Support

- Full documentation: `docs/`
- Docker guide: `docs/deployment/DOCKER_GUIDE.md`
- Issues: Check Docker logs with `docker-compose logs`

---

**ClaudeVN Platform** - AI Agent Orchestration in Docker

