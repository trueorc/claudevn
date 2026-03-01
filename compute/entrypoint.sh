#!/bin/bash
# Compute container entrypoint
#
# Handles credential provisioning based on COMPUTE_AUTH_MODE:
#   serving  - Fetch credentials from Serving's /auth/credentials endpoint
#   local    - Copy from host-mounted /host-claude staging directory
#   external - No-op (credentials pre-mounted or managed externally)

set -e

AUTH_MODE="${COMPUTE_AUTH_MODE:-serving}"
TARGET_DIR="/home/compute/.claude"
SERVING_AUTH_URL="${CLAUDEVN_SERVING_AUTH_URL:-http://serving:8002/api/v1/auth}"

echo "[entrypoint] Auth mode: $AUTH_MODE"

case "$AUTH_MODE" in
  serving)
    # Fetch credentials from Serving's auth API
    mkdir -p "$TARGET_DIR"
    MAX_ATTEMPTS=15
    RETRY_DELAY=2
    attempt=0

    echo "[entrypoint] Fetching credentials from $SERVING_AUTH_URL/credentials ..."

    while [ $attempt -lt $MAX_ATTEMPTS ]; do
      attempt=$((attempt + 1))

      # Use -k (insecure) when TLS_VERIFY is disabled (self-signed certs for local testing)
      tls_flag=""
      if [ "${TLS_VERIFY:-true}" = "false" ]; then
        tls_flag="-k"
      fi
      response=$(curl -s $tls_flag -w "\n%{http_code}" "$SERVING_AUTH_URL/credentials" 2>/dev/null || true)
      http_code=$(echo "$response" | tail -1)
      body=$(echo "$response" | head -n -1)

      if [ "$http_code" = "200" ]; then
        # Extract the credentials object from the response JSON
        echo "$body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
creds = data.get('credentials', data)
with open('$TARGET_DIR/.credentials.json', 'w') as f:
    json.dump(creds, f)
" 2>/dev/null

        if [ -f "$TARGET_DIR/.credentials.json" ]; then
          chmod 600 "$TARGET_DIR/.credentials.json"
          chown -R compute:compute "$TARGET_DIR"
          echo "[entrypoint] Credentials fetched and written to $TARGET_DIR/.credentials.json"
          break
        fi
      fi

      if [ $attempt -lt $MAX_ATTEMPTS ]; then
        echo "[entrypoint] Attempt $attempt/$MAX_ATTEMPTS: credentials not ready (HTTP $http_code), retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
      else
        echo "[entrypoint] WARNING: Failed to fetch credentials after $MAX_ATTEMPTS attempts. Continuing without credentials."
      fi
    done
    ;;

  local)
    # Copy credentials from host-mounted staging directory
    STAGING_DIR="/host-claude"

    if [ -d "$STAGING_DIR" ]; then
      mkdir -p "$TARGET_DIR"

      if [ -f "$STAGING_DIR/.credentials.json" ]; then
        cp "$STAGING_DIR/.credentials.json" "$TARGET_DIR/.credentials.json"
        chmod 600 "$TARGET_DIR/.credentials.json"
      fi

      # Copy any other config files that may exist
      for f in "$STAGING_DIR"/*; do
        [ -e "$f" ] || continue
        fname=$(basename "$f")
        cp -r "$f" "$TARGET_DIR/$fname"
      done

      chown -R compute:compute "$TARGET_DIR"
      echo "[entrypoint] Credentials copied from $STAGING_DIR to $TARGET_DIR"
    else
      echo "[entrypoint] No staging mount at $STAGING_DIR — skipping credential copy"
    fi
    ;;

  external)
    # Credentials pre-mounted or managed externally — no-op
    echo "[entrypoint] External auth mode — credentials expected to be pre-provisioned"
    ;;

  *)
    echo "[entrypoint] WARNING: Unknown auth mode '$AUTH_MODE', skipping credential provisioning"
    ;;
esac

# Fix ownership of volume-mounted directories (Docker creates them as root)
chown -R compute:compute /app/logs /app/data 2>/dev/null || true

# Drop privileges and execute the main command as 'compute' user.
# The entrypoint runs as root for credential setup (chown), then gosu drops to
# compute for the actual service. This ensures uvicorn, the spawner, git, SSH keys,
# and Claude CLI all run as the same user — eliminating ownership mismatches.
exec gosu compute "$@"
