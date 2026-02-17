#!/bin/bash

# ClaudeVN Platform - Stop All Services

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN Platform - Stopping Services${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

PID_FILE=".claudevn.pid"

# Function to kill process safely
kill_process() {
    local pid=$1
    local name=$2
    
    if ps -p $pid > /dev/null 2>&1; then
        echo -e "${YELLOW}→${NC} Stopping ${name} (PID: ${pid})..."
        kill -15 $pid 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}→${NC} Force stopping ${name}..."
            kill -9 $pid 2>/dev/null || true
        fi
        
        if ! ps -p $pid > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} ${name} stopped"
            return 0
        else
            echo -e "${RED}✗${NC} Failed to stop ${name}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠${NC}  ${name} (PID: ${pid}) not running"
        return 0
    fi
}

# Function to kill all processes on a port
kill_port() {
    local port=$1
    local name=$2
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        PIDS=$(lsof -Pi :$port -sTCP:LISTEN -t)
        echo -e "${YELLOW}→${NC} Stopping ${name} on port ${port}..."
        for PID in $PIDS; do
            kill -9 $PID 2>/dev/null || true
        done
        echo -e "${GREEN}✓${NC} ${name} stopped"
    fi
}

# Read PIDs from file if it exists
if [ -f "$PID_FILE" ]; then
    echo -e "${YELLOW}→${NC} Reading PIDs from ${PID_FILE}..."
    PIDS=($(cat "$PID_FILE"))
    
    # Try to identify and stop services by PID
    for PID in "${PIDS[@]}"; do
        if ps -p $PID > /dev/null 2>&1; then
            CMD=$(ps -p $PID -o command= | head -n 1)
            if [[ $CMD == *"marketplace"* ]]; then
                kill_process $PID "Marketplace"
            elif [[ $CMD == *"serving"* ]]; then
                kill_process $PID "Serving"
            elif [[ $CMD == *"compute"* ]]; then
                kill_process $PID "Compute"
            else
                kill_process $PID "Service"
            fi
        fi
    done
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}✓${NC} PID file removed"
else
    echo -e "${YELLOW}⚠${NC}  No PID file found, will check ports..."
fi

echo ""
echo -e "${YELLOW}→${NC} Checking ports for any remaining processes..."

# Kill any remaining processes on known ports
MARKETPLACE_PORT=${MARKETPLACE_PORT:-8001}
SERVING_PORT=${SERVING_PORT:-8002}
COMPUTE_PORT=${COMPUTE_PORT:-8003}
FRONTEND_PORT=${FRONTEND_PORT:-3000}

kill_port $MARKETPLACE_PORT "Marketplace"
kill_port $SERVING_PORT "Serving"
kill_port $COMPUTE_PORT "Compute"

# Also check for individual component PIDs
for component in marketplace serving compute; do
    if [ -f "${component}/.${component}.pid" ]; then
        PID=$(cat "${component}/.${component}.pid")
        if ps -p $PID > /dev/null 2>&1; then
            kill_process $PID "$component"
        fi
        rm -f "${component}/.${component}.pid"
    fi
done

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All Services Stopped${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Show what's still running on our ports (if anything)
for port in $MARKETPLACE_PORT $SERVING_PORT $COMPUTE_PORT; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${YELLOW}⚠${NC}  Warning: Port ${port} still has active connections"
    fi
done

echo ""

