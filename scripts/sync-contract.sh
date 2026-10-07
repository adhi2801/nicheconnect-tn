#!/bin/sh
# Copy the committed API contract from the backend repository.
# Usage: BACKEND=/path/to/nicheconnect-tn pnpm contract:sync
set -e
BACKEND="${BACKEND:-$HOME/nicheconnect-tn}"
cp "$BACKEND/docs/api/openapi.json" contract/openapi.json
COMMIT=$(git -C "$BACKEND" rev-parse --short HEAD)
printf 'Contract copied from the backend repository at commit %s on %s.\nThe backend repo is the source of truth; never edit contract/openapi.json here.\n' "$COMMIT" "$(date +%F)" > contract/SOURCE.txt
echo "synced from $COMMIT"
