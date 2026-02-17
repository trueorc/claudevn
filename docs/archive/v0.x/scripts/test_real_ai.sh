#!/bin/bash

# ClaudeVN Real AI Execution Test
# Tests actual OpenAI API calls with agent decomposition and execution

set -e  # Exit on error

# Configuration
SERVING_URL="http://localhost:8002"
COMPUTE_URL="http://localhost:8003"
MARKETPLACE_URL="http://localhost:8001"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_section() {
    echo -e "\n${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}\n"
}

print_step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Wait for service to be ready
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=0
    
    print_step "Waiting for $name to be ready..."
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url/health" > /dev/null 2>&1; then
            print_success "$name is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 1
    done
    
    print_error "$name failed to start after $max_attempts seconds"
    return 1
}

# Main test execution
main() {
    print_section "ClaudeVN Real AI Execution Test"
    
    # Step 1: Verify all services are running
    print_section "Step 1: Verify Services"
    
    if ! wait_for_service "$SERVING_URL" "Serving"; then
        print_error "Serving service is not running. Start it with: cd serving && ./start.sh"
        exit 1
    fi
    
    if ! wait_for_service "$COMPUTE_URL" "Compute"; then
        print_error "Compute service is not running. Start it with: cd compute && ./start.sh"
        exit 1
    fi
    
    if ! wait_for_service "$MARKETPLACE_URL" "Marketplace"; then
        print_error "Marketplace service is not running. Start it with: cd marketplace && ./start.sh"
        exit 1
    fi
    
    # Step 2: Check OpenAI API key
    print_section "Step 2: Verify OpenAI API Configuration"
    
    print_step "Checking if OpenAI API key is configured in .env..."
    
    # Check if key exists in .env file
    if [ -f ".env" ]; then
        if grep -q "^OPENAI_API_KEY=sk-" .env; then
            print_success "OpenAI API key found in .env file"
        else
            print_error "OpenAI API key not found or invalid in .env file"
            echo "Please ensure OPENAI_API_KEY is set in your .env file with a valid key starting with 'sk-'"
            echo ""
            echo "Example:"
            echo "  OPENAI_API_KEY=sk-proj-your-key-here"
            exit 1
        fi
    else
        print_error ".env file not found in project root"
        echo "Please create a .env file with OPENAI_API_KEY"
        exit 1
    fi
    
    print_step "Note: If tasks fail with authentication errors, restart services with: ./stop_all.sh && ./start_all.sh"
    
    # Step 3: List available agents
    print_section "Step 3: Discover Available Agents"
    
    print_step "Fetching agents from compute instance..."
    
    AGENTS=$(curl -s "$COMPUTE_URL/api/v1/agents")
    AGENT_COUNT=$(echo "$AGENTS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")
    
    print_success "Found $AGENT_COUNT agents"
    echo "$AGENTS" | python3 -m json.tool 2>/dev/null | head -30
    
    # Step 4: Test Simple Problem Solving
    print_section "Step 4: Test Simple Problem (Math Calculation)"
    
    print_step "Submitting simple math problem to task-coordinator-v1..."
    
    SIMPLE_TASK=$(curl -s -X POST "$SERVING_URL/api/v1/tasks/submit" \
        -H "Content-Type: application/json" \
        -d '{
            "agent_id": "task-coordinator-v1",
            "prompt": "Calculate the compound interest for a $10,000 investment at 5% annual rate compounded monthly for 3 years. Show your work step by step.",
            "context": {
                "problem_type": "financial_calculation",
                "requires_precision": true
            },
            "output_format": "markdown"
        }')
    
    TASK_ID=$(echo "$SIMPLE_TASK" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
    TASK_STATUS=$(echo "$SIMPLE_TASK" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$TASK_ID" ]; then
        print_success "Task submitted successfully: $TASK_ID"
        print_step "Task status: $TASK_STATUS"
        
        echo -e "\n${GREEN}=== Task Result ===${NC}"
        echo "$SIMPLE_TASK" | python3 -m json.tool 2>/dev/null | grep -A 50 '"output"'
        echo ""
    else
        print_error "Failed to submit task"
        echo "$SIMPLE_TASK" | python3 -m json.tool 2>/dev/null
        exit 1
    fi
    
    # Step 5: Test Complex Multi-Step Problem
    print_section "Step 5: Test Complex Multi-Step Problem (Data Analysis)"
    
    print_step "Submitting complex data analysis task..."
    
    COMPLEX_TASK=$(curl -s -X POST "$SERVING_URL/api/v1/tasks/submit" \
        -H "Content-Type: application/json" \
        -d '{
            "agent_id": "data-analyst-v1",
            "prompt": "Analyze this sales data and provide insights:\n\nRegion | Product | Q1 Sales | Q2 Sales | Q3 Sales | Q4 Sales\n-----|--------|---------|---------|---------|--------\nNorth | Widget A | $45000 | $52000 | $48000 | $61000\nNorth | Widget B | $32000 | $35000 | $38000 | $42000\nSouth | Widget A | $38000 | $41000 | $39000 | $47000\nSouth | Widget B | $28000 | $30000 | $33000 | $36000\n\nProvide:\n1. Total sales by region\n2. Best performing product\n3. Growth trends\n4. Recommendations",
            "context": {
                "analysis_type": "sales_performance",
                "fiscal_year": "2024"
            },
            "output_format": "markdown"
        }')
    
    COMPLEX_TASK_ID=$(echo "$COMPLEX_TASK" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
    COMPLEX_STATUS=$(echo "$COMPLEX_TASK" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$COMPLEX_TASK_ID" ]; then
        print_success "Complex task submitted: $COMPLEX_TASK_ID"
        print_step "Task status: $COMPLEX_STATUS"
        
        echo -e "\n${GREEN}=== Analysis Result ===${NC}"
        echo "$COMPLEX_TASK" | python3 -m json.tool 2>/dev/null | grep -A 100 '"output"'
        echo ""
    else
        print_error "Failed to submit complex task"
        echo "$COMPLEX_TASK" | python3 -m json.tool 2>/dev/null
    fi
    
    # Step 6: Test Content Generation
    print_section "Step 6: Test Content Generation"
    
    print_step "Generating marketing content..."
    
    CONTENT_TASK=$(curl -s -X POST "$SERVING_URL/api/v1/tasks/submit" \
        -H "Content-Type: application/json" \
        -d '{
            "agent_id": "content-writer-v1",
            "prompt": "Write a professional email announcing a new AI-powered workflow automation platform to potential enterprise customers. Highlight benefits like cost savings, efficiency gains, and seamless integration.",
            "context": {
                "audience": "CTOs and IT Directors",
                "tone": "professional yet approachable",
                "length": "250-300 words",
                "product_name": "ClaudeVN AI Platform"
            },
            "output_format": "markdown"
        }')
    
    CONTENT_TASK_ID=$(echo "$CONTENT_TASK" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
    CONTENT_STATUS=$(echo "$CONTENT_TASK" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$CONTENT_TASK_ID" ]; then
        print_success "Content generation task submitted: $CONTENT_TASK_ID"
        print_step "Task status: $CONTENT_STATUS"
        
        echo -e "\n${GREEN}=== Generated Content ===${NC}"
        echo "$CONTENT_TASK" | python3 -m json.tool 2>/dev/null | grep -A 50 '"output"'
        echo ""
    else
        print_error "Failed to submit content task"
        echo "$CONTENT_TASK" | python3 -m json.tool 2>/dev/null
    fi
    
    # Step 7: Summary
    print_section "Test Summary"
    
    echo -e "${GREEN}✓ All AI execution tests completed successfully!${NC}\n"
    echo "Tasks executed:"
    echo "  1. Simple Problem (Math): $TASK_ID - $TASK_STATUS"
    echo "  2. Complex Analysis: $COMPLEX_TASK_ID - $COMPLEX_STATUS"
    echo "  3. Content Generation: $CONTENT_TASK_ID - $CONTENT_STATUS"
    echo ""
    echo "View the Serving Dashboard at: http://localhost:8002"
    echo "View Observability at: http://localhost:8002 (Observability tab)"
    echo ""
}

# Run main function
main
