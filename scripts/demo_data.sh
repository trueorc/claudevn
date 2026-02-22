#!/bin/bash

# ClaudeVN Demo Data CLI Script
# Manages demo data for development and testing
#
# This is a lightweight wrapper around the demo_data package that provides
# a consistent CLI interface with bash-style argument parsing.

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
ACTION=""
PHASE=""
PROJECTS=false
GOALS=false
WORK=false
SKILLS=false
SEED=""
COUNT=""
VERBOSE=false
DRY_RUN=false
SERVING_URL="http://localhost:8002"
MARKETPLACE_URL="http://localhost:8003"

usage() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}ClaudeVN - Demo Data Manager${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "Manage demo data for ClaudeVN development and testing."
    echo "Data is organized in phases based on real project history."
    echo ""
    echo -e "${CYAN}Phases:${NC}"
    echo "  1 - Foundation: Project, Git infrastructure, Auth (completed)"
    echo "  2 - Execution:  Dispatcher, Conflict resolution (mostly done)"
    echo "  3 - Growth:     Marketplace, Frontend, active work (in-flight)"
    echo ""
    echo -e "${CYAN}Usage:${NC} $0 [OPTIONS]"
    echo ""
    echo -e "${CYAN}Actions:${NC}"
    echo "  -f, --full              Full reset: delete all data and regenerate"
    echo "  -d, --delete            Delete all demo data (no regeneration)"
    echo "  -r, --refresh           Refresh existing data (update timestamps)"
    echo "  -s, --status            Show current data counts"
    echo ""
    echo -e "${CYAN}Phase Selection:${NC}"
    echo "  --phase <phases>        Comma-separated phases (1,2,3). Default: all"
    echo ""
    echo -e "${CYAN}Category Filters:${NC}"
    echo "  --projects              Only affect projects data"
    echo "  --goals                 Only affect goals data"
    echo "  --work                  Only affect work items data"
    echo "  --skills                Only affect skills data (user skills only)"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  --seed <number>         Random seed for reproducible data"
    echo "  --count <number>        Limit items per category"
    echo "  --serving-url <url>     Serving API URL (default: http://localhost:8002)"
    echo "  --marketplace-url <url> Marketplace API URL (default: http://localhost:8003)"
    echo "  -v, --verbose           Verbose output"
    echo "  -n, --dry-run           Show what would be done without making changes"
    echo "  -h, --help              Show this help message"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  $0 --full                    # Complete reset (all phases)"
    echo "  $0 --full --phase 1          # Reset with only foundation data"
    echo "  $0 --full --phase 1,2        # Foundation + execution"
    echo "  $0 --delete --projects       # Delete only project data"
    echo "  $0 --refresh --goals         # Refresh goals only"
    echo "  $0 --status                  # Check current data counts"
    echo "  $0 -n --full                 # Preview full reset (dry run)"
    echo ""
    echo -e "${CYAN}Endpoints (must be running):${NC}"
    echo "  Serving:     http://localhost:8002"
    echo "  Marketplace: http://localhost:8003"
    echo ""
}

# Check if virtual environment exists
check_venv() {
    if [[ ! -f "${VENV_PATH}/bin/python" ]]; then
        echo -e "${RED}Error: Virtual environment not found at ${VENV_PATH}${NC}"
        echo "Please create a virtual environment first:"
        echo "  python3 -m venv .venv"
        echo "  source .venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
}

