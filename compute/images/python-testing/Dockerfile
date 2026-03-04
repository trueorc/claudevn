# ClaudeVN Compute Python Testing Image
# Extends compute-base with Python 3.12 + testing/linting tools.
#
# Build:
#   docker build -t trueorc/compute-python-testing:latest -f compute/images/python-testing/Dockerfile .
#
# Capabilities advertised: runtime:python:3.12, runtime:python, testing, linting
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install system dependencies (same as base compute)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    gosu \
    procps \
    iputils-ping \
    netcat-openbsd \
    findutils \
    && rm -rf /var/lib/apt/lists/*

# Install Python testing and linting tools
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    pytest-asyncio \
    pytest-xdist \
    tox \
    coverage \
    mypy \
    ruff

# Create non-root user (same as base compute)
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

# Bundle MCP stdio server script
COPY serving/mcp/stdio_server.py /app/mcp/stdio_server.py

# Copy detect-capabilities script
COPY compute/images/python-testing/detect-capabilities.sh /app/detect-capabilities.sh
RUN chmod +x /app/detect-capabilities.sh

# Copy and configure entrypoint
COPY compute/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create necessary directories
RUN mkdir -p data/compute logs workspace data/workspace && \
    chown -R compute:compute /app

# Default environment (overridden in docker-compose)
ENV COMPUTE_INSTANCE_ID=compute-python-testing
ENV COMPUTE_INSTANCE_NAME=Compute-PythonTesting
ENV COMPUTE_STORAGE_PATH=/app/data/compute
ENV COMPUTE_LOG_FILE=/app/logs/compute.log
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1
ENV COMPUTE_REGISTER_ON_STARTUP=true
ENV SERVING_URL=http://serving:8002
ENV COMPUTE_HEARTBEAT_INTERVAL=30
ENV MCP_ENABLED=true
ENV CLAUDEVN_SERVING_URL=http://serving:8002
ENV COMPUTE_SKILLS=code-writer,test-automator
ENV COMPUTE_CAPABILITIES=python,testing,linting
ENV COMPUTE_AUTH_MODE=serving
ENV CLAUDEVN_SERVING_AUTH_URL=http://serving:8002/api/v1/auth
ENV COMPUTE_HEARTBEAT_FILE=/tmp/compute-heartbeat

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD find /tmp/compute-heartbeat -newermt '-60 seconds' 2>/dev/null | grep -q . || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "app.py"]
