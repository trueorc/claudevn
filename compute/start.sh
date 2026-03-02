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
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN Compute Engine - Starting${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Configuration
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
if ! python3 -c "import pydantic" 2>/dev/null; then
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

# Wait for heartbeat file (indicates SSE connection is alive)
echo -e "${YELLOW}→${NC} Waiting for SSE connection..."
sleep 5

HEARTBEAT_FILE="${COMPUTE_HEARTBEAT_FILE:-/tmp/compute-heartbeat}"
if [ -f "$HEARTBEAT_FILE" ]; then
    echo -e "${GREEN}✓${NC} Compute engine is healthy (SSE connected)"
else
    echo -e "${YELLOW}⚠${NC}  Heartbeat file not yet created (SSE may still be connecting)"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Compute Engine Running${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${CYAN}Service Information:${NC}"
echo -e "  PID:       ${PID}"
echo -e "  Heartbeat: ${HEARTBEAT_FILE}"
echo ""
echo -e "${CYAN}Logs:${NC}"
echo -e "  ${LOG_DIR}/compute.log"
echo ""
echo -e "${CYAN}Management:${NC}"
echo -e "  Stop:      ${YELLOW}./stop.sh${NC}"
echo -e "  View logs: ${YELLOW}tail -f ${LOG_DIR}/compute.log${NC}"
echo ""