# Build Python arguments from parsed options
build_python_args() {
    local args=()

    # Action
    case "$ACTION" in
        full)
            args+=("--clear")
            args+=("--populate")
            ;;
        delete)
            args+=("--delete")
            ;;
        refresh)
            args+=("--refresh")
            ;;
        status)
            args+=("--status")
            ;;
        *)
            # Default: populate (no clear)
            args+=("--populate")
            ;;
    esac

    # Phase selection
    if [[ -n "$PHASE" ]]; then
        args+=("--phase" "$PHASE")
    fi

    # Category filters
    if [[ "$PROJECTS" == true ]]; then
        args+=("--projects")
    fi
    if [[ "$GOALS" == true ]]; then
        args+=("--goals")
    fi
    if [[ "$WORK" == true ]]; then
        args+=("--work")
    fi
    if [[ "$SKILLS" == true ]]; then
        args+=("--skills")
    fi

    # Options
    if [[ -n "$SEED" ]]; then
        args+=("--seed" "$SEED")
    fi
    if [[ -n "$COUNT" ]]; then
        args+=("--count" "$COUNT")
    fi
    if [[ "$VERBOSE" == true ]]; then
        args+=("--verbose")
    fi
    if [[ "$DRY_RUN" == true ]]; then
        args+=("--dry-run")
    fi
    if [[ "$SERVING_URL" != "http://localhost:8002" ]]; then
        args+=("--serving-url" "$SERVING_URL")
    fi
    if [[ "$MARKETPLACE_URL" != "http://localhost:8003" ]]; then
        args+=("--marketplace-url" "$MARKETPLACE_URL")
    fi

    echo "${args[@]}"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -f|--full)
            if [[ -n "$ACTION" && "$ACTION" != "full" ]]; then
                echo -e "${RED}Error: Cannot combine --full with --delete or --refresh${NC}"
                exit 1
            fi
            ACTION="full"
            shift
            ;;
        -d|--delete)
            if [[ -n "$ACTION" && "$ACTION" != "delete" ]]; then
                echo -e "${RED}Error: Cannot combine --delete with --full or --refresh${NC}"
                exit 1
            fi
            ACTION="delete"
            shift
            ;;
        -r|--refresh)
            if [[ -n "$ACTION" && "$ACTION" != "refresh" ]]; then
                echo -e "${RED}Error: Cannot combine --refresh with --full or --delete${NC}"
                exit 1
            fi
            ACTION="refresh"
            shift
            ;;
        -s|--status)
            ACTION="status"
            shift
            ;;
        --phase)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo -e "${RED}Error: --phase requires phases (e.g., 1,2,3)${NC}"
                exit 1
            fi
            PHASE="$2"
            shift 2
            ;;
        --projects)
            PROJECTS=true
            shift
            ;;
        --goals)
            GOALS=true
            shift
            ;;
        --work)
            WORK=true
            shift
            ;;
        --skills)
            SKILLS=true
            shift
            ;;
        --seed)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo -e "${RED}Error: --seed requires a number${NC}"
                exit 1
            fi
            SEED="$2"
            shift 2
            ;;
        --count)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo -e "${RED}Error: --count requires a number${NC}"
                exit 1
            fi
            COUNT="$2"
            shift 2
            ;;
        --serving-url)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo -e "${RED}Error: --serving-url requires a URL${NC}"
                exit 1
            fi
            SERVING_URL="$2"
            shift 2
            ;;
        --marketplace-url)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo -e "${RED}Error: --marketplace-url requires a URL${NC}"
                exit 1
            fi
            MARKETPLACE_URL="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            echo ""
            usage
            exit 1
            ;;
        *)
            echo -e "${RED}Unexpected argument: $1${NC}"
            echo ""
            usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    check_venv

    # Build the Python command
    local python_args
    python_args=$(build_python_args)

    if [[ "$VERBOSE" == true ]]; then
        echo -e "${CYAN}Running:${NC} ${VENV_PATH}/bin/python ${SCRIPT_DIR}/demo_data.py ${python_args}"
    fi

    # Set PYTHONPATH to include project root and shared module
    export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/shared:${SCRIPT_DIR}:${PYTHONPATH:-}"

    # Execute Python script
    # shellcheck disable=SC2086
    "${VENV_PATH}/bin/python" "${SCRIPT_DIR}/demo_data.py" $python_args
}

main
