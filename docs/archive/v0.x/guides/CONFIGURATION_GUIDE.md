# ClaudeVN Platform - Configuration Guide

**Version:** 0.1.6  
**Last Updated:** November 23, 2025

---

## Overview

The ClaudeVN platform consists of three independent services, each with its own configuration:

1. **Marketplace** (Port 8001) - Agent/tool discovery
2. **Serving** (Port 8002) - Orchestration hub
3. **Compute** (Port 8003) - Agent execution runtime

Each service can be configured independently via environment variables, making them suitable for both local development and distributed production deployments.

---

## Configuration Approaches

### Development: Single Configuration File

For local development, use a single `.env` file in the project root:

```bash
# Place at: /path/to/claudevn/.env
```

All services will read from this file when started with `./start_all.sh`.

### Production: Separate Configuration Files

For production, each service instance has its own configuration:

```bash
# Marketplace instance
claudevn/marketplace/.env

# Serving instance  
claudevn/serving/.env

# Compute instance (can have multiple)
claudevn/compute/.env
```

This allows you to:
- Deploy services on different machines
- Scale compute instances horizontally
- Configure environment-specific settings
- Manage secrets separately

---

## Complete Configuration Reference

### 🏪 Marketplace Configuration

**Location:** `marketplace/.env` or root `.env`

#### Server Settings
```bash
# Bind address (0.0.0.0 for all interfaces, 127.0.0.1 for localhost only)
MARKETPLACE_HOST=0.0.0.0

# Service port
MARKETPLACE_PORT=8001
```

#### Storage Backend
```bash
# Storage type: filesystem, dynamodb, or s3
STORAGE_BACKEND=filesystem

# Filesystem storage (default)
STORAGE_PATH=./marketplace/data/marketplace

# DynamoDB storage (optional)
DYNAMODB_TABLE_PREFIX=claudevn
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret

# S3 storage (optional)
S3_BUCKET=claudevn-marketplace
S3_PREFIX=marketplace/
```

#### Logging
```bash
# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Log file location
MARKETPLACE_LOG_FILE=./logs/marketplace.log
```

#### Application Settings
```bash
# Environment: development, staging, production
ENVIRONMENT=development

# Enable debug mode (adds detailed error messages)
DEBUG=false

# API rate limiting (requests per minute)
RATE_LIMIT=100
```

#### Frontend Integration
```bash
# Frontend build directory (for serving static files)
FRONTEND_BUILD_DIR=./marketplace/frontend/dist
```

#### Serving Registration (Optional)
```bash
# URL of serving component to register with
SERVING_URL=http://localhost:8002

# Auto-register with serving on marketplace startup
AUTO_REGISTER_WITH_SERVING=true

# Marketplace identity (optional, auto-generated if not provided)
MARKETPLACE_ID=marketplace-001
MARKETPLACE_NAME="ClaudeVN Central Marketplace"

# Public endpoint for serving to use (optional, for production)
MARKETPLACE_PUBLIC_ENDPOINT=https://marketplace.example.com

# Registration priority (lower = higher priority, 1-100)
MARKETPLACE_PRIORITY=1
```

---

### 🔀 Serving Configuration

**Location:** `serving/.env` or root `.env`

#### Server Settings
```bash
# Bind address
SERVING_HOST=0.0.0.0

# Service port
SERVING_PORT=8002
```

#### Storage
```bash
# Storage directory for registrations and sessions
STORAGE_PATH=./serving/data/serving
```

#### Health Monitoring
```bash
# Interval between health checks (seconds)
HEALTH_CHECK_INTERVAL=30

# Time before marking instance as degraded (seconds)
DEGRADED_THRESHOLD=60

# Time before marking instance as offline (seconds)
OFFLINE_THRESHOLD=90

# Max consecutive failed checks before action
MAX_FAILED_CHECKS=3

# Auto-deregister offline instances
AUTO_DEREGISTER=false
```

