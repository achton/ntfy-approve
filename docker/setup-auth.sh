#!/bin/bash
# Run once after 'docker compose up -d' to create the ntfy user and grant topic access.
# Usage: NTFY_PASSWORD=<password> ./setup-auth.sh

set -e

if [[ -z "$NTFY_PASSWORD" ]]; then
    echo "Usage: NTFY_PASSWORD=<password> $0" >&2
    exit 1
fi

docker exec -e NTFY_PASSWORD="$NTFY_PASSWORD" ntfy ntfy user add --ignore-exists achton
docker exec ntfy ntfy access achton cc-approve rw
docker exec ntfy ntfy access achton cc-response rw

echo "Done. User 'achton' has rw access to cc-approve and cc-response."
