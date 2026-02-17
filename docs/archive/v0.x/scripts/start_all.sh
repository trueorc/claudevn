#!/bin/bash

# ClaudeVN Platform - Complete Development Environment Startup
# Starts all services: Marketplace, Serving, and Compute

set -e

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Configuration
MARKETPLACE_PORT=${MARKETPLACE_PORT:-8001}
SERVING_PORT=${SERVING_PORT:-8002}
COMPUTE_PORT=${COMPUTE_PORT:-8003}
FRONTEND_PORT=${FRONTEND_PORT:-3000}

LOG_DIR="./logs"
PID_FILE=".claudevn.pid"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN Platform - Development Environment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Create log directory
mkdir -p "$LOG_DIR"

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to kill process on port
kill_port() {
    local port=$1
    local service_name=$2
    
    if check_port $port; then
        echo -e "${RED}✗${NC} Port ${port} is in use (${service_name})"
        PIDS=$(lsof -Pi :$port -sTCP:LISTEN -t)
        
        echo -e "${YELLOW}→${NC} Killing existing processes: ${PIDS}"
        for PID in $PIDS; do
            kill -9 $PID 2>/dev/null || true
        done
        
        # Wait for port to be released
        sleep 2
        
        if check_port $port; then
            echo -e "${RED}✗${NC} Failed to free port ${port}"
            return 1
        fi
        
        echo -e "${GREEN}✓${NC} Port ${port} freed"
    else
        echo -e "${GREEN}✓${NC} Port ${port} is available"
    fi
    return 0
}

# Function to activate venv if it exists
activate_venv() {
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        echo -e "${GREEN}✓${NC} Using virtual environment (.venv)"
    fi
}

# Function to check if Python dependencies are installed
check_python_deps() {
    local dir=$1
    local component=$2
    
    if [ ! -f "$dir/requirements.txt" ]; then
        echo -e "${YELLOW}⚠${NC}  No requirements.txt found for ${component}"
        return 1
    fi
    
    # Quick check - just verify a key package
    case $component in
        "Marketplace")
            python3 -c "import fastapi; import email_validator" 2>/dev/null || return 1
            ;;
        "Serving")
            python3 -c "import fastapi" 2>/dev/null || return 1
            ;;
        "Compute")
            python3 -c "import fastapi" 2>/dev/null || return 1
            ;;
    esac
    return 0
}

# Function to install dependencies if needed
ensure_dependencies() {
    local dir=$1
    local component=$2
    
    if ! check_python_deps "$dir" "$component"; then
        echo -e "${YELLOW}→${NC} Installing ${component} dependencies..."
        cd "$dir"
        pip install -q -r requirements.txt 2>&1 | tee -a "../${LOG_DIR}/install.log" > /dev/null
        cd - > /dev/null
        echo -e "${GREEN}✓${NC} ${component} dependencies installed"
    else
        echo -e "${GREEN}✓${NC} ${component} dependencies are installed"
    fi
}

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 is not installed"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $(python3 --version | cut -d' ' -f2)"

# Activate virtual environment if it exists
activate_venv

# Load environment variables
if [ -f .env ]; then
    echo -e "${YELLOW}→${NC} Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check and free ports
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Checking Ports...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

kill_port $MARKETPLACE_PORT "Marketplace" || exit 1
kill_port $SERVING_PORT "Serving" || exit 1
kill_port $COMPUTE_PORT "Compute" || exit 1
kill_port $FRONTEND_PORT "Frontend" || true  # Don't fail if frontend port busy

# Ensure shared library is installed
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Checking Shared Library...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ -d "shared" ]; then
    if ! python3 -c "import claudevn_shared" 2>/dev/null; then
        echo -e "${YELLOW}→${NC} Installing shared library..."
        pip install -q -e shared/
        echo -e "${GREEN}✓${NC} Shared library installed"
    else
        echo -e "${GREEN}✓${NC} Shared library is installed"
    fi
fi

# Check dependencies for each component
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Checking Dependencies...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

ensure_dependencies "marketplace" "Marketplace"
ensure_dependencies "serving" "Serving"
ensure_dependencies "compute" "Compute"

# Build Frontend
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Building Frontend...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

