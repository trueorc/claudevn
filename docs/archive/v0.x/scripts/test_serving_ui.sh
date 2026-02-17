#!/bin/bash

# ClaudeVN - Test Serving UI with Mock Compute Instances
# This script registers fake compute instances to populate the Serving UI

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Serving UI Test Data Generator${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

SERVING_URL="http://localhost:8002/api/v1"

# Check if serving is running
echo -e "${YELLOW}→${NC} Checking if Serving component is running..."
if ! curl -s -f "${SERVING_URL}/health" > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} Serving component is not running"
    echo -e "${YELLOW}→${NC} Start it with: ./start_all.sh"
    exit 1
fi
echo -e "${GREEN}✓${NC} Serving component is running"
echo ""

# Function to register a compute instance
register_instance() {
    local instance_id=$1
    local name=$2
    local port=$3
    local agents=$4
    local tools=$5
    
    echo -e "${CYAN}→${NC} Registering ${name}..."
    
    local response=$(curl -s -X POST "${SERVING_URL}/compute/register" \
        -H "Content-Type: application/json" \
        -d @- <<EOF
{
    "instance_id": "${instance_id}",
    "name": "${name}",
    "endpoint": "http://compute-${instance_id}:${port}",
    "capabilities": {
        "agents": ${agents},
        "tools": ${tools},
        "resources": {
            "cpu_cores": 8,
            "memory_gb": 32,
            "gpu_available": true
        }
    },
    "metadata": {
        "region": "us-west-2",
        "zone": "az1",
        "instance_type": "compute.large",
        "version": "1.0.0"
    }
}
EOF
)
    
    if echo "$response" | grep -q "instance_id"; then
        echo -e "${GREEN}✓${NC} ${name} registered"
    else
        echo -e "${YELLOW}⚠${NC}  ${name} registration failed (may already exist)"
    fi
}

echo -e "${BLUE}Registering Test Compute Instances...${NC}"
echo ""

# Register Instance 1 - Data Processing Node
register_instance \
    "compute-001" \
    "Data Processing Node" \
    "8003" \
    '["data-analyzer", "csv-processor", "json-transformer"]' \
    '["pandas", "numpy", "data-validator"]'

sleep 0.5

# Register Instance 2 - Web Services Node
register_instance \
    "compute-002" \
    "Web Services Node" \
    "8004" \
    '["web-scraper", "api-caller", "http-client"]' \
    '["requests", "beautifulsoup", "selenium"]'

sleep 0.5

# Register Instance 3 - ML/AI Node
register_instance \
    "compute-003" \
    "ML/AI Node" \
    "8005" \
    '["text-classifier", "sentiment-analyzer", "image-recognizer"]' \
    '["tensorflow", "pytorch", "scikit-learn"]'

sleep 0.5

# Register Instance 4 - Utility Node
register_instance \
    "compute-004" \
    "Utility Node" \
    "8006" \
    '["file-handler", "text-processor", "code-formatter"]' \
    '["file-utils", "string-utils", "formatters"]'

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Test Data Loaded${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get current stats
echo -e "${YELLOW}→${NC} Fetching registry stats..."
echo ""
curl -s "${SERVING_URL}/compute/stats" | python3 -m json.tool 2>/dev/null || curl -s "${SERVING_URL}/compute/stats"
echo ""
echo ""

echo -e "${CYAN}Next Steps:${NC}"
echo -e "  1. Open ${GREEN}http://localhost:8002${NC} in your browser"
echo -e "  2. Navigate to the ${YELLOW}Compute Registry${NC} tab"
echo -e "  3. View the ${YELLOW}Dashboard${NC} for stats"
echo -e "  4. Check ${YELLOW}Capabilities${NC} to see aggregated resources"
echo ""
echo -e "${CYAN}To clear test data:${NC}"
echo -e "  ${YELLOW}curl -X DELETE ${SERVING_URL}/compute/instances/{instance_id}${NC}"
echo ""
echo -e "${CYAN}To simulate heartbeats:${NC}"
echo -e "  ${YELLOW}curl -X POST ${SERVING_URL}/compute/instances/{instance_id}/heartbeat${NC}"
echo ""
echo -e "${GREEN}Happy Testing! 🚀${NC}"
echo ""

