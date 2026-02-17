#!/bin/bash

# ClaudeVN Serving Component - Stop Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${SERVING_PORT:-8002}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ClaudeVN Serving Component - Stop${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Stop by PID file
if [ -f "serving.pid" ]; then
    PID=$(cat serving.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping serving component (PID: $PID)..."
        kill $PID
        sleep 2
        
        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}Force stopping...${NC}"
            kill -9 $PID
        fi
        
        rm serving.pid
        echo -e "${GREEN}✓ Serving component stopped${NC}"
    else
        echo -e "${YELLOW}Process not running (stale PID file)${NC}"
        rm serving.pid
    fi
else
    # Try to find by port
    PID=$(lsof -ti:$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Stopping process on port $PORT (PID: $PID)..."
        kill $PID
        sleep 2
        
        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}Force stopping...${NC}"
            kill -9 $PID
        fi
        
        echo -e "${GREEN}✓ Serving component stopped${NC}"
    else
        echo "Serving component not running"
    fi
fi

echo ""