build_frontend() {
    local component=$1
    local frontend_dir="$component/frontend"
    local component_name=$(echo "$component" | sed 's/.*/\u&/')  # Capitalize
    
    echo -e "${CYAN}→ Building ${component_name} frontend...${NC}"
    
    # Check if frontend directory exists
    if [ ! -d "$frontend_dir" ]; then
        echo -e "${YELLOW}⚠${NC}  ${component_name} frontend directory not found - skipping"
        return 1
    fi
    
    cd "$frontend_dir"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}→${NC} Installing ${component_name} frontend dependencies..."
        if npm install > /tmp/npm-install-${component}.log 2>&1; then
            echo -e "${GREEN}✓${NC} ${component_name} frontend dependencies installed"
        else
            echo -e "${RED}✗${NC} npm install failed (check /tmp/npm-install-${component}.log)"
            cd ../..
            return 1
        fi
    else
        echo -e "${GREEN}✓${NC} ${component_name} frontend dependencies are installed"
    fi
    
    # Build frontend if dist doesn't exist or is outdated
    if [ ! -d "dist" ] || [ ! -f "dist/index.html" ]; then
        echo -e "${YELLOW}→${NC} Building ${component_name} frontend for production..."
        if npm run build > /tmp/npm-build-${component}.log 2>&1; then
            echo -e "${GREEN}✓${NC} ${component_name} frontend built successfully"
        else
            echo -e "${RED}✗${NC} ${component_name} frontend build failed (check /tmp/npm-build-${component}.log)"
            return 1
        fi
    else
        # Check if source files are newer than dist
        if [ "src/App.jsx" -nt "dist/index.html" ] 2>/dev/null; then
            echo -e "${YELLOW}→${NC} Rebuilding ${component_name} frontend (source files changed)..."
            if npm run build > /tmp/npm-build-${component}.log 2>&1; then
                echo -e "${GREEN}✓${NC} ${component_name} frontend rebuilt successfully"
            else
                echo -e "${RED}✗${NC} ${component_name} frontend rebuild failed (check /tmp/npm-build-${component}.log)"
                return 1
            fi
        else
            echo -e "${GREEN}✓${NC} ${component_name} frontend is up to date"
        fi
    fi
    
    cd ../..
    return 0
}

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Node.js not found - skipping frontend builds"
    echo -e "${YELLOW}→${NC}  Services will run in API-only mode"
    echo -e "${YELLOW}→${NC}  To enable frontends: install Node.js 18+ from https://nodejs.org"
    FRONTENDS_BUILT=false
else
    echo -e "${GREEN}✓${NC} Node.js $(node --version)"
    
    # Check if npm is installed
    if ! command -v npm &> /dev/null; then
        echo -e "${YELLOW}⚠${NC}  npm not found - skipping frontend builds"
        FRONTENDS_BUILT=false
    else
        echo -e "${GREEN}✓${NC} npm $(npm --version)"
        echo ""
        
        # Build Marketplace frontend
        if build_frontend "marketplace"; then
            MARKETPLACE_FRONTEND_READY=true
        else
            MARKETPLACE_FRONTEND_READY=false
        fi
        
        echo ""
        
        # Build Serving frontend
        if build_frontend "serving"; then
            SERVING_FRONTEND_READY=true
        else
            SERVING_FRONTEND_READY=false
        fi
        
        if [ "$MARKETPLACE_FRONTEND_READY" = true ] || [ "$SERVING_FRONTEND_READY" = true ]; then
            FRONTENDS_BUILT=true
        else
            FRONTENDS_BUILT=false
        fi
    fi
fi

# Start services
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Starting Services...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Array to store PIDs
declare -a PIDS

# Start Marketplace
echo -e "${CYAN}→ Starting Marketplace Service...${NC}"
cd marketplace

# Ensure data directories exist
mkdir -p data/marketplace/{agents,tools,access_control,_metadata,users,organizations,memberships,sessions}

# Set environment variables
export MARKETPLACE_PORT=$MARKETPLACE_PORT
export MARKETPLACE_HOST=0.0.0.0
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Start the service (using main.py which imports app.py with all initialization)
# Use venv python3.11 directly (not symlink) to ensure dependencies are found
nohup /Users/mlyons/Development/claudevn/.venv/bin/python3.11 main.py > "../${LOG_DIR}/marketplace.log" 2>&1 &
MARKETPLACE_PID=$!
PIDS+=($MARKETPLACE_PID)
cd ..

