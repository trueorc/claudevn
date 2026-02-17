#!/bin/bash

# ClaudeVN Compute Engine - Start Script

set -e

# Load environment variables from parent .env if it exists
if [ -f ../.env ]; then
    echo "Loading environment variables from ../.env..."
    export $(grep -v '^#' ../.env | grep -v '^$' | xargs)
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN Compute Engine - Starting${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Configuration
COMPUTE_PORT=${COMPUTE_PORT:-8003}
LOG_DIR="../logs"
PID_FILE=".compute.pid"

# Create log directory
mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠${NC}  Compute engine already running (PID: ${PID})"
        echo -e "${YELLOW}→${NC} Use ./stop.sh first to restart"
        exit 1
    else
        echo -e "${YELLOW}→${NC} Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Check if port is in use
if lsof -Pi :$COMPUTE_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${RED}✗${NC} Port ${COMPUTE_PORT} is already in use"
    echo -e "${YELLOW}→${NC} Process using port:"
    lsof -Pi :$COMPUTE_PORT -sTCP:LISTEN
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 is not installed"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $(python3 --version | cut -d' ' -f2)"

# Load environment variables from root .env file if it exists
if [ -f "../.env" ]; then
    echo -e "${YELLOW}→${NC} Loading environment variables from root .env..."
    set -a  # automatically export all variables
    source "../.env"
    set +a
    echo -e "${GREEN}✓${NC} Environment variables loaded"
fi

# Check dependencies
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}→${NC} Installing dependencies..."
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓${NC} Dependencies installed"
else
    echo -e "${GREEN}✓${NC} Dependencies are installed"
fi

# Check shared library
if ! python3 -c "import claudevn_shared" 2>/dev/null; then
    echo -e "${YELLOW}→${NC} Installing shared library..."
    pip install -q -e ../shared/
    echo -e "${GREEN}✓${NC} Shared library installed"
else
    echo -e "${GREEN}✓${NC} Shared library is installed"
fi

# Create data directories
mkdir -p data/compute

echo ""
echo -e "${CYAN}→ Starting Compute Engine...${NC}"

# Set environment variables
export COMPUTE_PORT=$COMPUTE_PORT
export COMPUTE_HOST=0.0.0.0
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Start the service
nohup python3 main.py > "${LOG_DIR}/compute.log" 2>&1 &
PID=$!

# Save PID
echo $PID > "$PID_FILE"

# Wait a moment for initialization
sleep 2

# Check if process is running
if ps -p $PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Compute engine started (PID: ${PID})"
else
    echo -e "${RED}✗${NC} Compute engine failed to start"
    echo -e "${YELLOW}→${NC} Check logs at: ${LOG_DIR}/compute.log"
    tail -20 "${LOG_DIR}/compute.log"
    rm -f "$PID_FILE"
    exit 1
fi

# Wait for health check
echo -e "${YELLOW}→${NC} Waiting for service to be ready..."
sleep 3

if curl -s -f --connect-timeout 3 --max-time 5 "http://localhost:${COMPUTE_PORT}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Compute engine is healthy"
else
    echo -e "${YELLOW}⚠${NC}  Health check pending (service may still be initializing)"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Compute Engine Running${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${CYAN}Service Information:${NC}"
echo -e "  API:    http://localhost:${COMPUTE_PORT}"
echo -e "  Health: http://localhost:${COMPUTE_PORT}/health"
echo -e "  Docs:   http://localhost:${COMPUTE_PORT}/docs"
echo -e "  PID:    ${PID}"
echo ""
echo -e "${CYAN}Logs:${NC}"
echo -e "  ${LOG_DIR}/compute.log"
echo ""
echo -e "${CYAN}Management:${NC}"
echo -e "  Stop:      ${YELLOW}./stop.sh${NC}"
echo -e "  View logs: ${YELLOW}tail -f ${LOG_DIR}/compute.log${NC}"
echo ""

