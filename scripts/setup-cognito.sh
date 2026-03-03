#!/usr/bin/env bash
#
# setup-cognito.sh — Deploy Cognito User Pool and configure ClaudeVN serving
#
# Usage:
#   ./scripts/setup-cognito.sh --admin-email admin@example.com
#   ./scripts/setup-cognito.sh --admin-email admin@example.com --profile personal
#   ./scripts/setup-cognito.sh --admin-email admin@example.com --environment production --serving-url https://claudevn.example.com
#   ./scripts/setup-cognito.sh --dry-run
#
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────

ENVIRONMENT="dev"
AWS_PROFILE_FLAG=""
SERVING_URL="http://localhost:8002"
ADMIN_EMAIL=""
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STACK_NAME=""
CF_TEMPLATE="deploy/cloud/cognito-user-pool.yaml"

# ── Color helpers ─────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✔${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
err()   { echo -e "${RED}✖${NC}  $*" >&2; }

# ── Usage ─────────────────────────────────────────────────────────────────────

usage() {
    cat <<'EOF'
Usage: setup-cognito.sh [OPTIONS]

Deploy the Cognito User Pool and configure ClaudeVN serving auth.

Options:
  --admin-email EMAIL     Email for the first admin user (required)
  --environment ENV       dev | production (default: dev)
  --profile PROFILE       AWS CLI profile to use
  --serving-url URL       Serving URL for invitation emails (default: http://localhost:8002)
  --dry-run               Preview changes without applying
  -h, --help              Show this help

Examples:
  ./scripts/setup-cognito.sh --admin-email admin@example.com
  ./scripts/setup-cognito.sh --admin-email admin@example.com --profile personal
  ./scripts/setup-cognito.sh --admin-email admin@example.com --environment production --serving-url https://claudevn.example.com
EOF
    exit 0
}

# ── Parse arguments ───────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case $1 in
        --admin-email)   ADMIN_EMAIL="$2"; shift 2 ;;
        --environment)   ENVIRONMENT="$2"; shift 2 ;;
        --profile)       AWS_PROFILE_FLAG="--profile $2"; shift 2 ;;
        --serving-url)   SERVING_URL="$2"; shift 2 ;;
        --dry-run)       DRY_RUN=true; shift ;;
        -h|--help)       usage ;;
        *)               err "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$ADMIN_EMAIL" ]]; then
    err "--admin-email is required"
    echo ""
    usage
fi

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "production" ]]; then
    err "--environment must be 'dev' or 'production'"
    exit 1
fi

STACK_NAME="claudevn-cognito-${ENVIRONMENT}"

# ── Preflight checks ─────────────────────────────────────────────────────────

info "Checking prerequisites..."

if ! command -v aws &>/dev/null; then
    err "AWS CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi

# Verify credentials work
if ! aws sts get-caller-identity $AWS_PROFILE_FLAG &>/dev/null; then
    err "AWS credentials invalid or expired. Run 'aws configure' or check --profile."
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity $AWS_PROFILE_FLAG --query Account --output text)
AWS_REGION=$(aws configure get region $AWS_PROFILE_FLAG 2>/dev/null || echo "us-east-1")
ok "AWS account: $AWS_ACCOUNT (region: $AWS_REGION)"

if [[ ! -f "$PROJECT_ROOT/$CF_TEMPLATE" ]]; then
    err "CloudFormation template not found: $CF_TEMPLATE"
    exit 1
fi

# ── Dry-run summary ──────────────────────────────────────────────────────────

if $DRY_RUN; then
    echo ""
    info "DRY RUN — no changes will be made"
    echo ""
    echo "  Stack name:    $STACK_NAME"
    echo "  Environment:   $ENVIRONMENT"
    echo "  Region:        $AWS_REGION"
    echo "  Serving URL:   $SERVING_URL"
    echo "  Admin email:   $ADMIN_EMAIL"
    echo "  CF template:   $CF_TEMPLATE"
    echo ""
    echo "  Actions:"
    echo "    1. Deploy/update CloudFormation stack '$STACK_NAME'"
    echo "    2. Create admin user '$ADMIN_EMAIL' in the User Pool"
    echo "    3. Write .env file with Cognito configuration"
    echo ""
    exit 0
fi

# ── Step 1: Deploy CloudFormation stack ───────────────────────────────────────

echo ""
info "Step 1: Deploying CloudFormation stack '$STACK_NAME'..."

STACK_EXISTS=false
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG &>/dev/null; then
    STACK_EXISTS=true
    CURRENT_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG \
        --query 'Stacks[0].StackStatus' --output text)
    info "Stack already exists (status: $CURRENT_STATUS) — updating..."
else
    info "Stack does not exist — creating..."
fi

aws cloudformation deploy \
    --template-file "$PROJECT_ROOT/$CF_TEMPLATE" \
    --stack-name "$STACK_NAME" \
    --parameter-overrides \
        "Environment=$ENVIRONMENT" \
        "ServingUrl=$SERVING_URL" \
    --no-fail-on-empty-changeset \
    $AWS_PROFILE_FLAG

# Verify stack status
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG \
    --query 'Stacks[0].StackStatus' --output text)

if [[ "$STACK_STATUS" != *"COMPLETE"* ]] || [[ "$STACK_STATUS" == *"ROLLBACK"* ]]; then
    err "Stack is in unexpected state: $STACK_STATUS"
    err "Check the CloudFormation console for details."
    exit 1
fi

ok "Stack '$STACK_NAME' is $STACK_STATUS"

