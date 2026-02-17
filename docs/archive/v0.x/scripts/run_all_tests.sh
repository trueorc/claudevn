#!/bin/bash
# ClaudeVN Complete Test Suite Runner
# Executes all integration and UAT tests

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
MARKETPLACE_URL="http://localhost:8001"
SERVING_URL="http://localhost:8002"
COMPUTE_URL="http://localhost:8003"
API_PREFIX="/api/v1"

# Test directories
COMPUTE_TESTS="compute"
SERVING_TESTS="serving/tests"
MARKETPLACE_TESTS="marketplace/tests"
SYSTEM_TESTS="tests"

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

print_header() {
    echo ""
    echo -e "${BLUE}${BOLD}========================================${NC}"
    echo -e "${BLUE}${BOLD}$1${NC}"
    echo -e "${BLUE}${BOLD}========================================${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${CYAN}▶ $1${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

check_service() {
    local name=$1
    local url=$2
    
    if curl -s -f "$url" > /dev/null 2>&1; then
        print_success "$name is online"
        return 0
    else
        print_error "$name is offline at $url"
        return 1
    fi
}

run_test_file() {
    local test_file=$1
    local test_name=$2
    
    print_section "Running: $test_name"
    
    if [ -f "$test_file" ]; then
        if python3 -m pytest "$test_file" -v --tb=short; then
            print_success "$test_name passed"
            ((PASSED_TESTS++))
            return 0
        else
            print_error "$test_name failed"
            ((FAILED_TESTS++))
            return 1
        fi
    else
        print_warning "$test_file not found, skipping"
        return 0
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

clear
print_header "ClaudeVN Complete Test Suite"

echo -e "${BOLD}Test Suite Overview:${NC}"
echo "  • Phase 1: Service Health Checks"
echo "  • Phase 2: API Integration Tests"
echo "  • Phase 3: System Integration Tests"
echo "  • Phase 4: User Acceptance Tests"
echo "  • Phase 5: Unit Tests (Week 1-6)"
echo ""

# ============================================================================
# Phase 1: Health Checks
# ============================================================================

print_header "Phase 1: Service Health Checks"

ALL_HEALTHY=true

check_service "Marketplace" "$MARKETPLACE_URL/health" || ALL_HEALTHY=false
check_service "Serving" "$SERVING_URL$API_PREFIX/health" || ALL_HEALTHY=false
check_service "Compute" "$COMPUTE_URL$API_PREFIX/health" || ALL_HEALTHY=false

if [ "$ALL_HEALTHY" = false ]; then
    print_error "Not all services are healthy. Please start all services first."
    echo ""
    echo "To start services:"
    echo "  ./start_all.sh"
    echo ""
    exit 1
fi

print_success "All services healthy and ready for testing"

# ============================================================================
# Phase 2: API Integration Tests
# ============================================================================

print_header "Phase 2: API Integration Tests"

print_info "Testing individual service APIs..."

# Compute API tests
run_test_file "$COMPUTE_TESTS/test_api_integration.py" "Compute API Integration"
((TOTAL_TESTS++))

# Serving API tests
run_test_file "$SERVING_TESTS/test_api_integration.py" "Serving API Integration"
((TOTAL_TESTS++))

# Marketplace API tests
run_test_file "$MARKETPLACE_TESTS/test_api_integration.py" "Marketplace API Integration"
((TOTAL_TESTS++))

# ============================================================================
# Phase 3: System Integration Tests
# ============================================================================

print_header "Phase 3: System Integration Tests"

print_info "Testing cross-service communication and workflows..."

run_test_file "$SYSTEM_TESTS/test_system_integration.py" "System Integration"
((TOTAL_TESTS++))

# ============================================================================
# Phase 4: User Acceptance Tests
# ============================================================================

print_header "Phase 4: User Acceptance Tests"

print_info "Running end-to-end user scenarios..."

run_test_file "$SYSTEM_TESTS/test_user_scenarios.py" "User Scenarios (UAT)"
((TOTAL_TESTS++))

# ============================================================================
# Phase 5: Unit Tests (Week 1-6 Implementation)
# ============================================================================

print_header "Phase 5: Unit Tests (Week 1-6)"

print_info "Running implementation unit tests..."

# Week 1: Conversation loops
if [ -f "$COMPUTE_TESTS/test_conversation_loop.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_conversation_loop.py" "Week 1: Conversation Loops"
    ((TOTAL_TESTS++))
fi

# Week 2: Blocker handling
if [ -f "$COMPUTE_TESTS/test_blocker_creates_activity.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_blocker_creates_activity.py" "Week 2: Blocker Handling"
    ((TOTAL_TESTS++))
fi

# Week 3: Consistency detection
if [ -f "$COMPUTE_TESTS/test_consistency_detection.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_consistency_detection.py" "Week 3: Consistency Detection"
    ((TOTAL_TESTS++))
fi

# Week 4: Map evolution
if [ -f "$COMPUTE_TESTS/test_map_evolution.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_map_evolution.py" "Week 4: Map Evolution"
    ((TOTAL_TESTS++))
fi

# Week 5: Result synthesis
if [ -f "$COMPUTE_TESTS/test_result_synthesis.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_result_synthesis.py" "Week 5: Result Synthesis"
    ((TOTAL_TESTS++))
fi

# Week 6: Complete workflow
if [ -f "$COMPUTE_TESTS/test_complete_emergent_workflow.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_complete_emergent_workflow.py" "Week 6: Complete Workflow"
    ((TOTAL_TESTS++))
fi

# Additional unit tests
if [ -f "$COMPUTE_TESTS/test_tool_execution.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_tool_execution.py" "Tool Execution"
    ((TOTAL_TESTS++))
fi

if [ -f "$COMPUTE_TESTS/test_integration_tool_execution.py" ]; then
    run_test_file "$COMPUTE_TESTS/test_integration_tool_execution.py" "Integration Tool Execution"
    ((TOTAL_TESTS++))
fi

# ============================================================================
# Test Summary
# ============================================================================

print_header "Test Summary"

echo -e "${BOLD}Results:${NC}"
echo -e "  Total Test Suites: ${BOLD}$TOTAL_TESTS${NC}"
echo -e "  Passed: ${GREEN}${BOLD}$PASSED_TESTS${NC}"
echo -e "  Failed: ${RED}${BOLD}$FAILED_TESTS${NC}"
echo ""

SKIPPED=$((TOTAL_TESTS - PASSED_TESTS - FAILED_TESTS))
if [ $SKIPPED -gt 0 ]; then
    echo -e "  Skipped: ${YELLOW}${BOLD}$SKIPPED${NC}"
    echo ""
fi

# Calculate success rate
if [ $TOTAL_TESTS -gt 0 ]; then
    SUCCESS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo -e "${BOLD}Success Rate: $SUCCESS_RATE%${NC}"
else
    echo -e "${YELLOW}No tests were run${NC}"
fi

echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    print_success "All tests passed! System ready for user testing. ✨"
    echo ""
    echo "Next steps:"
    echo "  1. Review test results above"
    echo "  2. Check docs/UAT_TEST_PLAN.md for user testing guide"
    echo "  3. Begin user acceptance testing"
    echo ""
    exit 0
else
    print_error "Some tests failed. Please review errors above."
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check service logs: ./status.sh"
    echo "  2. Review failed test output above"
    echo "  3. Ensure all services are running: ./start_all.sh"
    echo "  4. Check compute/logs/, serving/logs/, marketplace/logs/"
    echo ""
    exit 1
fi
