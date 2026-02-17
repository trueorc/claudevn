#!/bin/bash

# ClaudeVN Platform - Status Check

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
MARKETPLACE_PORT=${MARKETPLACE_PORT:-8001}
SERVING_PORT=${SERVING_PORT:-8002}
COMPUTE_PORT=${COMPUTE_PORT:-8003}
FRONTEND_PORT=${FRONTEND_PORT:-3000}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN Platform - Status${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check service health
check_service() {
    local name=$1
    local port=$2
    local health_endpoint=$3
    
    # Check if port is in use
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        local pid=$(lsof -Pi :$port -sTCP:LISTEN -t | head -n 1)
        
        # Try health check
        if [ -n "$health_endpoint" ]; then
            if curl -s -f "http://localhost:${port}${health_endpoint}" > /dev/null 2>&1; then
                local health=$(curl -s "http://localhost:${port}${health_endpoint}" 2>/dev/null)
                echo -e "  ${GREEN}●${NC} ${name}"
                echo -e "    Status:  ${GREEN}Running${NC}"
                echo -e "    Port:    ${port}"
                echo -e "    PID:     ${pid}"
                echo -e "    Health:  ${GREEN}Healthy${NC}"
                return 0
            else
                echo -e "  ${YELLOW}●${NC} ${name}"
                echo -e "    Status:  ${YELLOW}Running (no health check)${NC}"
                echo -e "    Port:    ${port}"
                echo -e "    PID:     ${pid}"
                return 1
            fi
        else
            echo -e "  ${GREEN}●${NC} ${name}"
            echo -e "    Status:  ${GREEN}Running${NC}"
            echo -e "    Port:    ${port}"
            echo -e "    PID:     ${pid}"
            return 0
        fi
    else
        echo -e "  ${RED}○${NC} ${name}"
        echo -e "    Status:  ${RED}Not Running${NC}"
        echo -e "    Port:    ${port} (available)"
        return 1
    fi
}

echo -e "${CYAN}Services:${NC}"
echo ""

check_service "Marketplace" $MARKETPLACE_PORT "/api/v1/health"
echo ""

check_service "Serving" $SERVING_PORT "/health"
echo ""

check_service "Compute" $COMPUTE_PORT "/health"
echo ""

# Check frontend (integrated into marketplace on port 8001)
if [ -f "marketplace/frontend/dist/index.html" ]; then
    echo -e "  ${GREEN}●${NC} Frontend (Integrated)"
    echo -e "    Status:  ${GREEN}Built${NC}"
    echo -e "    URL:     http://localhost:${MARKETPLACE_PORT}"
    echo -e "    Dev:     cd marketplace/frontend && npm run dev (port ${FRONTEND_PORT})"
else
    echo -e "  ${YELLOW}○${NC} Frontend (Integrated)"
    echo -e "    Status:  ${YELLOW}Not Built${NC}"
    echo -e "    Build:   cd marketplace && ./build_frontend.sh"
    echo -e "    Dev:     cd marketplace/frontend && npm run dev (port ${FRONTEND_PORT})"
fi

echo ""
echo -e "${BLUE}========================================${NC}"

# Quick stats if marketplace is running
if curl -s -f "http://localhost:${MARKETPLACE_PORT}/api/v1/stats" > /dev/null 2>&1; then
    echo ""
    echo -e "${CYAN}Marketplace Stats:${NC}"
    
    stats=$(curl -s "http://localhost:${MARKETPLACE_PORT}/api/v1/stats" 2>/dev/null)
    
    if [ -n "$stats" ]; then
        total_agents=$(echo "$stats" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['agents']['total'])" 2>/dev/null || echo "?")
        coordinating=$(echo "$stats" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['agents']['coordinating'])" 2>/dev/null || echo "?")
        specialized=$(echo "$stats" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['agents']['specialized'])" 2>/dev/null || echo "?")
        
        echo -e "  Total Agents:        ${total_agents}"
        echo -e "  Coordinating Agents: ${coordinating}"
        echo -e "  Specialized Agents:  ${specialized}"
    fi
    echo ""
    echo -e "${BLUE}========================================${NC}"
fi

# Show logs location
echo ""
echo -e "${CYAN}Logs:${NC}"
if [ -d "logs" ]; then
    echo -e "  Location: ./logs/"
    echo -e "  View all: ${YELLOW}tail -f logs/*.log${NC}"
else
    echo -e "  ${YELLOW}No logs directory found${NC}"
fi

echo ""
echo -e "${CYAN}Management:${NC}"
echo -e "  Start all:  ${YELLOW}./start_all.sh${NC}"
echo -e "  Stop all:   ${YELLOW}./stop_all.sh${NC}"
echo -e "  Status:     ${YELLOW}./status.sh${NC}"

echo ""