#### Component Registration
```bash
# NOTE: Serving uses a "phone home" registration pattern.
# Components (Marketplace, Compute) register themselves WITH Serving.
# Serving does NOT initiate connections - it only accepts registrations.
#
# Marketplaces register by calling: POST /api/v1/marketplaces/register
# Compute instances register by calling: POST /api/v1/compute/register
#
# No marketplace/compute URLs need to be configured in Serving.
# Configure SERVING_URL in marketplace/compute instead.
#
# See: docs/design/specifications/REGISTRATION_ARCHITECTURE.md
```

#### Logging
```bash
LOG_LEVEL=INFO
SERVING_LOG_FILE=./logs/serving.log
```

#### Session Management
```bash
# Session timeout (minutes)
SESSION_TIMEOUT=60

# Maximum concurrent sessions
MAX_SESSIONS=100

# Session storage cleanup interval (minutes)
SESSION_CLEANUP_INTERVAL=15
```

---

### ⚡ Compute Configuration

**Location:** `compute/.env` or root `.env`

#### Server Settings
```bash
# Bind address
COMPUTE_HOST=0.0.0.0

# Service port
COMPUTE_PORT=8003
```

#### Instance Identity
```bash
# Unique instance ID (auto-generated from hostname if not set)
COMPUTE_INSTANCE_ID=compute-node-01

# Human-readable instance name
COMPUTE_INSTANCE_NAME="Production Compute Node 1"
```

#### Serving Integration
```bash
# Serving component URL
SERVING_URL=http://localhost:8002

# Auto-register with serving on startup
COMPUTE_REGISTER_ON_STARTUP=true

# Heartbeat interval (10-300 seconds)
COMPUTE_HEARTBEAT_INTERVAL=30
```

#### Storage
```bash
# Data storage path
COMPUTE_STORAGE_PATH=./compute/data
```

#### Agents and Tools
```bash
# Directory containing agent JSON definitions
COMPUTE_AGENTS_DIR=./compute/agents

# Directory containing tool JSON definitions
COMPUTE_TOOLS_DIR=./compute/tools
```

#### LLM Providers
```bash
# OpenAI configuration
OPENAI_API_KEY=sk-...
OPENAI_ORG_ID=org-...  # Optional

# Anthropic configuration
ANTHROPIC_API_KEY=sk-ant-...

# Azure OpenAI (future)
# AZURE_OPENAI_ENDPOINT=...
# AZURE_OPENAI_API_KEY=...
```

#### Features
```bash
# Enable GPU acceleration
COMPUTE_ENABLE_GPU=false

# Enable specific features
ENABLE_STREAMING=true
ENABLE_FUNCTION_CALLING=true
```

#### Resource Limits (future)
```bash
# Maximum memory per task (MB)
MAX_TASK_MEMORY=2048

# Maximum CPU per task (cores)
MAX_TASK_CPU=2

# Task timeout (seconds)
TASK_TIMEOUT=300
```

#### Logging
```bash
LOG_LEVEL=INFO
COMPUTE_LOG_FILE=./logs/compute.log
```

---

## Configuration Examples

### Example 1: Local Development (Single Machine)

**File:** `.env` in project root

