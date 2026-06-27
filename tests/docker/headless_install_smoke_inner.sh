#!/usr/bin/env bash
# Inner script for tests/docker/test_headless_install_smoke.sh (runs inside container).
set -euo pipefail

export HOME="${HOME:-/tmp/if-home}"
export INSTALL_DIR="${HOME}/.intentframe/agent-integrations"
export DEBIAN_FRONTEND=noninteractive

step() { printf '\n==> %s\n' "$*"; }

step "Installing OS packages"
apt-get update -qq
apt-get install -y -qq curl tar ca-certificates git
rm -rf /var/lib/apt/lists/*

step "Stub Hermes CLI (headless smoke — no Hermes installer)"
mkdir -p "${HOME}/.local/bin"
cat >"${HOME}/.local/bin/hermes" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "hermes 0.17.0"
  exit 0
fi
exit 0
EOF
chmod +x "${HOME}/.local/bin/hermes"
export PATH="${HOME}/.local/bin:${PATH}"

step "Copy local integration pack into ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
tar -cC /repo --exclude=.git . | tar -xC "${INSTALL_DIR}"

step "Install Python workspace (uv sync --all-packages)"
cd "${INSTALL_DIR}"
uv sync --all-packages

IF_CLI="${INSTALL_DIR}/.venv/bin/intentframe-integrations"
test -x "${IF_CLI}"

step "Integrate Hermes plugin + seed runtime templates"
"${IF_CLI}" integrate hermes --copy

step "Verify CLI and install artifacts"
"${IF_CLI}" --version
"${IF_CLI}" doctor hermes
test -f "${HOME}/.hermes/plugins/intentframe-gate/plugin.yaml"
test -f "${HOME}/.intentframe/integrations/hermes/governance/tools.yaml"
test -f "${HOME}/.intentframe/integrations/hermes/policy.yaml"
grep -q 'execute_code' "${HOME}/.intentframe/integrations/hermes/governance/tools.yaml"

step "Headless install smoke passed"
