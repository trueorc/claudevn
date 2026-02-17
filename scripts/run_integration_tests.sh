#!/bin/bash

# ClaudeVN Platform - Tier 2 Integration Test Runner
# Runs integration tests from */tests/integration/ directories

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
START_SERVER=false
SERVER_PID=""
SPECIFIC_PATH=""

# Server configuration
SERVER_HOST="127.0.0.1"
SERVER_PORT="8002"
SERVER_URL="http://${SERVER_HOST}:${SERVER_PORT}"

usage() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}ClaudeVN - Tier 2 Integration Tests${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "Runs integration tests that require running services."
    echo ""
    echo "Usage: $0 [OPTIONS] [TEST_PATH]"
    echo ""
    echo "Options:"
    echo "  -s, --start-server Start the server automatically before tests"
    echo "  -c, --coverage     Enable coverage reporting"
    echo "  -h, --html         Generate HTML coverage report (implies -c)"
    echo "  -v, --verbose      Verbose output"
    echo "  -x, --fail-fast    Stop on first failure"
    echo "  -i, --install      Install test dependencies"
    echo "  --help             Show this help message"
    echo ""
    echo "Test Directories:"
    echo "  serving/tests/integration/      Serving service integration tests"
    echo "  marketplace/tests/integration/  Marketplace service integration tests"
    echo "  compute/tests/integration/      Compute service integration tests"
    echo "  tests/                          System-level integration tests"
    echo ""
    echo "Examples:"
    echo "  $0                Run integration tests (server must be running)"
    echo "  $0 -s             Start server and run tests"
    echo "  $0 -s -v          Start server, verbose output"
    echo "  $0 -c             Run with coverage"
    echo ""
    echo "Test Tiers:"
    echo "  Tier 1 (run_unit_tests.sh): Unit tests - mocked, fast, no server required"
    echo "  Tier 2 (this script): Integration tests - require running services"
    echo ""
    echo "Prerequisites:"
    echo "  - Server running at ${SERVER_URL} (or use -s flag to auto-start)"
    echo "  - If starting server manually, use: TESTING=true MCP_AUTH_BYPASS=true python app.py"
    echo "  - If using Docker: docker compose -f docker-compose.yml -f docker-compose.test.yml up -d"
    echo "  - Redis running (if required by server)"
    echo ""
}

install_deps() {
    echo -e "${YELLOW}→${NC} Installing test dependencies..."
    "${VENV_PATH}/bin/pip" install pytest pytest-cov pytest-asyncio httpx
    echo -e "${GREEN}✓${NC} Test dependencies installed"
}

check_server() {
    if curl -s -o /dev/null -w "%{http_code}" "${SERVER_URL}/health" 2>/dev/null | grep -q "200"; then
        return 0
    else
        return 1
    fi
}

start_server() {
    echo -e "${YELLOW}→${NC} Starting server with test overrides (rate limiting disabled, MCP auth bypass)..."
    cd "${PROJECT_ROOT}/serving"
    # Set TESTING=true to disable rate limiting, MCP_AUTH_BYPASS=true to skip compute key verification
    TESTING=true MCP_AUTH_BYPASS=true "${VENV_PATH}/bin/python" app.py &
    SERVER_PID=$!
    cd "$PROJECT_ROOT"

    echo -e "${CYAN}→${NC} Waiting for server to be ready..."
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if check_server; then
            echo -e "${GREEN}✓${NC} Server is ready (PID: ${SERVER_PID})"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done

    echo -e "${RED}✗${NC} Server failed to start within ${max_attempts} seconds"
    if [ -n "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
    fi
    exit 1
}

stop_server() {
    if [ -n "$SERVER_PID" ]; then
        echo -e "${YELLOW}→${NC} Stopping server (PID: ${SERVER_PID})..."
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
        echo -e "${GREEN}✓${NC} Server stopped"
    fi
}

# Trap to ensure server is stopped on exit
trap stop_server EXIT

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--start-server)
            START_SERVER=true
            shift
            ;;
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
echo -e "${BLUE}ClaudeVN - Tier 2 Integration Tests${NC}"
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
echo -e "${CYAN}→${NC} Tier: 2 (Integration tests)"

# Handle server
if [ "$START_SERVER" = true ]; then
    start_server
else
    echo -e "${CYAN}→${NC} Checking for running server at ${SERVER_URL}..."
    if check_server; then
        echo -e "${GREEN}✓${NC} Server is running"
        echo -e "${YELLOW}!${NC} Note: Ensure server was started with TESTING=true MCP_AUTH_BYPASS=true"
    else
        echo -e "${RED}✗${NC} Server is not running at ${SERVER_URL}"
        echo ""
        echo -e "${YELLOW}Options:${NC}"
        echo "  1. Start the server manually: cd serving && TESTING=true MCP_AUTH_BYPASS=true python app.py"
        echo "  2. Use -s flag to auto-start: $0 -s"
        echo ""
        exit 1
    fi
fi

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
    echo -e "${CYAN}→${NC} Running ${service} integration tests..."

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
    elif [[ "$SPECIFIC_PATH" == tests/* ]]; then
        PYTHONPATH="serving:marketplace:compute:shared" "$PYTEST_CMD" "${COMMON_ARGS[@]}" "$SPECIFIC_PATH"
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

    echo -e "${CYAN}→${NC} Running all integration tests"

    # Run tests for each service separately to avoid module name collisions
    run_tests "serving" "serving/tests/integration" "serving:shared"
    run_tests "marketplace" "marketplace/tests/integration" "marketplace:shared"
    run_tests "compute" "compute/tests/integration" "compute:shared"

    # Run system-level integration tests
    if [ -d "tests" ]; then
        echo ""
        echo -e "${CYAN}→${NC} Running system integration tests..."
        PYTHONPATH="serving:marketplace:compute:shared" "$PYTEST_CMD" "${COMMON_ARGS[@]}" tests/ || OVERALL_EXIT=1
    fi

    EXIT_CODE=$OVERALL_EXIT
fi

echo ""
echo -e "${BLUE}========================================${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All integration tests passed${NC}"
else
    echo -e "${RED}✗ Some integration tests failed${NC}"
fi

if [ "$HTML_REPORT" = true ] && [ $EXIT_CODE -eq 0 ]; then
    echo -e "${CYAN}→${NC} HTML report: ${PROJECT_ROOT}/htmlcov/index.html"
fi

echo -e "${BLUE}========================================${NC}"
echo ""

exit $EXIT_CODE
