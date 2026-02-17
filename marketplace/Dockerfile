# ClaudeVN Skill Marketplace Dockerfile
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy VERSION file and shared library, then install
COPY VERSION /app/VERSION
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Copy marketplace requirements and install
COPY marketplace/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy marketplace application
COPY marketplace/ .

RUN mkdir -p skills/system skills/user personas/system personas/user

ENV MARKETPLACE_HOST=0.0.0.0
ENV MARKETPLACE_PORT=8003
ENV SKILLS_PATH=/app/skills
ENV PERSONAS_PATH=/app/personas
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
