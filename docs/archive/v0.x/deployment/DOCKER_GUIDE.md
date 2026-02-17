# ClaudeVN Docker Deployment Guide

This guide explains how to deploy ClaudeVN using Docker containers.

## Overview

The ClaudeVN platform consists of three main services that can be containerized:

- **Marketplace** (port 8001) - Agent discovery and registry with React frontend
- **Serving** (port 8002) - Central orchestration hub with React frontend
- **Compute** (port 8003) - Agent runtime environment

## Quick Start

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- 10GB disk space

### Basic Usage

```bash
# Build and start all services
docker-compose up --build

# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### Access Services

Once running, access the services at:

- **Marketplace Frontend**: http://localhost:8001
- **Marketplace API**: http://localhost:8001/api/v1
- **Marketplace Docs**: http://localhost:8001/docs
- **Serving Frontend**: http://localhost:8002
- **Serving API**: http://localhost:8002/api/v1
- **Serving Docs**: http://localhost:8002/docs
- **Compute API**: http://localhost:8003
- **Compute Docs**: http://localhost:8003/docs

## Configuration

### Environment Variables

You can configure services using environment variables. Create a `.env` file in the project root:

```bash
# LLM API Keys
OPENAI_API_KEY=your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here

# Service Configuration
LOG_LEVEL=INFO
CORS_ORIGINS=*

# Compute Instance
INSTANCE_ID=compute-01
INSTANCE_NAME=My-Compute-Instance
```

Docker Compose will automatically load this file.

### Production Configuration

For production deployments, customize the `docker-compose.yml`:

1. **Remove Development Features**:
   - Change `restart: unless-stopped` to `restart: always`
   - Remove volume mounts for local development
   - Set specific CORS origins instead of `*`

2. **Add Reverse Proxy**:
   - Use nginx or traefik for SSL termination
   - Set up proper domain names
   - Configure rate limiting

3. **Secrets Management**:
   - Use Docker secrets or external secret managers
   - Don't commit API keys to version control

## Individual Services

### Building Individual Containers

Build each service separately:

```bash
# Marketplace
docker build -t claudevn-marketplace:latest -f marketplace/Dockerfile .

# Serving
docker build -t claudevn-serving:latest -f serving/Dockerfile .

# Compute
docker build -t claudevn-compute:latest -f compute/Dockerfile .
```

### Running Individual Containers

Run services independently:

```bash
# Marketplace
docker run -d \
  --name claudevn-marketplace \
  -p 8001:8001 \
  -v marketplace_data:/app/data/marketplace \
  claudevn-marketplace:latest

# Serving
docker run -d \
  --name claudevn-serving \
  -p 8002:8002 \
  -v serving_data:/app/data/serving \
  claudevn-serving:latest

# Compute
docker run -d \
  --name claudevn-compute \
  -p 8003:8003 \
  -e OPENAI_API_KEY=your-key \
  -e SERVING_URL=http://serving:8002 \
  -v compute_data:/app/data/compute \
  claudevn-compute:latest
```

## Dockerfile Details

### Multi-Stage Builds

The Marketplace and Serving Dockerfiles use multi-stage builds:

1. **Frontend Builder Stage**: Uses Node.js to build React frontends
2. **Runtime Stage**: Uses Python slim image for the FastAPI backend

This approach:
- Reduces final image size (no Node.js in production)
- Improves build caching
- Separates build-time and runtime dependencies

### Shared Library

All services depend on the `shared` library. The Dockerfiles:
1. Copy the shared library first
2. Install it as an editable package
3. Then install service-specific dependencies

### Health Checks

Each service includes a health check:
- Interval: 30 seconds
- Timeout: 10 seconds
- Start period: 40 seconds (allows startup time)
- Retries: 3 attempts

## Volumes

### Persistent Data

The docker-compose configuration creates named volumes for:

- `marketplace_data` - Agent and tool registry data
- `marketplace_logs` - Marketplace service logs
- `serving_data` - Session and registry data
- `serving_logs` - Serving service logs
- `serving_db` - Database files
- `compute_data` - Compute instance data
- `compute_logs` - Compute service logs

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect a volume
docker volume inspect claudevn_marketplace_data

# Remove unused volumes
docker volume prune

# Backup a volume
docker run --rm \
  -v claudevn_marketplace_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/marketplace_data.tar.gz -C /data .

# Restore a volume
docker run --rm \
  -v claudevn_marketplace_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/marketplace_data.tar.gz -C /data
```

