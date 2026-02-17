#!/bin/bash

# ClaudeVN Platform - Tier 1 Unit Test Runner
# Runs fast, mocked unit tests from */tests/unit/ directories

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="${PROJECT_ROOT}/.venv"

# Default settings
COVERAGE=false
HTML_REPORT=false
VERBOSE=false
FAIL_FAST=false
SPECIFIC_PATH=""

usage() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}ClaudeVN - Tier 1 Unit Tests${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "Runs fast, mocked unit tests. No server required."
    echo ""
    echo "Usage: $0 [OPTIONS] [TEST_PATH]"
    echo ""
    echo "Options:"
    echo "  -c, --coverage     Enable coverage reporting"
    echo "  -h, --html         Generate HTML coverage report (implies -c)"
    echo "  -v, --verbose      Verbose output"
    echo "  -x, --fail-fast    Stop on first failure"
    echo "  -i, --install      Install test dependencies"
    echo "  --help             Show this help message"
    echo ""
    echo "Test Directories:"
    echo "  serving/tests/unit/      Serving service unit tests"
    echo "  marketplace/tests/unit/  Marketplace service unit tests"
    echo "  compute/tests/unit/      Compute service unit tests"
    echo "  shared/tests/            Shared library tests"
    echo ""
    echo "Examples:"
    echo "  $0                                    Run all unit tests"
    echo "  $0 -c                                 Run with coverage"
    echo "  $0 -v -x                              Verbose with fail-fast"
    echo "  $0 serving/tests/unit/test_models.py Run specific test file"
    echo ""
    echo "Test Tiers:"
    echo "  Tier 1 (this script): Unit tests - mocked, fast, no server required"
    echo "  Tier 2 (run_integration_tests.sh): Integration tests - require running services"
    echo ""
}

install_deps() {
    echo -e "${YELLOW}→${NC} Installing test dependencies..."
    "${VENV_PATH}/bin/pip" install pytest pytest-cov pytest-asyncio
    echo -e "${GREEN}✓${NC} Test dependencies installed"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -h|--html)
            COVERAGE=true
            HTML_REPORT=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -x|--fail-fast)
            FAIL_FAST=true
            shift
            ;;
        -i|--install)
            install_deps
            exit 0
            ;;
        --help)
            usage
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
        *)
            SPECIFIC_PATH="$1"
            shift
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN - Tier 1 Unit Tests${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}✗${NC} Virtual environment not found at ${VENV_PATH}"
    echo -e "${YELLOW}→${NC} Create it with: python3 -m venv .venv"
    exit 1
fi

# Check pytest is installed
if ! "${VENV_PATH}/bin/python" -c "import pytest" 2>/dev/null; then
    echo -e "${RED}✗${NC} pytest is not installed"
    echo -e "${YELLOW}→${NC} Install with: $0 --install"
    exit 1
fi

echo -e "${GREEN}✓${NC} Virtual environment found"
echo -e "${CYAN}→${NC} Tier: 1 (Unit tests only)"

cd "$PROJECT_ROOT"

# Build common pytest args
PYTEST_CMD="${VENV_PATH}/bin/pytest"
COMMON_ARGS=()

if [ "$VERBOSE" = true ]; then
    COMMON_ARGS+=("-v")
fi

if [ "$FAIL_FAST" = true ]; then
    COMMON_ARGS+=("-x")
fi

# Track overall exit code
OVERALL_EXIT=0

run_tests() {
    local service=$1
    local test_path=$2
    local pythonpath=$3

    if [ ! -d "$test_path" ]; then
        return 0
    fi

    echo ""
    echo -e "${CYAN}→${NC} Running ${service} unit tests..."

    local args=("${COMMON_ARGS[@]}")

    if [ "$COVERAGE" = true ]; then
        args+=("--cov=${service}" "--cov-report=term-missing" "--cov-append")
    fi

    args+=("$test_path")

    PYTHONPATH="$pythonpath" "$PYTEST_CMD" "${args[@]}" || OVERALL_EXIT=1
}

# If specific path provided, run just that
if [ -n "$SPECIFIC_PATH" ]; then
    echo -e "${CYAN}→${NC} Running: ${SPECIFIC_PATH}"

    # Determine which service based on path
    if [[ "$SPECIFIC_PATH" == serving/* ]]; then
        PYTHONPATH="serving:shared" "$PYTEST_CMD" "${COMMON_ARGS[@]}" "$SPECIFIC_PATH"
    elif [[ "$SPECIFIC_PATH" == marketplace/* ]]; then
        PYTHONPATH="marketplace:shared" "$PYTEST_CMD" "${COMMON_ARGS[@]}" "$SPECIFIC_PATH"
    elif [[ "$SPECIFIC_PATH" == compute/* ]]; then
        PYTHONPATH="compute:shared" "$PYTEST_CMD" "${COMMON_ARGS[@]}" "$SPECIFIC_PATH"
    elif [[ "$SPECIFIC_PATH" == shared/* ]]; then
        PYTHONPATH="shared" "$PYTEST_CMD" "${COMMON_ARGS[@]}" "$SPECIFIC_PATH"
    else
        "$PYTEST_CMD" "${COMMON_ARGS[@]}" "$SPECIFIC_PATH"
    fi
    EXIT_CODE=$?
else
    # Clear coverage data if coverage is enabled
    if [ "$COVERAGE" = true ]; then
        rm -f .coverage
        echo -e "${CYAN}→${NC} Coverage enabled"
    fi

    echo -e "${CYAN}→${NC} Running all unit tests"

    # Run tests for each service separately to avoid module name collisions
    run_tests "serving" "serving/tests/unit" "serving:shared"
    run_tests "marketplace" "marketplace/tests/unit" "marketplace:shared"
    run_tests "compute" "compute/tests/unit" "compute:shared"
    run_tests "shared" "shared/tests" "shared"

    EXIT_CODE=$OVERALL_EXIT

    # Generate final coverage report
    if [ "$COVERAGE" = true ] && [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo -e "${CYAN}→${NC} Combined coverage report:"
        "$PYTEST_CMD" --cov-report=term-missing --cov-report=html --cov=serving --cov=marketplace --cov=compute --collect-only -q 2>/dev/null || true
        if [ "$HTML_REPORT" = true ]; then
            echo -e "${CYAN}→${NC} HTML report: ${PROJECT_ROOT}/htmlcov/index.html"
        fi
    fi
fi

echo ""
echo -e "${BLUE}========================================${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All unit tests passed${NC}"
else
    echo -e "${RED}✗ Some unit tests failed${NC}"
fi

echo -e "${BLUE}========================================${NC}"
echo ""

exit $EXIT_CODE