# ── Step 2: Extract stack outputs ─────────────────────────────────────────────

info "Step 2: Extracting stack outputs..."

get_output() {
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" $AWS_PROFILE_FLAG \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
        --output text
}

USER_POOL_ID=$(get_output UserPoolId)
APP_CLIENT_ID=$(get_output AppClientId)
COGNITO_REGION=$(get_output Region)

if [[ -z "$USER_POOL_ID" || -z "$APP_CLIENT_ID" ]]; then
    err "Failed to extract stack outputs. Check the stack in the AWS console."
    exit 1
fi

ok "User Pool ID:  $USER_POOL_ID"
ok "App Client ID: $APP_CLIENT_ID"
ok "Region:        $COGNITO_REGION"

# ── Step 3: Create admin user ─────────────────────────────────────────────────

info "Step 3: Creating admin user '$ADMIN_EMAIL'..."

# Check if user already exists
USER_EXISTS=false
if aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$ADMIN_EMAIL" \
    $AWS_PROFILE_FLAG &>/dev/null; then
    USER_EXISTS=true
fi

if $USER_EXISTS; then
    warn "User '$ADMIN_EMAIL' already exists — skipping creation."
else
    aws cognito-idp admin-create-user \
        --user-pool-id "$USER_POOL_ID" \
        --username "$ADMIN_EMAIL" \
        --user-attributes \
            "Name=email,Value=$ADMIN_EMAIL" \
            "Name=email_verified,Value=true" \
        --desired-delivery-mediums EMAIL \
        $AWS_PROFILE_FLAG \
        --output text >/dev/null

    ok "Admin user created. A temporary password was sent to $ADMIN_EMAIL."
fi

# ── Step 4: Write .env file ──────────────────────────────────────────────────

info "Step 4: Configuring docker-compose environment..."

ENV_FILE="$PROJECT_ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
    # Check if it already has Cognito vars
    if grep -q "^AUTH_MODE=" "$ENV_FILE"; then
        warn "Existing .env file found with AUTH_MODE set."
        echo ""
        read -rp "  Overwrite Cognito settings in .env? [y/N] " CONFIRM
        if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
            warn "Skipping .env update. Manually set these values:"
            echo "    AUTH_MODE=cognito"
            echo "    COGNITO_USER_POOL_ID=$USER_POOL_ID"
            echo "    COGNITO_APP_CLIENT_ID=$APP_CLIENT_ID"
            echo "    COGNITO_REGION=$COGNITO_REGION"
            echo "    COGNITO_ADMIN_ENABLED=true"
            # Skip to validation
            ENV_WRITTEN=false
        else
            ENV_WRITTEN=true
        fi
    else
        ENV_WRITTEN=true
    fi
else
    ENV_WRITTEN=true
fi

if [[ "${ENV_WRITTEN:-true}" == "true" ]]; then
    # Remove existing Cognito lines if present, then append
    if [[ -f "$ENV_FILE" ]]; then
        # Preserve non-Cognito lines
        TEMP_ENV=$(mktemp)
        grep -v -E '^(AUTH_MODE|COGNITO_USER_POOL_ID|COGNITO_APP_CLIENT_ID|COGNITO_REGION|COGNITO_ADMIN_ENABLED)=' \
            "$ENV_FILE" > "$TEMP_ENV" 2>/dev/null || true
        cp "$TEMP_ENV" "$ENV_FILE"
        rm -f "$TEMP_ENV"
    fi

    cat >> "$ENV_FILE" <<EOF
AUTH_MODE=cognito
COGNITO_USER_POOL_ID=$USER_POOL_ID
COGNITO_APP_CLIENT_ID=$APP_CLIENT_ID
COGNITO_REGION=$COGNITO_REGION
COGNITO_ADMIN_ENABLED=true
EOF

    ok "Wrote Cognito configuration to .env"
fi

# ── Step 5: Validate setup ───────────────────────────────────────────────────

echo ""
info "Step 5: Validating setup..."

# Verify the user pool is accessible
POOL_STATUS=$(aws cognito-idp describe-user-pool \
    --user-pool-id "$USER_POOL_ID" $AWS_PROFILE_FLAG \
    --query 'UserPool.Status' --output text 2>/dev/null || echo "UNKNOWN")

if [[ "$POOL_STATUS" == "Enabled" ]]; then
    ok "User Pool is accessible and enabled"
else
    warn "User Pool status: $POOL_STATUS (expected: Enabled)"
fi

# Count users
USER_COUNT=$(aws cognito-idp list-users \
    --user-pool-id "$USER_POOL_ID" $AWS_PROFILE_FLAG \
    --query 'length(Users)' --output text 2>/dev/null || echo "?")

ok "Users in pool: $USER_COUNT"

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e " ${GREEN}Cognito setup complete${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Stack:         $STACK_NAME ($STACK_STATUS)"
echo "  User Pool:     $USER_POOL_ID"
echo "  App Client:    $APP_CLIENT_ID"
echo "  Region:        $COGNITO_REGION"
echo "  Admin:         $ADMIN_EMAIL"
echo "  Auth mode:     cognito"
echo ""
echo "  Next steps:"
echo "    1. Restart docker-compose:"
echo "       docker compose down && docker compose up -d"
echo ""
echo "    2. Open http://localhost:8002 — you should see the Login page"
echo ""
echo "    3. Log in with $ADMIN_EMAIL and the temporary password from your email"
echo ""
echo "  To revert to bypass mode:"
echo "    ./scripts/teardown-cognito.sh"
echo ""
