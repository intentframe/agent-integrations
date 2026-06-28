#!/usr/bin/env bash
# Production-like install inside Docker: curl | bash from GitHub (same as a real user).
#
# Runs only inside a container — never installs on the host. Verifies install
# artifacts only (no doctor / no runtime / no OPENAI_API_KEY).
#
# Env:
#   REF   Git ref for script URL and --ref (default: main)
#   ORG   GitHub org (default: intentframe)
#   REPO  GitHub repo (default: agent-integrations)
set -euo pipefail

ORG="${ORG:-intentframe}"
REPO="${REPO:-agent-integrations}"
REF="${REF:-main}"
IMAGE="${INSTALLER_CURL_DOCKER_IMAGE:-ghcr.io/astral-sh/uv:python3.14-bookworm-slim}"
INSTALL_URL="https://github.com/${ORG}/${REPO}/raw/${REF}/scripts/install-hermes-plugin.sh"

docker run --rm \
  "${IMAGE}" \
  bash -lc "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl tar ca-certificates git xz-utils
rm -rf /var/lib/apt/lists/*

export HOME=/tmp/if-home
export INSTALL_DIR=\"\${HOME}/.intentframe/agent-integrations\"
mkdir -p \"\${HOME}\"

curl -fsSL \"${INSTALL_URL}\" | bash -s -- --headless --no-control-plane --ref \"${REF}\"

export PATH=\"\${HOME}/.local/bin:/usr/local/bin:\${PATH}\"
command -v intentframe-integrations
intentframe-integrations --version
python3 -m json.tool \"\${INSTALL_DIR}/.install-manifest.json\"

test -f \"\${HOME}/.hermes/.env\"
test -d \"\${HOME}/.hermes/plugins/intentframe-gate\"
test -f \"\${HOME}/.hermes/plugins/intentframe-gate/plugin.yaml\"
test -f \"\${HOME}/.intentframe/integrations/hermes/governance/tools.yaml\"
test -f \"\${HOME}/.intentframe/integrations/hermes/governance/generic_actions.manifest\"
test -f \"\${HOME}/.intentframe/integrations/hermes/policy.yaml\"
grep -q execute_code \"\${HOME}/.intentframe/integrations/hermes/governance/tools.yaml\"

echo 'curl | bash Docker install test passed (ref=${REF})'
"
