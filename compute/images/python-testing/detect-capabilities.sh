#!/usr/bin/env bash
#
# detect-capabilities.sh — Auto-detect runtimes and set COMPUTE_CAPABILITIES
#
# Sourced by the compute entrypoint to populate runtime capability labels.
# Detects installed runtimes and appends runtime:name:version labels to
# the COMPUTE_CAPABILITIES environment variable.
#
# This script is the reusable template for all compute images.
# Each image includes it; the detected runtimes depend on what's installed.
#
set -euo pipefail

DETECTED=()

# ── Node.js ──────────────────────────────────────────────────────────────────
if command -v node &>/dev/null; then
    VER=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
    if [[ -n "$VER" ]]; then
        DETECTED+=("runtime:node:${VER}" "runtime:node")
    fi
fi

# ── Python ───────────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    VER=$(python3 --version 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
    if [[ -n "$VER" ]]; then
        DETECTED+=("runtime:python:${VER}" "runtime:python")
    fi
fi

# ── Go ───────────────────────────────────────────────────────────────────────
if command -v go &>/dev/null; then
    VER=$(go version 2>/dev/null | awk '{print $3}' | sed 's/^go//' | cut -d. -f1,2)
    if [[ -n "$VER" ]]; then
        DETECTED+=("runtime:go:${VER}" "runtime:go")
    fi
fi

# ── Rust ─────────────────────────────────────────────────────────────────────
if command -v rustc &>/dev/null; then
    VER=$(rustc --version 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
    if [[ -n "$VER" ]]; then
        DETECTED+=("runtime:rust:${VER}" "runtime:rust")
    fi
fi

# ── Java ─────────────────────────────────────────────────────────────────────
if command -v java &>/dev/null; then
    VER=$(java -version 2>&1 | head -1 | awk -F'"' '{print $2}' | cut -d. -f1)
    if [[ -n "$VER" && "$VER" != "0" ]]; then
        DETECTED+=("runtime:java:${VER}" "runtime:java")
    fi
fi

# ── Output ───────────────────────────────────────────────────────────────────
# Merge with existing COMPUTE_CAPABILITIES (comma-separated)
EXISTING="${COMPUTE_CAPABILITIES:-}"
NEW_CAPS=$(IFS=','; echo "${DETECTED[*]}")

if [[ -n "$EXISTING" && -n "$NEW_CAPS" ]]; then
    export COMPUTE_CAPABILITIES="${EXISTING},${NEW_CAPS}"
elif [[ -n "$NEW_CAPS" ]]; then
    export COMPUTE_CAPABILITIES="$NEW_CAPS"
fi

echo "[detect-capabilities] Detected: ${NEW_CAPS:-none}"
echo "[detect-capabilities] COMPUTE_CAPABILITIES=${COMPUTE_CAPABILITIES:-}"
