#!/usr/bin/env bash
#
# detect-runtimes.sh — Detect installed runtimes and output capability labels
#
# Usage:
#   ./detect-runtimes.sh              # Print runtime:name:version lines
#   ./detect-runtimes.sh --json       # Print as JSON array
#   ./detect-runtimes.sh --comma      # Print comma-separated
#
# Output format (default): one capability per line
#   runtime:node:22
#   runtime:python:3.12
#   runtime:go:1.22
#
# Used by compute instances to populate tools_available at registration.
#
set -euo pipefail

RUNTIMES=()

# ── Detection functions ───────────────────────────────────────────────────────

detect_node() {
    if command -v node &>/dev/null; then
        local ver
        ver=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
        if [[ -n "$ver" ]]; then
            RUNTIMES+=("runtime:node:${ver}")
        fi
    fi
}

detect_python() {
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 --version 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
        if [[ -n "$ver" ]]; then
            RUNTIMES+=("runtime:python:${ver}")
        fi
    fi
}

detect_go() {
    if command -v go &>/dev/null; then
        local ver
        ver=$(go version 2>/dev/null | awk '{print $3}' | sed 's/^go//' | cut -d. -f1,2)
        if [[ -n "$ver" ]]; then
            RUNTIMES+=("runtime:go:${ver}")
        fi
    fi
}

detect_rust() {
    if command -v rustc &>/dev/null; then
        local ver
        ver=$(rustc --version 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
        if [[ -n "$ver" ]]; then
            RUNTIMES+=("runtime:rust:${ver}")
        fi
    fi
}

detect_java() {
    if command -v java &>/dev/null; then
        local ver
        ver=$(java -version 2>&1 | head -1 | awk -F'"' '{print $2}' | cut -d. -f1)
        if [[ -n "$ver" && "$ver" != "0" ]]; then
            RUNTIMES+=("runtime:java:${ver}")
        fi
    fi
}

detect_ruby() {
    if command -v ruby &>/dev/null; then
        local ver
        ver=$(ruby --version 2>/dev/null | awk '{print $2}' | cut -d. -f1,2)
        if [[ -n "$ver" ]]; then
            RUNTIMES+=("runtime:ruby:${ver}")
        fi
    fi
}

detect_docker() {
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        RUNTIMES+=("runtime:docker")
    fi
}

# ── Run detection ─────────────────────────────────────────────────────────────

detect_node
detect_python
detect_go
detect_rust
detect_java
detect_ruby
detect_docker

# ── Output ────────────────────────────────────────────────────────────────────

FORMAT="${1:-}"

case "$FORMAT" in
    --json)
        printf '['
        for i in "${!RUNTIMES[@]}"; do
            [[ $i -gt 0 ]] && printf ','
            printf '"%s"' "${RUNTIMES[$i]}"
        done
        printf ']\n'
        ;;
    --comma)
        IFS=','; echo "${RUNTIMES[*]}"
        ;;
    *)
        for rt in "${RUNTIMES[@]}"; do
            echo "$rt"
        done
        ;;
esac