```bash
# ============================================
# ClaudeVN Platform - Development Configuration
# ============================================

# General
ENVIRONMENT=development
LOG_LEVEL=INFO

# ============================================
# Marketplace (8001)
# ============================================
MARKETPLACE_HOST=0.0.0.0
MARKETPLACE_PORT=8001
STORAGE_BACKEND=filesystem
STORAGE_PATH=./marketplace/data/marketplace

# Marketplace registers with serving (optional)
SERVING_URL=http://localhost:8002
AUTO_REGISTER_WITH_SERVING=true

# ============================================
# Serving (8002)
# ============================================
SERVING_HOST=0.0.0.0
SERVING_PORT=8002
HEALTH_CHECK_INTERVAL=30
DEGRADED_THRESHOLD=60
OFFLINE_THRESHOLD=90

# Note: Marketplace and Compute register themselves with Serving
# No marketplace/compute URLs needed in Serving configuration

# ============================================
# Compute (8003)
# ============================================
COMPUTE_HOST=0.0.0.0
COMPUTE_PORT=8003
COMPUTE_INSTANCE_ID=compute-dev-local
COMPUTE_INSTANCE_NAME="Development Machine"
SERVING_URL=http://localhost:8002
COMPUTE_REGISTER_ON_STARTUP=true
COMPUTE_HEARTBEAT_INTERVAL=30

# LLM Configuration
OPENAI_API_KEY=sk-your-key-here

# Optional: Agent/Tool Directories
COMPUTE_AGENTS_DIR=./examples/agents
COMPUTE_TOOLS_DIR=./examples/tools
```

**Usage:**
```bash
./start_all.sh  # Starts all three services
```

---

### Example 2: Production - Separate Machines

#### Marketplace Server (marketplace-prod.example.com)

**File:** `/opt/claudevn/marketplace/.env`

```bash
# Marketplace Production Configuration
ENVIRONMENT=production
LOG_LEVEL=WARNING

MARKETPLACE_HOST=0.0.0.0
MARKETPLACE_PORT=8001

# Production storage (DynamoDB)
STORAGE_BACKEND=dynamodb
DYNAMODB_TABLE_PREFIX=claudevn-prod
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# Register with serving component
SERVING_URL=https://serving-prod.example.com
AUTO_REGISTER_WITH_SERVING=true
MARKETPLACE_NAME="Production Central Marketplace"
MARKETPLACE_PUBLIC_ENDPOINT=https://marketplace-prod.example.com

# Security
CORS_ORIGINS=https://app.example.com,https://api.example.com
API_KEY_REQUIRED=true
```

**Start:**
```bash
cd /opt/claudevn/marketplace
./start.sh
```

---

#### Serving Server (serving-prod.example.com)

**File:** `/opt/claudevn/serving/.env`

```bash
# Serving Production Configuration
ENVIRONMENT=production
LOG_LEVEL=WARNING

SERVING_HOST=0.0.0.0
SERVING_PORT=8002

# Storage
STORAGE_PATH=/var/lib/claudevn/serving

# Health monitoring (production settings)
HEALTH_CHECK_INTERVAL=20
DEGRADED_THRESHOLD=45
OFFLINE_THRESHOLD=60
MAX_FAILED_CHECKS=3
AUTO_DEREGISTER=true

# Component Registration (Phone Home Pattern)
# Marketplaces and compute instances register themselves with Serving.
# No configuration needed here - configure SERVING_URL in those components instead.

# Session management
SESSION_TIMEOUT=120
MAX_SESSIONS=1000
```

**Start:**
```bash
cd /opt/claudevn/serving
./start.sh
```

---

#### Compute Node 1 (compute-01.example.com)

**File:** `/opt/claudevn/compute/.env`

```bash
# Compute Node 1 - Production
ENVIRONMENT=production
LOG_LEVEL=INFO

COMPUTE_HOST=0.0.0.0
COMPUTE_PORT=8003

# Instance identity
COMPUTE_INSTANCE_ID=compute-prod-01
COMPUTE_INSTANCE_NAME="Production Compute Node 1 - US-West-2a"

# Serving integration
SERVING_URL=https://serving-prod.example.com
COMPUTE_REGISTER_ON_STARTUP=true
COMPUTE_HEARTBEAT_INTERVAL=20

# Storage
COMPUTE_STORAGE_PATH=/var/lib/claudevn/compute

# Agents and tools
COMPUTE_AGENTS_DIR=/opt/claudevn/compute/agents
COMPUTE_TOOLS_DIR=/opt/claudevn/compute/tools

# LLM configuration
OPENAI_API_KEY=sk-prod-key-1...
ANTHROPIC_API_KEY=sk-ant-prod-key-1...

# Features
COMPUTE_ENABLE_GPU=true
```

