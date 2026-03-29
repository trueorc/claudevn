#!/bin/bash
# ClaudeVN Compute Environment Launcher
#
# Usage:
#   ./compute-envs/start.sh              # Build and start ALL project computes
#   ./compute-envs/start.sh calculator   # Build and start one project's compute
#
# Finds Dockerfiles in compute-envs/<project>/, builds images, attaches
# to the claudevn network, and starts containers that self-register
# with serving.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETWORK_NAME="${CLAUDEVN_NETWORK:-claudevn_claudevn-network}"
SERVING_URL="${CLAUDEVN_SERVING_URL:-http://serving:8002}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

start_project() {
    local project_dir="$1"
    local project_name=$(basename "$project_dir")

    if [ ! -f "$project_dir/Dockerfile" ]; then
        return
    fi

    # Read metadata
    local desc="default"
    local compute_id=""
    local project_id=""
    if [ -f "$project_dir/metadata.json" ]; then
        desc=$(python3 -c "import json; print(json.load(open('$project_dir/metadata.json')).get('description','default'))" 2>/dev/null || echo "default")
        compute_id=$(python3 -c "import json; print(json.load(open('$project_dir/metadata.json')).get('compute_id',''))" 2>/dev/null || echo "")
        project_id=$(python3 -c "import json; print(json.load(open('$project_dir/metadata.json')).get('project_id',''))" 2>/dev/null || echo "")
    fi

    local safe_desc=$(echo "$desc" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g' | head -c 30)
    local container_name="${project_name}-compute_${safe_desc}"
    local image_name="claudevn-compute-${project_name}"

    echo -e "${CYAN}[$project_name]${NC} Building $image_name..."

    # Stop existing
    docker stop "$container_name" 2>/dev/null && docker rm "$container_name" 2>/dev/null || true

    # Build
    docker build -q -t "$image_name" -f "$project_dir/Dockerfile" "$project_dir"

    # Run
    docker run -d \
        --name "$container_name" \
        --network "$NETWORK_NAME" \
        -e "COMPUTE_INSTANCE_ID=${compute_id:-${container_name}}" \
        -e "COMPUTE_INSTANCE_NAME=${container_name}" \
        -e "SERVING_URL=$SERVING_URL" \
        -e "CLAUDEVN_SERVING_URL=$SERVING_URL" \
        -e "COMPUTE_REGISTER_ON_STARTUP=true" \
        -e "COMPUTE_AUTH_MODE=serving" \
        -e "CLAUDEVN_SERVING_AUTH_URL=${SERVING_URL}/api/v1/auth" \
        -e "MCP_ENABLED=true" \
        -e "LOG_LEVEL=INFO" \
        ${project_id:+-e "PROJECT_ID=$project_id"} \
        "$image_name" > /dev/null

    echo -e "${GREEN}[$project_name]${NC} Started $container_name"
}

# Main
if [ -n "$1" ]; then
    # Specific project
    if [ ! -d "$SCRIPT_DIR/$1" ]; then
        echo -e "${RED}No environment found for: $1${NC}"
        exit 1
    fi
    start_project "$SCRIPT_DIR/$1"
else
    # All projects
    found=0
    for dir in "$SCRIPT_DIR"/*/; do
        [ -f "$dir/Dockerfile" ] && { start_project "$dir"; found=$((found+1)); }
    done
    if [ $found -eq 0 ]; then
        echo -e "${YELLOW}No compute environments found. Approve an environment on the Plan page first.${NC}"
    else
        echo -e "${GREEN}Started $found compute environment(s)${NC}"
    fi
fi
