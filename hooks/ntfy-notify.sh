#!/bin/bash
#
# Claude Code notification hook for ntfy
# Sends a push notification when Claude Code is idle/waiting for input
#
# Fire-and-forget — exits immediately after POST
#

set -e

# Check dependencies
if ! command -v jq &> /dev/null; then
    exit 0
fi

# Load credentials
CRED_FILE="$HOME/.config/ntfy/credentials"
if [[ ! -f "$CRED_FILE" ]]; then
    exit 0
fi
source "$CRED_FILE"

# Read JSON input from stdin
INPUT=$(cat)

# Parse fields
NOTIFICATION_TYPE=$(echo "$INPUT" | jq -r '.notification_type // "unknown"')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_NAME=""
if [[ -n "$CWD" ]]; then
    PROJECT_NAME=$(basename "$CWD")
fi

# Only handle idle_prompt
if [[ "$NOTIFICATION_TYPE" != "idle_prompt" ]]; then
    exit 0
fi

TITLE="Claude Code waiting for input"
BODY="Project: ${PROJECT_NAME:-unknown}"
if [[ -n "$CWD" ]]; then
    BODY=$(printf "%s\nPath: %s" "$BODY" "$CWD")
fi

# Fire-and-forget POST to ntfy
curl -sf \
    -u "${NTFY_USER}:${NTFY_PASS}" \
    -H "Title: ${TITLE}" \
    -H "Priority: default" \
    -H "Tags: hourglass" \
    -d "${BODY}" \
    "${NTFY_SERVER}/${NTFY_TOPIC_APPROVE}" \
    > /dev/null 2>&1 || true

exit 0
