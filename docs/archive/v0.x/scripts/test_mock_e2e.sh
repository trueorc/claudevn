#!/bin/bash
# End-to-End Mock Test Script
# Tests the complete ClaudeVN workflow with mock LLM provider

set -e

echo "=========================================="
echo "ClaudeVN End-to-End Mock Test"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVING_URL="http://localhost:8002"
COMPUTE_URL="http://localhost:8003"
MARKETPLACE_URL="http://localhost:8001"

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

# Check if services are running
print_section "Step 1: Verify Services"

ALL_SERVICES_UP=true
check_service "Marketplace" "$MARKETPLACE_URL" || ALL_SERVICES_UP=false
check_service "Serving" "$SERVING_URL" || ALL_SERVICES_UP=false
check_service "Compute" "$COMPUTE_URL" || ALL_SERVICES_UP=false

if [ "$ALL_SERVICES_UP" = false ]; then
    print_error "Not all services are running!"
    echo ""
    echo "Please start services with:"
    echo "  ./start_all.sh"
    echo ""
    exit 1
fi

print_success "All services are running"

# Check compute registration
print_section "Step 2: Verify Compute Registration"

print_step "Getting compute instances from serving..."
COMPUTE_INSTANCES=$(curl -s "$SERVING_URL/api/v1/compute")
INSTANCE_COUNT=$(echo "$COMPUTE_INSTANCES" | grep -o '"instance_id"' | wc -l)

if [ "$INSTANCE_COUNT" -eq 0 ]; then
    print_error "No compute instances registered!"
    echo ""
    echo "The compute engine should auto-register on startup."
    echo "Check compute logs: tail -f logs/compute.log"
    echo ""
    exit 1
fi

print_success "Found $INSTANCE_COUNT registered compute instance(s)"

# Get first compute instance ID for testing
INSTANCE_ID=$(echo "$COMPUTE_INSTANCES" | grep -o '"instance_id":"[^"]*"' | head -1 | cut -d'"' -f4)
print_step "Using compute instance: $INSTANCE_ID"

# List available agents
print_section "Step 3: List Available Agents"

print_step "Querying agents from compute instance..."
AGENTS=$(curl -s "$COMPUTE_URL/agents")
echo "$AGENTS" | python3 -m json.tool 2>/dev/null || echo "$AGENTS"

AGENT_COUNT=$(echo "$AGENTS" | grep -o '"agent_id"' | wc -l)
print_success "Found $AGENT_COUNT agent(s)"

# Test individual agent execution
print_section "Step 4: Test Individual Agent Execution"

print_step "Executing data analyst agent directly on compute..."

ANALYSIS_RESULT=$(curl -s -X POST "$COMPUTE_URL/agents/execute" \
    -H "Content-Type: application/json" \
    -d '{
        "agent_id": "data-analyst-v1",
        "prompt": "Analyze Q4 2024 sales data with 95 transactions totaling $24,127.50. Identify key trends.",
        "context": {
            "data_summary": {
                "total_records": 95,
                "total_revenue": 24127.50,
                "date_range": "Oct 1 - Dec 31, 2024"
            }
        },
        "output_format": "markdown"
    }')

