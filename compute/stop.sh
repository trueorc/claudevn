#!/bin/bash

# ClaudeVN Compute Engine - Stop Script

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN Compute Engine - Stopping${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

PID_FILE=".compute.pid"
COMPUTE_PORT=${COMPUTE_PORT:-8003}

# Function to kill process safely
kill_process() {
    local pid=$1
    
    if ps -p $pid > /dev/null 2>&1; then
        echo -e "${YELLOW}→${NC} Stopping compute engine (PID: ${pid})..."
        kill -15 $pid 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}→${NC} Force stopping..."
            kill -9 $pid 2>/dev/null || true
        fi
        
        if ! ps -p $pid > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Compute engine stopped"
            return 0
        else
            echo -e "${RED}✗${NC} Failed to stop compute engine"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠${NC}  Compute engine (PID: ${pid}) not running"
        return 0
    fi
}

# Try to stop using PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    kill_process $PID
    rm -f "$PID_FILE"
else
    echo -e "${YELLOW}⚠${NC}  No PID file found"
fi

# Also check port for any remaining processes
if lsof -Pi :$COMPUTE_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}→${NC} Found process on port ${COMPUTE_PORT}"
    PIDS=$(lsof -Pi :$COMPUTE_PORT -sTCP:LISTEN -t)
    for PID in $PIDS; do
        kill_process $PID
    done
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Compute Engine Stopped${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

