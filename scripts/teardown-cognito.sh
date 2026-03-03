#!/usr/bin/env bash
#
# teardown-cognito.sh — Remove Cognito User Pool and revert to bypass auth
#
# Usage:
#   ./scripts/teardown-cognito.sh
#   ./scripts/teardown-cognito.sh --environment production --profile personal
#   ./scripts/teardown-cognito.sh --keep-stack   # only reset .env, don't delete stack
#   ./scripts/teardown-cognito.sh --dry-run
#
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────

ENVIRONMENT="dev"
AWS_PROFILE_FLAG=""
KEEP_STACK=false
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STACK_NAME=""

# ── Color helpers ─────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✔${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
err()   { echo -e "${RED}✖${NC}  $*" >&2; }

# ── Usage ─────────────────────────────────────────────────────────────────────

usage() {
    cat <<'EOF'
Usage: teardown-cognito.sh [OPTIONS]

Remove the Cognito User Pool and revert ClaudeVN to bypass auth mode.

Options:
  --environment ENV     dev | production (default: dev)
  --profile PROFILE     AWS CLI profile to use
  --keep-stack          Only reset .env; do not delete the CloudFormation stack
  --dry-run             Preview changes without applying
  -h, --help            Show this help

Examples:
  ./scripts/teardown-cognito.sh
  ./scripts/teardown-cognito.sh --keep-stack
  ./scripts/teardown-cognito.sh --environment production --profile personal
EOF
    exit 0
}

# ── Parse arguments ───────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case $1 in
        --environment)   ENVIRONMENT="$2"; shift 2 ;;
        --profile)       AWS_PROFILE_FLAG="--profile $2"; shift 2 ;;
        --keep-stack)    KEEP_STACK=true; shift ;;
        --dry-run)       DRY_RUN=true; shift ;;
        -h|--help)       usage ;;
        *)               err "Unknown option: $1"; usage ;;
    esac
done

STACK_NAME="claudevn-cognito-${ENVIRONMENT}"

# ── Dry-run summary ──────────────────────────────────────────────────────────

if $DRY_RUN; then
    echo ""
    info "DRY RUN — no changes will be made"
    echo ""
    echo "  Actions:"
    if ! $KEEP_STACK; then
        echo "    1. Delete CloudFormation stack '$STACK_NAME'"
    else
        echo "    1. (skipped — --keep-stack) CloudFormation stack '$STACK_NAME' will not be deleted"
    fi
    echo "    2. Remove Cognito vars from .env and set AUTH_MODE=bypass"
    echo ""
    exit 0
fi

# ── Confirmation ──────────────────────────────────────────────────────────────

echo ""
if ! $KEEP_STACK; then
    warn "This will DELETE the CloudFormation stack '$STACK_NAME' and all its users."
else
    info "This will reset auth to bypass mode. The stack '$STACK_NAME' will be kept."
fi
echo ""
read -rp "  Continue? [y/N] " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    info "Aborted."
    exit 0
fi

# ── Step 1: Delete CloudFormation stack ───────────────────────────────────────

echo ""
if ! $KEEP_STACK; then
    info "Step 1: Deleting CloudFormation stack '$STACK_NAME'..."

    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG &>/dev/null; then
        # Check for deletion protection (production pools)
        DELETION_PROTECTION=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG \
            --query 'Stacks[0].EnableTerminationProtection' --output text 2>/dev/null || echo "false")

        if [[ "$DELETION_PROTECTION" == "true" ]]; then
            err "Stack has termination protection enabled (production pool)."
            err "Disable it first: aws cloudformation update-termination-protection --no-enable-termination-protection --stack-name $STACK_NAME"
            exit 1
        fi

        # For production pools, the Cognito User Pool has DeletionProtection: ACTIVE
        # We need to update it to INACTIVE before deleting the stack
        if [[ "$ENVIRONMENT" == "production" ]]; then
            USER_POOL_ID=$(aws cloudformation describe-stacks \
                --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG \
                --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
                --output text 2>/dev/null || echo "")

            if [[ -n "$USER_POOL_ID" ]]; then
                info "Disabling Cognito deletion protection for production pool..."
                aws cognito-idp update-user-pool \
                    --user-pool-id "$USER_POOL_ID" \
                    --deletion-protection INACTIVE \
                    $AWS_PROFILE_FLAG 2>/dev/null || true
            fi
        fi

        aws cloudformation delete-stack --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG

        info "Waiting for stack deletion (this may take a minute)..."
        aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG 2>/dev/null

        ok "Stack '$STACK_NAME' deleted"
    else
        warn "Stack '$STACK_NAME' does not exist — nothing to delete."
    fi
else
    info "Step 1: Skipped (--keep-stack)"
fi

# ── Step 2: Reset .env ───────────────────────────────────────────────────────

info "Step 2: Resetting .env to bypass mode..."

ENV_FILE="$PROJECT_ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
    # Remove Cognito-specific lines
    TEMP_ENV=$(mktemp)
    grep -v -E '^(AUTH_MODE|COGNITO_USER_POOL_ID|COGNITO_APP_CLIENT_ID|COGNITO_REGION|COGNITO_ADMIN_ENABLED)=' \
        "$ENV_FILE" > "$TEMP_ENV" 2>/dev/null || true
    cp "$TEMP_ENV" "$ENV_FILE"
    rm -f "$TEMP_ENV"

    # Add bypass mode
    echo "AUTH_MODE=bypass" >> "$ENV_FILE"

    # Remove file if it only contains AUTH_MODE=bypass (clean state)
    LINE_COUNT=$(wc -l < "$ENV_FILE" | tr -d ' ')
    CONTENT=$(cat "$ENV_FILE" | tr -d '[:space:]')
    if [[ "$CONTENT" == "AUTH_MODE=bypass" ]]; then
        rm "$ENV_FILE"
        ok "Removed .env (only had AUTH_MODE=bypass, which is the default)"
    else
        ok "Updated .env: AUTH_MODE=bypass (removed Cognito vars)"
    fi
else
    ok ".env file does not exist — already in bypass mode (default)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e " ${GREEN}Teardown complete — auth mode is now 'bypass'${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Next steps:"
echo "    docker compose down && docker compose up -d"
echo ""
