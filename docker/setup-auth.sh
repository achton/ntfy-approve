#!/bin/bash
# Run once after 'docker compose up -d' to create the ntfy user and grant topic access.
# Reads username and topics from ~/.config/ntfy/credentials.
#
# Usage: NTFY_PASSWORD=<password> ./setup-auth.sh

set -e

CRED_FILE="$HOME/.config/ntfy/credentials"
if [[ ! -f "$CRED_FILE" ]]; then
    echo "Error: credentials file not found at $CRED_FILE" >&2
    echo "Create it first — see README.md step 3." >&2
    exit 1
fi
source "$CRED_FILE"

if [[ -z "$NTFY_PASSWORD" ]]; then
    echo "Usage: NTFY_PASSWORD=<password> $0" >&2
    exit 1
fi

if [[ -z "$NTFY_USER" || -z "$NTFY_TOPIC_APPROVE" || -z "$NTFY_TOPIC_RESPONSE" ]]; then
    echo "Error: NTFY_USER, NTFY_TOPIC_APPROVE, and NTFY_TOPIC_RESPONSE must be set in $CRED_FILE" >&2
    exit 1
fi

docker exec -e NTFY_PASSWORD="$NTFY_PASSWORD" ntfy ntfy user add --ignore-exists "$NTFY_USER"
docker exec ntfy ntfy access "$NTFY_USER" "$NTFY_TOPIC_APPROVE" rw
docker exec ntfy ntfy access "$NTFY_USER" "$NTFY_TOPIC_RESPONSE" rw

echo "Done. User '$NTFY_USER' has rw access to $NTFY_TOPIC_APPROVE and $NTFY_TOPIC_RESPONSE."
