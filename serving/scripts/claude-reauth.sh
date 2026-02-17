#!/bin/bash
# Re-authenticate Claude CLI inside the serving container.
#
# Usage:
#   docker exec -it claudevn-serving /app/scripts/claude-reauth.sh
#
# This runs `claude login` headless (no browser auto-open).
# It prints an OAuth URL to visit in your browser. After completing
# the flow, credentials are written to $CLAUDE_CREDENTIALS_PATH.

set -e

CREDS_PATH="${CLAUDE_CREDENTIALS_PATH:-/app/data/serving/claude-credentials}"

export CLAUDE_CONFIG_DIR="$CREDS_PATH"
export BROWSER=""

echo "[claude-reauth] Starting headless Claude login..."
echo "[claude-reauth] Credentials will be stored at: $CREDS_PATH"
echo ""

claude login

echo ""
echo "[claude-reauth] Login complete. Credentials stored at: $CREDS_PATH"
