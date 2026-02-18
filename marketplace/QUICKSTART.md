# Marketplace Service - Quick Start

## Running Standalone (Development)

### Prerequisites
- Python 3.11+
- pip

### 1. Install Dependencies

```bash
cd marketplace
pip install -r requirements.txt
```

### 2. Start Service

```bash
python app.py
```

Service will start on http://localhost:8003

### 3. Test Endpoints

```bash
# Health check
curl http://localhost:8003/api/v1/health

# List skills
curl http://localhost:8003/api/v1/skills

# View API docs
open http://localhost:8003/docs
```

---

## Running with Docker Compose

### 1. Build Services

```bash
cd claudevn
docker compose build marketplace
```

### 2. Start Services

```bash
# Start all services (marketplace + serving + redis)
docker compose up -d

# Or start only marketplace
docker compose up -d marketplace
```

### 3. Check Status

```bash
docker compose ps
docker compose logs marketplace
```

### 4. Test Marketplace

```bash
# Health check
curl http://localhost:8003/api/v1/health

# List skills
curl http://localhost:8003/api/v1/skills

# Get specific skill
curl http://localhost:8003/api/v1/skills/code-writer

# Compose agent
curl -X POST http://localhost:8003/api/v1/skills/compose \
  -H "Content-Type: application/json" \
  -d '{
    "task": {
      "task_id": "test-123",
      "description": "Test task",
      "required_capabilities": ["coding"]
    }
  }'
```

---

## Environment Variables

```bash
# Service configuration
export MARKETPLACE_HOST=0.0.0.0
export MARKETPLACE_PORT=8003

# Paths
export SKILLS_PATH=./skills

# Logging
export LOG_LEVEL=INFO

# CORS
export CORS_ORIGINS=*

# API version
export API_VERSION=v1
```

---

## API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8003/docs
- **ReDoc:** http://localhost:8003/redoc
- **OpenAPI JSON:** http://localhost:8003/openapi.json

---

## Adding Custom Skills

### 1. Create Skill File

```bash
cd marketplace/skills/user
nano my-custom-skill.yaml
```

### 2. Define Skill

```yaml
id: my-custom-skill
name: My Custom Skill
description: Does something useful
version: "1.0.0"

instructions: |
  # My Custom Skill
  
  ## Role
  You do something useful.
  
  ## Approach
  - Step 1
  - Step 2

specialized_tools:
  - my_tool

tags:
  - custom
  - useful

constraints:
  - Don't do bad things
```

### 3. Restart Service

```bash
docker compose restart marketplace
```

### 4. Verify Skill

```bash
curl http://localhost:8003/api/v1/skills/my-custom-skill
```

---

## Troubleshooting

### Service won't start

```bash
# Check logs
docker compose logs marketplace

# Check health
docker compose ps marketplace

# Rebuild
docker compose build --no-cache marketplace
docker compose up -d marketplace
```

### Skills not loading

```bash
# Check skills directory
docker compose exec marketplace ls -la /app/skills/system/

# Check logs for errors
docker compose logs marketplace | grep -i skill

# Verify YAML syntax
yamllint marketplace/skills/system/*.yaml
```

### Connection refused

```bash
# Check if service is running
docker compose ps marketplace

# Check port binding
docker compose port marketplace 8003

# Check network
docker network inspect claudevn-network
```

---

## Production Deployment

### 1. Configure Environment

```bash
# .env file
MARKETPLACE_HOST=0.0.0.0
MARKETPLACE_PORT=8003
SKILLS_PATH=/app/skills
LOG_LEVEL=INFO
CORS_ORIGINS=https://your-domain.com
```

### 2. Secure CORS

Update `CORS_ORIGINS` to allow only trusted domains:

```bash
export CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

### 3. Volume Mounting

Mount skills directory to persist custom skills:

```yaml
volumes:
  - ./marketplace/skills:/app/skills:ro  # Read-only for security
```

### 4. Health Monitoring

```bash
# Kubernetes liveness probe
livenessProbe:
  httpGet:
    path: /api/v1/health
    port: 8003
  initialDelaySeconds: 10
  periodSeconds: 30
```

---

## Integration with Serving

Serving connects to marketplace via HTTP:

```python
from services.marketplace_client import get_marketplace_client

client = get_marketplace_client()

# List skills
response = await client.list_skills(tags=['coding'])

# Compose agent
agent = await client.compose_agent(
    task_id='task-123',
    task_description='Build a feature',
    required_capabilities=['coding', 'testing']
)
```

Configure marketplace URL:

```bash
export MARKETPLACE_URL=http://marketplace:8003  # Docker network
# or
export MARKETPLACE_URL=http://localhost:8003    # Local development
```

---

## Development Tips

### Hot Reload

```bash
# Run with auto-reload
uvicorn app:app --reload --host 0.0.0.0 --port 8003
```

### Debug Mode

```bash
export LOG_LEVEL=DEBUG
python app.py
```

### Test Changes

```bash
# Run syntax check
python -m py_compile *.py

# Run with docker compose
docker compose up marketplace
```

---

For full documentation, see [README.md](README.md)