# Wait a moment for initialization
sleep 3

# Check if it's actually running
if ps -p $MARKETPLACE_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Marketplace started (PID: ${MARKETPLACE_PID})"
else
    echo -e "${RED}✗${NC} Marketplace failed to start"
    echo -e "${YELLOW}→${NC} Check logs at: ${LOG_DIR}/marketplace.log"
    tail -20 "${LOG_DIR}/marketplace.log"
    exit 1
fi

# Start Serving
echo -e "${CYAN}→ Starting Serving Component...${NC}"
cd serving
if [ -f "app.py" ]; then
    # Create data directories if needed
    mkdir -p data/serving
    
    # Set environment variables with isolated PYTHONPATH
    export SERVING_PORT=$SERVING_PORT
    export SERVING_HOST=0.0.0.0
    
    # Start with isolated PYTHONPATH (serving directory only, not marketplace)
    PYTHONPATH="$(pwd)" nohup python3 -m uvicorn app:app --host 0.0.0.0 --port $SERVING_PORT --log-level info > "../${LOG_DIR}/serving.log" 2>&1 &
    SERVING_PID=$!
    PIDS+=($SERVING_PID)
    
    # Wait a moment for initialization
    sleep 2
    
    # Check if it's actually running
    if ps -p $SERVING_PID > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Serving started (PID: ${SERVING_PID})"
    else
        echo -e "${RED}✗${NC} Serving failed to start"
        echo -e "${YELLOW}→${NC} Check logs at: ${LOG_DIR}/serving.log"
        tail -20 "../${LOG_DIR}/serving.log"
        SERVING_PID=""
    fi
else
    echo -e "${YELLOW}⚠${NC}  Serving component not yet implemented (app.py not found)"
    SERVING_PID=""
fi
cd ..

# Start Compute
echo -e "${CYAN}→ Starting Compute Engine...${NC}"
cd compute
if [ -f "main.py" ]; then
    # Create data directories if needed
    mkdir -p data/compute
    
    # Set environment variables
    export COMPUTE_PORT=$COMPUTE_PORT
    export COMPUTE_HOST=0.0.0.0
    export PYTHONPATH="$(pwd):${PYTHONPATH}"
    
    # Start the service
    nohup python3 main.py > "../${LOG_DIR}/compute.log" 2>&1 &
    COMPUTE_PID=$!
    PIDS+=($COMPUTE_PID)
    
    # Wait a moment for initialization
    sleep 2
    
    # Check if it's actually running
    if ps -p $COMPUTE_PID > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Compute started (PID: ${COMPUTE_PID})"
    else
        echo -e "${RED}✗${NC} Compute failed to start"
        echo -e "${YELLOW}→${NC} Check logs at: ${LOG_DIR}/compute.log"
        tail -20 "../${LOG_DIR}/compute.log"
        COMPUTE_PID=""
    fi
else
    echo -e "${YELLOW}⚠${NC}  Compute component not yet implemented (main.py not found)"
    COMPUTE_PID=""
fi
cd ..

# Save PIDs
echo "${PIDS[@]}" > "$PID_FILE"

# Wait for services to initialize
echo ""
echo -e "${YELLOW}→${NC} Waiting for services to initialize..."
sleep 5

# Health checks
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Health Checks...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check Marketplace
if ps -p $MARKETPLACE_PID > /dev/null 2>&1; then
    if curl -s -f --connect-timeout 3 --max-time 5 "http://localhost:${MARKETPLACE_PORT}/api/v1/health" > /dev/null 2>&1; then
        MARKETPLACE_HEALTH=$(curl -s --connect-timeout 3 --max-time 5 "http://localhost:${MARKETPLACE_PORT}/api/v1/health" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "unknown")
        if [ "$MARKETPLACE_HEALTH" = "healthy" ]; then
            echo -e "${GREEN}✓${NC} Marketplace: healthy"
        else
            echo -e "${YELLOW}⚠${NC}  Marketplace: $MARKETPLACE_HEALTH"
        fi
    else
        echo -e "${YELLOW}⚠${NC}  Marketplace: initializing (check logs if this persists)"
    fi
