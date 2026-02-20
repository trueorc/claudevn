# ClaudeVN Serving Component Dockerfile
FROM node:20-bookworm-slim AS frontend-builder

# Build frontend
WORKDIR /app/frontend
COPY serving/frontend/package*.json ./
RUN npm ci
COPY serving/frontend/ ./
RUN npm run build

# Python runtime stage
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    openssh-client \
    redis-tools \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 and Claude CLI for serving-side OAuth login
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# Copy VERSION file and shared library, then install
COPY VERSION /app/VERSION
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Copy serving requirements and install
COPY serving/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy serving application
COPY serving/ .

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create necessary directories
RUN mkdir -p data/serving logs db data/repos data/ssh_keys marketplace/skills/system marketplace/skills/user

# Expose port (API with built-in Git Smart HTTP)
EXPOSE 8002

# Set environment variables
ENV SERVING_HOST=0.0.0.0
ENV SERVING_PORT=8002
ENV STORAGE_PATH=/app/data/serving
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1
ENV HEALTH_CHECK_INTERVAL=30
ENV DEGRADED_THRESHOLD=60
ENV OFFLINE_THRESHOLD=90
ENV MAX_FAILED_CHECKS=3
ENV AUTO_DEREGISTER=false

# Redis configuration
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379
ENV REDIS_DB=0
ENV REDIS_KEY_PREFIX=claudevn:

# Git infrastructure
ENV GIT_REPOS_PATH=/app/data/repos
ENV GIT_SSH_KEYS_PATH=/app/data/ssh_keys
ENV GIT_HOOK_REDIS_NOTIFY=true

# Claude authentication credentials path
ENV CLAUDE_CREDENTIALS_PATH=/app/data/serving/claude-credentials

# Skill marketplace
ENV SKILLS_PATH=/app/marketplace/skills

# Compute spawner
ENV WORKSPACES_PATH=/app/data/workspaces
ENV SERVING_PUBLIC_URL=http://serving:8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8002/api/v1/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]

