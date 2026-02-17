#!/bin/bash
# Observability Test Script with Artificial Delays
# Tests the complete observability system with visible delays to see real-time updates

set -e

echo "=========================================="
echo "ClaudeVN Observability Test"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
SERVING_URL="http://localhost:8002"
COMPUTE_URL="http://localhost:8003"
FRONTEND_URL="http://localhost:8002"  # Frontend is served from serving component
AGENT_DELAY=5  # 5 second delay for each agent execution

# Helper functions
check_service() {
    local name=$1
    local url=$2
    echo -n "Checking $name... "
    if curl -s -f "$url/health" > /dev/null 2>&1 || curl -s -f "$url/api/v1/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Online${NC}"
        return 0
    else
        echo -e "${RED}✗ Offline${NC}"
        return 1
    fi
}

print_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_step() {
    echo -e "${YELLOW}➜ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${MAGENTA}ℹ $1${NC}"
}

# Main script
print_section "OBSERVABILITY TESTING WITH VISIBLE DELAYS"

echo "This script will:"
echo "  1. Stop all services"
echo "  2. Start services with ${AGENT_DELAY}s agent execution delays"
echo "  3. Create a test session with multiple activities"
echo "  4. Give you time to observe real-time updates in the UI"
echo ""
echo -e "${YELLOW}Important: Have your browser ready at ${FRONTEND_URL}${NC}"
echo ""
read -p "Press Enter to continue..."

# Stop all services
print_section "Step 1: Stopping All Services"
print_step "Shutting down any running services..."
./stop_all.sh 2>/dev/null || true
sleep 2
print_success "Services stopped"

# Start Marketplace
print_section "Step 2: Starting Marketplace"
print_step "Starting marketplace service..."
cd marketplace
./start.sh > /dev/null 2>&1 &
cd ..
sleep 3
if check_service "Marketplace" "http://localhost:8001"; then
    print_success "Marketplace started"
else
    print_error "Failed to start Marketplace"
    exit 1
fi

# Start Serving
print_section "Step 3: Starting Serving"
print_step "Starting serving service..."
cd serving
./start.sh > /dev/null 2>&1 &
cd ..
sleep 3
if check_service "Serving" "$SERVING_URL"; then
    print_success "Serving started"
else
    print_error "Failed to start Serving"
    exit 1
fi

# Start Compute with delay enabled
print_section "Step 4: Starting Compute with ${AGENT_DELAY}s Execution Delay"
print_step "Configuring compute with artificial delays for observability testing..."

# Set environment variable and start compute
export COMPUTE_AGENT_EXECUTION_DELAY=$AGENT_DELAY

print_info "COMPUTE_AGENT_EXECUTION_DELAY=${AGENT_DELAY} seconds"
print_info "This will make each agent take ~${AGENT_DELAY} seconds to execute"

cd compute
./start.sh > /dev/null 2>&1 &
cd ..

# Wait longer for compute to initialize
sleep 5

if check_service "Compute" "$COMPUTE_URL"; then
    print_success "Compute started with ${AGENT_DELAY}s delay"
else
    print_error "Failed to start Compute"
    print_error "Check logs: tail -20 compute/logs/compute.log"
    tail -20 compute/logs/compute.log 2>/dev/null || true
    exit 1
fi

# Wait for compute to register
print_step "Waiting for compute to register..."
sleep 2

# Check compute registration
COMPUTE_INSTANCES=$(curl -s "$SERVING_URL/api/v1/compute")
INSTANCE_COUNT=$(echo "$COMPUTE_INSTANCES" | grep -o '"instance_id"' | wc -l)

if [ "$INSTANCE_COUNT" -eq 0 ]; then
    print_error "No compute instances registered!"
    exit 1
fi

print_success "Compute instance registered and ready"

# Create a test session
print_section "Step 5: Creating Test Session"
print_step "Creating a facilitated process session with multiple activities..."

SESSION_RESULT=$(curl -s -X POST "$SERVING_URL/api/v1/sessions/facilitated" \
    -H "Content-Type: application/json" \
    -d '{
        "business_goal": "Analyze Q4 2024 sales performance and create an executive report with recommendations",
        "context": {
            "data_available": "Q4 2024 sales transactions",
            "total_revenue": "$24,127.50",
            "transaction_count": 95,
            "date_range": "Oct 1 - Dec 31, 2024"
        },
        "coordination_mode": "facilitated"
    }')

