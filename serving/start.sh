#!/bin/bash

# ClaudeVN Serving Component - Start Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables from parent .env if it exists
if [ -f ../.env ]; then
    echo "Loading environment variables from ../.env..."
    export $(grep -v '^#' ../.env | grep -v '^$' | xargs)
fi

# Configuration
HOST="${SERVING_HOST:-0.0.0.0}"
PORT="${SERVING_PORT:-8002}"
LOG_FILE="logs/serving.log"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ClaudeVN Serving Component - Start${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Create logs directory
mkdir -p logs

# Check if already running
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠️  Serving component already running on port $PORT${NC}"
    echo ""
    echo "To restart, first run: ./stop.sh"
    exit 1
fi

# Check Python virtual environment
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Load environment variables from root .env file if it exists
if [ -f "../.env" ]; then
    echo "Loading environment variables from root .env..."
    set -a  # automatically export all variables
    source "../.env"
    set +a
fi

# Install/update dependencies
echo "Checking dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Build frontend if not already built
if [ ! -d "frontend/dist" ]; then
    echo -e "${YELLOW}Frontend not built. Building...${NC}"
    cd frontend
    npm install
    npm run build
    cd ..
    echo -e "${GREEN}✓ Frontend built successfully${NC}"
else
    echo -e "${GREEN}✓ Frontend already built${NC}"
fi

# Start the server
echo ""
echo -e "${GREEN}Starting Serving Component...${NC}"
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Log:  $LOG_FILE"
echo ""

nohup python -m uvicorn app:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    > "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo $SERVER_PID > serving.pid

# Wait a moment and check if it started
sleep 2

if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}✓ Serving component started successfully${NC}"
    echo ""
    echo "Access points:"
    echo "  • UI:      http://localhost:$PORT"
    echo "  • API:     http://localhost:$PORT/api/v1"
    echo "  • Docs:    http://localhost:$PORT/docs"
    echo "  • Health:  http://localhost:$PORT/api/v1/health"
    echo ""
    echo "Logs: tail -f $LOG_FILE"
    echo "Stop: ./stop.sh"
    echo ""
else
    echo -e "${RED}✗ Failed to start serving component${NC}"
    echo "Check logs: cat $LOG_FILE"
    rm -f serving.pid
    exit 1
fi

