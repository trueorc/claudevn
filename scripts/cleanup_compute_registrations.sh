#!/bin/bash

# ClaudeVN Platform - Cleanup Compute Registrations
# This script removes stale compute registrations from the serving component

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SERVING_PORT=${SERVING_PORT:-8002}
SERVING_URL="http://localhost:${SERVING_PORT}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ClaudeVN - Cleanup Compute Registrations${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if serving is running
if ! curl -s -f --connect-timeout 3 "${SERVING_URL}/api/v1/health" > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} Serving component is not running at ${SERVING_URL}"
    echo -e "${YELLOW}→${NC} Please start serving first with: cd serving && ./start.sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} Serving component is running"
echo ""

# Get list of registered compute instances
echo -e "${YELLOW}→${NC} Fetching registered compute instances..."
INSTANCES=$(curl -s "${SERVING_URL}/api/v1/compute" | python3 -c "import sys, json; data=json.load(sys.stdin); print(' '.join([i['instance_id'] for i in data.get('instances', [])]))" 2>/dev/null)

if [ -z "$INSTANCES" ]; then
    echo -e "${GREEN}✓${NC} No compute instances registered"
    exit 0
fi

echo -e "${YELLOW}→${NC} Found compute instances:"
for instance_id in $INSTANCES; do
    # Get instance details
    INSTANCE_DATA=$(curl -s "${SERVING_URL}/api/v1/compute/${instance_id}")
    STATUS=$(echo "$INSTANCE_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null)
    NAME=$(echo "$INSTANCE_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', 'unknown'))" 2>/dev/null)
    
    echo -e "  - ${instance_id} (${NAME}) - Status: ${STATUS}"
done

echo ""
echo -e "${YELLOW}→${NC} Do you want to remove all registrations? (y/N): "
read -r CONFIRM

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}→${NC} Cancelled"
    exit 0
fi

echo ""
echo -e "${YELLOW}→${NC} Removing compute registrations..."

for instance_id in $INSTANCES; do
    RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "${SERVING_URL}/api/v1/compute/${instance_id}")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓${NC} Removed ${instance_id}"
    else
        echo -e "${RED}✗${NC} Failed to remove ${instance_id} (HTTP ${HTTP_CODE})"
    fi
done

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Cleanup Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