SESSION_ID=$(echo "$SESSION_RESULT" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$SESSION_ID" ]; then
    print_error "Failed to create session!"
    echo "$SESSION_RESULT" | python3 -m json.tool 2>/dev/null || echo "$SESSION_RESULT"
    exit 1
fi

print_success "Session created: $SESSION_ID"

# Show the observability dashboard URL
print_section "Step 6: Observe in Real-Time!"

echo ""
echo -e "${MAGENTA}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║                                                                ║${NC}"
echo -e "${MAGENTA}║  🎯 NOW: Open your browser and view the observability UI      ║${NC}"
echo -e "${MAGENTA}║                                                                ║${NC}"
echo -e "${MAGENTA}║  Dashboard:  ${FRONTEND_URL}  (click Observability tab)     ║${NC}"
echo -e "${MAGENTA}║  Direct URL: ${FRONTEND_URL}/#observability                 ║${NC}"
echo -e "${MAGENTA}║                                                                ║${NC}"
echo -e "${MAGENTA}║  Each activity will take ~${AGENT_DELAY} seconds, giving you time    ║${NC}"
echo -e "${MAGENTA}║  to see:                                                       ║${NC}"
echo -e "${MAGENTA}║    • Real-time status changes                                  ║${NC}"
echo -e "${MAGENTA}║    • Activity progress                                         ║${NC}"
echo -e "${MAGENTA}║    • Timeline of events                                        ║${NC}"
echo -e "${MAGENTA}║    • Workflow visualization                                    ║${NC}"
echo -e "${MAGENTA}║    • Resource utilization                                      ║${NC}"
echo -e "${MAGENTA}║                                                                ║${NC}"
echo -e "${MAGENTA}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

read -p "Press Enter when you have the UI open and are ready to start..."

# Execute the session
print_section "Step 7: Executing Facilitated Process"
print_step "Starting facilitated process execution..."
print_info "Watch the UI for real-time updates as activities execute!"
echo ""

# Start the process
EXECUTION_RESULT=$(curl -s -X POST "$SERVING_URL/api/v1/sessions/$SESSION_ID/execute")

EXECUTION_STATUS=$(echo "$EXECUTION_RESULT" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$EXECUTION_STATUS" = "in_progress" ] || [ "$EXECUTION_STATUS" = "completed" ]; then
    print_success "Session execution started!"
    
    # Poll for completion
    print_step "Monitoring session progress..."
    COMPLETED=false
    MAX_WAIT=300  # 5 minutes max
    ELAPSED=0
    
    while [ "$COMPLETED" = false ] && [ $ELAPSED -lt $MAX_WAIT ]; do
        sleep 5
        ELAPSED=$((ELAPSED + 5))
        
        SESSION_STATUS=$(curl -s "$SERVING_URL/api/v1/sessions/$SESSION_ID")
        CURRENT_STATUS=$(echo "$SESSION_STATUS" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        
        if [ "$CURRENT_STATUS" = "completed" ] || [ "$CURRENT_STATUS" = "goal_met" ]; then
            COMPLETED=true
            print_success "Session completed!"
        elif [ "$CURRENT_STATUS" = "failed" ] || [ "$CURRENT_STATUS" = "blocked" ]; then
            print_error "Session $CURRENT_STATUS"
            COMPLETED=true
        else
            echo -e "${BLUE}  Status: $CURRENT_STATUS (${ELAPSED}s elapsed)${NC}"
        fi
    done
    
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        print_error "Timeout waiting for session completion"
    fi
else
    print_error "Failed to start session execution!"
    echo "$EXECUTION_RESULT" | python3 -m json.tool 2>/dev/null || echo "$EXECUTION_RESULT"
fi

# Show summary
print_section "Test Complete!"

echo ""
echo "What you should have observed:"
echo "  ✓ Real-time activity status updates"
echo "  ✓ Activities taking ~${AGENT_DELAY} seconds each"
echo "  ✓ Live timeline of events"
echo "  ✓ Workflow graph updating dynamically"
echo "  ✓ Resource utilization metrics"
echo ""
echo "Session Details:"
echo "  Session ID: $SESSION_ID"
echo "  View in UI: ${FRONTEND_URL}  (Observability tab → click your session)"
echo ""
echo "Observability Features Tested:"
echo "  • WebSocket real-time streaming"
echo "  • Activity state change events"
echo "  • Process map evolution"
echo "  • Timeline view with live updates"
echo "  • Workflow visualization"
echo "  • Resource monitoring"
echo ""

print_info "Services are still running with ${AGENT_DELAY}s delays enabled"
print_info "You can create more test sessions at: $SERVING_URL/docs"
echo ""
echo "To stop services: ./stop_all.sh"
echo "To restart without delays: ./start_all.sh"
echo ""