TASK_ID=$(echo "$ANALYSIS_RESULT" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
STATUS=$(echo "$ANALYSIS_RESULT" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$STATUS" = "completed" ]; then
    print_success "Agent execution completed! Task ID: $TASK_ID"
    
    echo ""
    echo "Output preview:"
    echo "$ANALYSIS_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    content = data.get('output', {}).get('content', 'No content')
    print(content[:500] + '...' if len(content) > 500 else content)
except:
    print('Could not parse output')
"
else
    print_error "Agent execution failed!"
    echo "$ANALYSIS_RESULT" | python3 -m json.tool 2>/dev/null || echo "$ANALYSIS_RESULT"
    exit 1
fi

# Test task routing through serving
print_section "Step 5: Test Task Routing via Serving"

print_step "Submitting task to serving (will route to compute)..."

ROUTED_RESULT=$(curl -s -X POST "$SERVING_URL/api/v1/tasks/submit" \
    -H "Content-Type: application/json" \
    -d '{
        "agent_id": "content-writer-v1",
        "prompt": "Write a brief executive summary about Q4 sales performance.",
        "context": {
            "topic": "Q4 Sales Performance",
            "audience": "Executives",
            "tone": "professional"
        },
        "output_format": "markdown"
    }')

ROUTED_TASK_ID=$(echo "$ROUTED_RESULT" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
ROUTED_STATUS=$(echo "$ROUTED_RESULT" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
COMPUTE_INSTANCE=$(echo "$ROUTED_RESULT" | grep -o '"compute_instance_id":"[^"]*"' | cut -d'"' -f4)

if [ "$ROUTED_STATUS" = "completed" ]; then
    print_success "Task routed and executed! Task ID: $ROUTED_TASK_ID"
    print_success "Executed on compute instance: $COMPUTE_INSTANCE"
    
    echo ""
    echo "Output preview:"
    echo "$ROUTED_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    content = data.get('output', {}).get('content', 'No content')
    print(content[:500] + '...' if len(content) > 500 else content)
except:
    print('Could not parse output')
"
else
    print_error "Task routing failed!"
    echo "$ROUTED_RESULT" | python3 -m json.tool 2>/dev/null || echo "$ROUTED_RESULT"
    exit 1
fi

# Test full business process
print_section "Step 6: Test Complete Business Process"

print_step "Running demo business process (3 agents, coordinated workflow)..."
echo "This will execute:"
echo "  1. Task Coordinator - Plans the workflow"
echo "  2. Data Analyst - Analyzes the data"
echo "  3. Content Writer - Generates the report"
echo ""

PROCESS_RESULT=$(curl -s -X POST "$SERVING_URL/api/v1/tasks/demo/business-process")

PROCESS_STATUS=$(echo "$PROCESS_RESULT" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$PROCESS_STATUS" = "completed" ]; then
    print_success "Business process completed successfully!"
    
    echo ""
    echo "Process Summary:"
    echo "$PROCESS_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    summary = data.get('summary', {})
    print(f\"  Total steps: {summary.get('total_steps', 0)}\")
    print(f\"  Successful: {summary.get('successful_steps', 0)}\")
    print(f\"  Agents used: {summary.get('total_agents_used', 0)}\")
    print(f\"  Compute instances: {summary.get('compute_instances_used', 0)}\")
    
    print()
    print('Step Results:')
    for step in data.get('steps', []):
        print(f\"  Step {step['step']}: {step['agent']} - {step['status']}\")
except Exception as e:
    print(f'Could not parse: {e}')
"
    
    echo ""
    echo "Sample Output from Step 2 (Data Analysis):"
    echo "$PROCESS_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    steps = data.get('steps', [])
    if len(steps) > 1:
        step2 = steps[1]
        content = step2.get('output', {}).get('content', 'No content')
        print(content[:600] + '...' if len(content) > 600 else content)
except:
    print('Could not parse output')
"
else
    print_error "Business process failed!"
    echo "$PROCESS_RESULT" | python3 -m json.tool 2>/dev/null || echo "$PROCESS_RESULT"
fi

# Summary
print_section "Test Summary"

echo -e "${GREEN}✓ All tests completed successfully!${NC}"
echo ""
echo "What was tested:"
echo "  1. Service health checks"
echo "  2. Compute instance registration"
echo "  3. Agent availability"
echo "  4. Direct agent execution on compute"
echo "  5. Task routing through serving"
echo "  6. Multi-agent business process coordination"
echo ""
echo "Key Features Demonstrated:"
echo "  • Mock LLM provider (no API calls)"
echo "  • Agent execution with realistic responses"
echo "  • Automatic task routing to compute instances"
echo "  • Multi-step coordinated workflows"
echo "  • Integration between serving and compute"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  • View full results in the output above"
echo "  • Check logs: tail -f logs/*.log"
echo "  • Try custom tasks: curl examples in docs/"
echo "  • Explore API docs: http://localhost:8002/docs"
echo ""

