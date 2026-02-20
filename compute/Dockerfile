# ClaudeVN Compute Engine Dockerfile
# v1.0: Supports MCP-based communication with Serving
# Authentication: Uses host's Claude OAuth credentials via entrypoint copy from staging mount
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies
# Network utilities for integration tests (procps for pgrep, iputils-ping, netcat)
# gosu is used by entrypoint to drop from root to compute user after credential setup
#
# NOTE: Node.js is no longer needed. The claude-agent-sdk Python package bundles
# the Claude CLI as a native binary. See requirements.txt for the SDK dependency.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    gosu \
    procps \
    iputils-ping \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for Claude CLI (required for bypassPermissions mode)
# Claude CLI refuses to run with this flag as root for security reasons
RUN useradd -m -s /bin/bash -u 1000 compute && \
    mkdir -p /home/compute/.claude && \
    chown -R compute:compute /home/compute

# Copy VERSION file and shared library, then install
COPY VERSION /app/VERSION
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Copy compute requirements and install
COPY compute/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy compute application
COPY compute/ .

# Bundle MCP stdio server script for communication with Serving
COPY serving/mcp/stdio_server.py /app/mcp/stdio_server.py

# Copy and configure entrypoint script
COPY compute/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create necessary directories with proper ownership
# Own the entire /app directory as compute since the service runs as compute user
RUN mkdir -p data/compute logs workspace data/workspace && \
    chown -R compute:compute /app

# Expose port (each instance gets a different port via docker-compose)
EXPOSE 8003

# Default environment variables (overridden per instance in docker-compose)
ENV COMPUTE_HOST=0.0.0.0
ENV COMPUTE_PORT=8003
ENV COMPUTE_INSTANCE_ID=compute-default
ENV COMPUTE_INSTANCE_NAME=Compute-Instance
ENV COMPUTE_STORAGE_PATH=/app/data/compute
ENV COMPUTE_LOG_FILE=/app/logs/compute.log
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1
ENV COMPUTE_REGISTER_ON_STARTUP=true
ENV SERVING_URL=http://serving:8002
ENV COMPUTE_HEARTBEAT_INTERVAL=30

# MCP configuration
ENV MCP_ENABLED=true
ENV CLAUDEVN_SERVING_URL=http://serving:8002

# Skill/capability tags (for work assignment)
ENV COMPUTE_SKILLS=code-writer
ENV COMPUTE_CAPABILITIES=python,javascript

# Claude CLI / OAuth authentication
# Auth mode: "serving" fetches from Serving, "local" mounts host creds, "external" pre-provisioned
ENV COMPUTE_AUTH_MODE=serving
ENV CLAUDEVN_SERVING_AUTH_URL=http://serving:8002/api/v1/auth
# The entire service runs as 'compute' user (uid 1000) via gosu in entrypoint.
# Git authentication uses HTTP tokens provisioned by Serving via SSE.

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${COMPUTE_PORT}/api/v1/health || exit 1

# Entrypoint copies credentials from staging mount and fixes ownership
ENTRYPOINT ["/app/entrypoint.sh"]

# Run the application using shell form to expand environment variable
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${COMPUTE_PORT:-8003}"]