**Start:**
```bash
cd /opt/claudevn/compute
./start.sh
```

---

#### Compute Node 2 (compute-02.example.com)

**File:** `/opt/claudevn/compute/.env`

```bash
# Compute Node 2 - Production (GPU-enabled)
ENVIRONMENT=production
LOG_LEVEL=INFO

COMPUTE_HOST=0.0.0.0
COMPUTE_PORT=8003

# Instance identity
COMPUTE_INSTANCE_ID=compute-prod-02-gpu
COMPUTE_INSTANCE_NAME="Production GPU Node - US-West-2b"

# Serving integration
SERVING_URL=https://serving-prod.example.com
COMPUTE_REGISTER_ON_STARTUP=true
COMPUTE_HEARTBEAT_INTERVAL=20

# Storage
COMPUTE_STORAGE_PATH=/var/lib/claudevn/compute

# Agents (specialized for ML/AI)
COMPUTE_AGENTS_DIR=/opt/claudevn/compute/agents-ml
COMPUTE_TOOLS_DIR=/opt/claudevn/compute/tools-ml

# LLM configuration
OPENAI_API_KEY=sk-prod-key-2...

# Features (GPU-enabled node)
COMPUTE_ENABLE_GPU=true
```

---

### Example 3: Hybrid Development/Testing

Multiple compute instances on one machine (different ports):

#### Compute Instance 1 (General Purpose)

**File:** `.env.compute1`

```bash
COMPUTE_PORT=8003
COMPUTE_INSTANCE_ID=compute-general
COMPUTE_INSTANCE_NAME="General Purpose Compute"
SERVING_URL=http://localhost:8002
COMPUTE_AGENTS_DIR=./agents/general
OPENAI_API_KEY=sk-...
```

**Start:**
```bash
cd compute
export $(cat .env.compute1 | xargs)
./start.sh
```

---

#### Compute Instance 2 (Specialized)

**File:** `.env.compute2`

```bash
COMPUTE_PORT=8004
COMPUTE_INSTANCE_ID=compute-specialized
COMPUTE_INSTANCE_NAME="Specialized Compute"
SERVING_URL=http://localhost:8002
COMPUTE_AGENTS_DIR=./agents/specialized
OPENAI_API_KEY=sk-...
```

**Start:**
```bash
cd compute
export $(cat .env.compute2 | xargs)
./start.sh
```

---

## Configuration Best Practices

### Security

1. **Never commit `.env` files** with real credentials
2. **Use `.env.example`** files for templates
3. **Rotate API keys regularly** in production
4. **Use secrets management** (AWS Secrets Manager, HashiCorp Vault) in production
5. **Restrict host binding** (`127.0.0.1`) when appropriate
6. **Enable HTTPS** in production with reverse proxy (nginx, Caddy)

### Development

1. **Use local file storage** for quick iterations
2. **Set `LOG_LEVEL=DEBUG`** for detailed information
3. **Keep ports consistent** (8001, 8002, 8003)
4. **Use single `.env` file** for convenience
5. **Use `./start_all.sh`** for full stack startup

### Production

1. **Use managed storage** (DynamoDB, S3, PostgreSQL)
2. **Set `LOG_LEVEL=WARNING`** or `ERROR`
3. **Enable auto-deregistration** for failed nodes
4. **Use shorter heartbeat intervals** (15-20s)
5. **Monitor logs** with centralized logging (CloudWatch, Datadog)
6. **Use service managers** (systemd, supervisord, Docker)
7. **Deploy serving and marketplace** with high availability
8. **Scale compute horizontally** based on load

### Multi-Compute Deployment

When running multiple compute instances:

