#!/usr/bin/env bash
set -euo pipefail

# Run from any directory. The checkout containing this script is the compose root.
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

NO_START=false
if [[ "${1:-}" == "--no-start" ]]; then
    NO_START=true
fi

mkdir -p data/legendary data/nile .empty

if [[ ! -f .env ]]; then
    touch .env
    echo "Created $ROOT_DIR/.env"
fi

fernet_key=""
if command -v openssl >/dev/null 2>&1; then
    fernet_key="$(openssl rand -base64 32 | tr '+/' '-_')"
else
    echo "openssl is required to generate PSN_ENCRYPTION_KEY" >&2
    exit 1
fi

if ! grep -q '^PSN_ENCRYPTION_KEY=' .env; then
    printf '\n# PlayStation Network credential encryption\nPSN_ENCRYPTION_KEY=%s\n' "$fernet_key" >> .env
    echo "Added PSN_ENCRYPTION_KEY to .env"
fi

if ! grep -q '^PSN_ALLOW_PLAINTEXT=' .env; then
    printf 'PSN_ALLOW_PLAINTEXT=false\n' >> .env
fi

if ! grep -q '^WEB_PORT=' .env; then
    printf 'WEB_PORT=5050\n' >> .env
fi

# Compose resolves relative volume paths against this checkout. Validate the
# generated configuration before starting so missing mounts fail early.
docker compose config >/dev/null

echo "Runtime directories ready under $ROOT_DIR/data"
echo "Persistent database: $ROOT_DIR/data/game_library.db"
echo "Open: http://localhost:${WEB_PORT:-5050}"

if [[ "$NO_START" == false ]]; then
    docker compose up -d --build
    echo "Backlogia is running. Logs: docker compose logs -f backlogia"
else
    echo "Configuration validated. Start with: docker compose up -d --build"
fi