else
    echo -e "${RED}✗${NC} Marketplace: failed to start (check logs)"
fi

# Check Serving
if [ -n "$SERVING_PID" ]; then
    if ps -p $SERVING_PID > /dev/null 2>&1; then
        if curl -s -f --connect-timeout 3 --max-time 5 "http://localhost:${SERVING_PORT}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Serving: healthy"
        else
            echo -e "${YELLOW}⚠${NC}  Serving: initializing (check logs if this persists)"
        fi
    else
        echo -e "${RED}✗${NC} Serving: failed to start (check logs)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Serving: not implemented yet"
fi

# Check Compute
if [ -n "$COMPUTE_PID" ]; then
    if ps -p $COMPUTE_PID > /dev/null 2>&1; then
        if curl -s -f --connect-timeout 3 --max-time 5 "http://localhost:${COMPUTE_PORT}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Compute: healthy"
        else
            echo -e "${YELLOW}⚠${NC}  Compute: initializing (check logs if this persists)"
        fi
    else
        echo -e "${RED}✗${NC} Compute: failed to start (check logs)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Compute: not implemented yet"
fi

# Display summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ ClaudeVN Platform Running${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${CYAN}Service Endpoints:${NC}"
echo ""

if ps -p $MARKETPLACE_PID > /dev/null 2>&1; then
    echo -e "  ${GREEN}Marketplace:${NC}"
    if [ "$MARKETPLACE_FRONTEND_READY" = true ]; then
        echo -e "    UI:     http://localhost:${MARKETPLACE_PORT}"
    fi
    echo -e "    API:    http://localhost:${MARKETPLACE_PORT}/api/v1"
    echo -e "    Health: http://localhost:${MARKETPLACE_PORT}/api/v1/health"
    echo -e "    Docs:   http://localhost:${MARKETPLACE_PORT}/docs"
    echo -e "    PID:    ${MARKETPLACE_PID}"
    echo ""
fi

if [ -n "$SERVING_PID" ] && ps -p $SERVING_PID > /dev/null 2>&1; then
    echo -e "  ${GREEN}Serving:${NC}"
    if [ "$SERVING_FRONTEND_READY" = true ]; then
        echo -e "    UI:     http://localhost:${SERVING_PORT}"
    fi
    echo -e "    API:    http://localhost:${SERVING_PORT}/api/v1"
    echo -e "    Docs:   http://localhost:${SERVING_PORT}/docs"
    echo -e "    Health: http://localhost:${SERVING_PORT}/api/v1/health"
    echo -e "    PID:    ${SERVING_PID}"
    echo ""
fi

if [ -n "$COMPUTE_PID" ] && ps -p $COMPUTE_PID > /dev/null 2>&1; then
    echo -e "  ${GREEN}Compute:${NC}"
    echo -e "    API:    http://localhost:${COMPUTE_PORT}"
    echo -e "    Health: http://localhost:${COMPUTE_PORT}/health"
    echo -e "    PID:    ${COMPUTE_PID}"
    echo ""
fi

if [ "$FRONTENDS_BUILT" != true ]; then
    echo -e "${CYAN}Frontend Development Mode (optional):${NC}"
    echo -e "  Marketplace: ${YELLOW}cd marketplace/frontend && npm run dev${NC}"
    echo -e "  Serving:     ${YELLOW}cd serving/frontend && npm run dev${NC}"
    echo ""
fi

echo -e "${CYAN}Logs:${NC}"
echo -e "  Marketplace: ${LOG_DIR}/marketplace.log"
if [ -n "$SERVING_PID" ]; then
    echo -e "  Serving:     ${LOG_DIR}/serving.log"
fi
if [ -n "$COMPUTE_PID" ]; then
    echo -e "  Compute:     ${LOG_DIR}/compute.log"
fi
echo ""

echo -e "${CYAN}Management:${NC}"
echo -e "  Stop all:    ${YELLOW}./stop_all.sh${NC}"
echo -e "  View logs:   ${YELLOW}tail -f ${LOG_DIR}/*.log${NC}"
echo -e "  Restart:     ${YELLOW}./stop_all.sh && ./start_all.sh${NC}"
echo ""

echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${CYAN}To view live logs:${NC} tail -f ${LOG_DIR}/*.log"
echo ""

