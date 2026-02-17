#!/bin/bash

# ClaudeVN Platform - Unit Test Summary Runner
# Runs all tier 1 unit tests and outputs a single summary line per component
#
# Usage: ./scripts/run_unit_summary.sh
#
# Output format:
#   [PASS] serving:     45 passed in 1.23s
#   [FAIL] marketplace: 30 passed, 2 failed in 0.89s
#   [PASS] compute:     18 passed in 0.56s
#   [PASS] shared:      12 passed in 0.34s

set -o pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="${PROJECT_ROOT}/.venv"

# Check virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}Error: Virtual environment not found at ${VENV_PATH}${NC}"
    exit 1
fi

PYTEST_CMD="${VENV_PATH}/bin/pytest"

# Check pytest is installed
if ! "${VENV_PATH}/bin/python" -c "import pytest" 2>/dev/null; then
    echo -e "${RED}Error: pytest not installed. Run: ./scripts/run_unit_tests.sh --install${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

# Track overall status
OVERALL_EXIT=0
declare -a RESULTS

# Run tests for a component and capture summary
run_component() {
    local name=$1
    local test_path=$2
    local pythonpath=$3
    local display_name=$4

    if [ ! -d "$test_path" ]; then
        RESULTS+=("${YELLOW}[SKIP]${NC} ${display_name}: no tests found")
        return 0
    fi

    # Run pytest and capture output
    local output
    output=$(PYTHONPATH="$pythonpath" "$PYTEST_CMD" -q --tb=no "$test_path" 2>&1)
    local exit_code=$?

    # Extract the summary line (e.g., "45 passed in 1.23s" or "30 passed, 2 failed in 0.89s")
    local summary
    summary=$(echo "$output" | grep -E "^[0-9]+ passed|^[0-9]+ failed" | tail -1)

    if [ -z "$summary" ]; then
        # Try to get any error info
        summary=$(echo "$output" | grep -E "error|Error|ERROR" | head -1)
        if [ -z "$summary" ]; then
            summary="no output"
        fi
    fi

    # Format the result
    if [ $exit_code -eq 0 ]; then
        RESULTS+=("${GREEN}[PASS]${NC} ${display_name}: ${summary}")
    else
        RESULTS+=("${RED}[FAIL]${NC} ${display_name}: ${summary}")
        OVERALL_EXIT=1
    fi
}

echo ""
echo -e "${BOLD}ClaudeVN Unit Test Summary (Tier 1)${NC}"
echo "==================================="
echo ""

# Run unit tests for each component
run_component "serving" "serving/tests/unit" "serving:shared" "serving    "
run_component "marketplace" "marketplace/tests/unit" "marketplace:shared" "marketplace"
run_component "compute" "compute/tests/unit" "compute:shared" "compute    "
run_component "shared" "shared/tests" "shared" "shared     "

# Print all results
for result in "${RESULTS[@]}"; do
    echo -e "$result"
done

echo ""
echo "==================================="

if [ $OVERALL_EXIT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}All unit tests passed${NC}"
else
    echo -e "${RED}${BOLD}Some unit tests failed${NC}"
fi

echo ""
exit $OVERALL_EXIT
