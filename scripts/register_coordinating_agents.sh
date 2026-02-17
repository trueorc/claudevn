#!/bin/bash
# Register coordinating agents from compute to marketplace

set -e

MARKETPLACE_URL="${MARKETPLACE_URL:-http://localhost:8001}"
COORDINATING_AGENTS_DIR="./compute/data/compute/agents/coordinating"

echo "Registering coordinating agents to marketplace at $MARKETPLACE_URL"
echo "=================================================="

if [ ! -d "$COORDINATING_AGENTS_DIR" ]; then
    echo "Error: Coordinating agents directory not found: $COORDINATING_AGENTS_DIR"
    exit 1
fi

# Counter for successful registrations
SUCCESS_COUNT=0
FAIL_COUNT=0

# Register each coordinating agent
for agent_file in "$COORDINATING_AGENTS_DIR"/*.json; do
    if [ -f "$agent_file" ]; then
        agent_name=$(basename "$agent_file")
        echo ""
        echo "Registering: $agent_name"
        
        # Read the agent definition
        agent_data=$(cat "$agent_file")
        
        # Extract agent_id for checking if already exists
        agent_id=$(echo "$agent_data" | jq -r '.agent_id')
        
        # Check if agent already exists in marketplace
        existing_agent=$(curl -s "$MARKETPLACE_URL/api/v1/agents/$agent_id" 2>/dev/null || echo "")
        
        if echo "$existing_agent" | grep -q "\"agent_id\""; then
            echo "  ⚠️  Agent $agent_id already exists in marketplace, updating..."
            # Update existing agent
            response=$(curl -s -X PUT "$MARKETPLACE_URL/api/v1/agents/$agent_id" \
                -H "Content-Type: application/json" \
                -d "$agent_data" || echo '{"error": "request failed"}')
        else
            echo "  ➕ Creating new agent $agent_id in marketplace..."
            # Create new agent
            response=$(curl -s -X POST "$MARKETPLACE_URL/api/v1/agents" \
                -H "Content-Type: application/json" \
                -d "$agent_data" || echo '{"error": "request failed"}')
        fi
        
        # Check if registration was successful
        if echo "$response" | grep -q "\"agent_id\""; then
            echo "  ✅ Successfully registered: $agent_id"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            echo "  ❌ Failed to register: $agent_id"
            echo "  Response: $response"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    fi
done

echo ""
echo "=================================================="
echo "Registration complete!"
echo "  ✅ Successful: $SUCCESS_COUNT"
echo "  ❌ Failed: $FAIL_COUNT"
echo ""

# Verify registrations
echo "Verifying coordinating agents in marketplace..."
coordinating_agents=$(curl -s "$MARKETPLACE_URL/api/v1/agents?agent_type=coordinating" | jq -r '.items[].agent_id' 2>/dev/null || echo "")

if [ -z "$coordinating_agents" ]; then
    echo "⚠️  Warning: Could not retrieve coordinating agents from marketplace"
else
    echo "Coordinating agents in marketplace:"
    echo "$coordinating_agents" | while read -r agent; do
        echo "  - $agent"
    done
fi
