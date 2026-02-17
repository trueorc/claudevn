#!/bin/bash

# ClaudeVN Platform - Test Runner
# Runs unit tests with optional coverage reporting

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
TEST_PATH="serving/tests"
COV_PATH="serving"

usage() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}ClaudeVN - Test Runner${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS] [TEST_PATH]"
    echo ""
    echo "Options:"
    echo "  -c, --coverage     Enable coverage reporting"
    echo "  -h, --html         Generate HTML coverage report (implies -c)"
    echo "  -v, --verbose      Verbose output"
    echo "  -i, --install      Install test dependencies"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                           Run all serving tests"
    echo "  $0 -c                        Run with coverage"
    echo "  $0 -h                        Run with HTML coverage report"
    echo "  $0 -v serving/tests/test_models.py   Run specific test file"
    echo "  $0 -i                        Install pytest and coverage"
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
            TEST_PATH="$1"
            shift
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN - Test Runner${NC}"
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
echo -e "${CYAN}→${NC} Test path: ${TEST_PATH}"

# Build pytest command
PYTEST_CMD="${VENV_PATH}/bin/pytest"
PYTEST_ARGS=()

if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS+=("-v")
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_ARGS+=("--cov=${COV_PATH}" "--cov-report=term-missing")
    if [ "$HTML_REPORT" = true ]; then
        PYTEST_ARGS+=("--cov-report=html")
    fi
    echo -e "${CYAN}→${NC} Coverage enabled for: ${COV_PATH}"
fi

PYTEST_ARGS+=("${PROJECT_ROOT}/${TEST_PATH}")

echo ""
echo -e "${YELLOW}→${NC} Running: pytest ${PYTEST_ARGS[*]}"
echo ""

# Change to project root and run tests
cd "$PROJECT_ROOT"
"$PYTEST_CMD" "${PYTEST_ARGS[@]}"
EXIT_CODE=$?

echo ""
echo -e "${BLUE}========================================${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
fi

if [ "$HTML_REPORT" = true ] && [ $EXIT_CODE -eq 0 ]; then
    echo -e "${CYAN}→${NC} HTML report: ${PROJECT_ROOT}/htmlcov/index.html"
fi

echo -e "${BLUE}========================================${NC}"
echo ""

exit $EXIT_CODE