## Networking

### Inter-Service Communication

Services communicate via the `claudevn-network` bridge network:

- Services use container names as hostnames
- Example: `http://serving:8002`, `http://marketplace:8001`
- Network isolation from other Docker containers

### External Access

Map ports to host system:
- 8001 → Marketplace
- 8002 → Serving
- 8003 → Compute

## Troubleshooting

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f marketplace
docker-compose logs -f serving
docker-compose logs -f compute

# Last 100 lines
docker-compose logs --tail=100
```

### Check Service Health

```bash
# Service status
docker-compose ps

# Health check status
docker inspect claudevn-marketplace | grep Health -A 10

# Test endpoints
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/health
```

### Common Issues

**Port Already in Use**:
```bash
# Find process using port
lsof -i :8001
# or
netstat -tulpn | grep 8001

# Stop existing services
docker-compose down
./stop_all.sh  # If running locally
```

**Build Failures**:
```bash
# Clean build without cache
docker-compose build --no-cache

# Remove old images
docker image prune -a
```

**Volume Permissions**:
```bash
# If permission errors occur, ensure volume directories are writable
docker-compose down -v
docker-compose up
```

## Production Deployment

### Docker Swarm

Deploy as a stack:

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml claudevn

# List services
docker stack services claudevn

# Remove stack
docker stack rm claudevn
```

### Kubernetes

Convert docker-compose to Kubernetes manifests:

```bash
# Install kompose
curl -L https://github.com/kubernetes/kompose/releases/download/v1.31.2/kompose-linux-amd64 -o kompose
chmod +x kompose

# Convert
./kompose convert -f docker-compose.yml

# Apply to cluster
kubectl apply -f marketplace-deployment.yaml
kubectl apply -f serving-deployment.yaml
kubectl apply -f compute-deployment.yaml
```

## Security Best Practices

1. **Use Specific Base Images**: Pin versions in Dockerfiles
2. **Run as Non-Root**: Add USER directive in Dockerfiles
3. **Scan Images**: Use `docker scan` or Trivy
4. **Limit Resources**: Set CPU/memory limits in docker-compose
5. **Network Segmentation**: Use multiple networks for isolation
6. **Secrets Management**: Use Docker secrets or external vaults
7. **Update Regularly**: Rebuild images with latest patches

## Performance Optimization

### Build Optimization

- Use `.dockerignore` to exclude unnecessary files
- Layer caching: Put frequently changing files last
- Multi-stage builds to reduce image size

### Runtime Optimization

```yaml
# Add resource limits to docker-compose.yml
services:
  marketplace:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

### Logging Configuration

```yaml
services:
  marketplace:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Monitoring

### Docker Stats

```bash
# Real-time resource usage
docker stats

# Specific services
docker stats claudevn-marketplace claudevn-serving claudevn-compute
```

### Health Monitoring

```bash
# Create monitoring script
cat > monitor.sh << 'EOF'
#!/bin/bash
while true; do
  echo "=== $(date) ==="
  curl -s http://localhost:8001/api/v1/health | jq .
  curl -s http://localhost:8002/api/v1/health | jq .
  curl -s http://localhost:8003/health | jq .
  sleep 30
done
EOF

chmod +x monitor.sh
./monitor.sh
```

## Development Workflow

### Local Development with Docker

```bash
# Build once
docker-compose build

# Start with auto-reload (requires volume mounts)
docker-compose -f docker-compose.dev.yml up

# Run tests in container
docker-compose exec marketplace pytest
```

### Hybrid Development

Run some services in Docker, others locally:

```bash
# Start only serving in Docker
docker-compose up serving

# Run marketplace locally
cd marketplace
./start.sh

# Run compute locally with Docker serving
cd compute
SERVING_URL=http://localhost:8002 ./start.sh
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Docker Images

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build images
        run: |
          docker-compose build
      
      - name: Run tests
        run: |
          docker-compose up -d
          sleep 30
          curl http://localhost:8001/api/v1/health
          curl http://localhost:8002/api/v1/health
          curl http://localhost:8003/health
          docker-compose down
```

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- ClaudeVN Documentation: `../README.md`

---

**Note**: This is a development-focused Docker setup. For production deployments, consult your infrastructure team and implement proper security, monitoring, and backup strategies.