1. **Use unique instance IDs** for each compute node
2. **Use descriptive names** indicating purpose/location
3. **Specialize by capability** (GPU nodes, CPU nodes, data processing)
4. **Load different agents** per node based on specialization
5. **Monitor aggregate capacity** via Serving's `/api/v1/compute/capabilities/aggregated`

---

## Environment Variable Priority

Configuration is loaded in this order (later overrides earlier):

1. **Default values** (in code)
2. **`.env` file** in project root (development)
3. **Component `.env` file** (e.g., `marketplace/.env`)
4. **System environment variables** (highest priority)

Example:
```bash
# .env file sets COMPUTE_PORT=8003
# But system override takes precedence:
export COMPUTE_PORT=9003
./start.sh  # Will use port 9003
```

---

## Verifying Configuration

### Check Loaded Configuration

Each service exposes its configuration (sanitized):

```bash
# Marketplace
curl http://localhost:8001/api/v1/health

# Serving
curl http://localhost:8002/api/v1/health

# Compute
curl http://localhost:8003/info
```

### Check Service Connectivity

```bash
# Verify compute registered with serving
curl http://localhost:8002/api/v1/compute

# Verify serving health monitoring
curl http://localhost:8002/api/v1/compute/stats/summary

# Verify marketplace registration (if enabled)
curl http://localhost:8002/api/v1/marketplaces
```

### Test Cross-Service Communication

```bash
# From compute, verify it can reach serving
curl http://localhost:8002/health

# From serving, verify it can reach marketplace
curl http://localhost:8001/api/v1/health
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find process using port
lsof -i :8003

# Kill process
kill -9 <PID>

# Or use stop scripts
./stop_all.sh
```

### Service Not Registering

1. **Check serving URL**: Ensure `SERVING_URL` is correct and reachable
2. **Check network**: Verify no firewall blocking
3. **Check logs**: `tail -f logs/compute.log`
4. **Test manually**:
   ```bash
   curl http://localhost:8002/api/v1/compute/register -X POST \
     -H "Content-Type: application/json" \
     -d '{"instance_id":"test","name":"Test","endpoint":"http://localhost:8003"}'
   ```

### Configuration Not Loading

1. **Check file location**: Must be in correct directory
2. **Check file permissions**: Must be readable
3. **Check syntax**: No spaces around `=`, no quotes unless needed
4. **Export manually** for testing:
   ```bash
   export COMPUTE_PORT=8003
   export SERVING_URL=http://localhost:8002
   ./start.sh
   ```

### Wrong Configuration Applied

1. **Check environment variables**: `env | grep COMPUTE_`
2. **Unset conflicts**: `unset COMPUTE_PORT`
3. **Use component `.env`**: Place config in `compute/.env` not root
4. **Clear and restart**: `./stop_all.sh && ./start_all.sh`

---

## Configuration Templates

Template files are provided in each component directory:

```bash
marketplace/.env.example
serving/.env.example
compute/.env.example
```

**Copy and customize:**
```bash
cp marketplace/.env.example marketplace/.env
cp serving/.env.example serving/.env
cp compute/.env.example compute/.env

# Edit with your values
nano marketplace/.env
```

---

## Docker Configuration (Future)

For containerized deployments, configuration can be passed via:

1. **Environment variables** in `docker run`
2. **`docker-compose.yml`** environment section
3. **Docker secrets** for sensitive values
4. **ConfigMaps** in Kubernetes

Example `docker-compose.yml`:
```yaml
version: '3.8'
services:
  compute:
    image: claudevn/compute:0.1.6
    environment:
      - COMPUTE_PORT=8003
      - SERVING_URL=http://serving:8002
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    env_file:
      - ./compute/.env
```

---

## References

- **Marketplace Configuration**: See `marketplace/README.md`
- **Serving Configuration**: See `serving/README.md`
- **Compute Configuration**: See `compute/README.md`
- **Environment Setup**: See `setup_environment.sh`

---

**Configuration Guide v0.1.6** - Complete configuration reference for ClaudeVN platform

