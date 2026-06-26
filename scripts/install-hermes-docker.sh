#!/usr/bin/env bash
# Docker one-liner: download compose file and start Hermes + IntentFrame stack.
#
# Usage:
#   export OPENAI_API_KEY=sk-...
#   curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-docker.sh | bash
#
# Options (env):
#   INSTALL_DIR  Where to save docker-compose.yml (default: ~/.intentframe/hermes-docker)
#   COMPOSE_URL    Override compose file URL
#   VERSION        Passed through to install-hermes.sh (default: main)
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-${HOME}/.intentframe/hermes-docker}"
COMPOSE_URL="${COMPOSE_URL:-https://github.com/intentframe/agent-integrations/raw/main/docker-compose.hermes.yml}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required." >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
curl -fsSL "${COMPOSE_URL}" -o "${INSTALL_DIR}/docker-compose.yml"

cd "${INSTALL_DIR}"
docker compose up
