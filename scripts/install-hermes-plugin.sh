#!/usr/bin/env bash
# Install Hermes (if missing) + IntentFrame plugin.
#
#   curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
#
# Then:
#   export OPENAI_API_KEY=sk-...
#   intentframe-integrations start hermes
#   hermes dashboard            # http://localhost:9119
set -euo pipefail

ORG="${ORG:-intentframe}"
REPO="${REPO:-agent-integrations}"
VERSION="${VERSION:-main}"
INSTALL_DIR="${INSTALL_DIR:-${HOME}/.intentframe/agent-integrations}"
LOCAL_BIN="${HOME}/.local/bin"
HERMES_ENV="${HOME}/.hermes/.env"

step() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# 1. uv
if ! have uv; then
  step "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"

# 2. Hermes: use existing, else official install
if have hermes && hermes --version >/dev/null 2>&1; then
  step "Using existing Hermes: $(hermes --version)"
else
  step "Installing latest Hermes (official installer)"
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# 3. IntentFrame pack (tarball, no git needed)
step "Downloading IntentFrame integration pack (${VERSION})"
rm -rf "${INSTALL_DIR}"; mkdir -p "${INSTALL_DIR}"
curl -fsSL "https://github.com/${ORG}/${REPO}/archive/refs/heads/${VERSION}.tar.gz" \
  | tar -xz -C "${INSTALL_DIR}" --strip-components=1
export INTENTFRAME_INTEGRATIONS_ROOT="${INSTALL_DIR}"
cd "${INSTALL_DIR}"

IF="${INSTALL_DIR}/bin/intentframe-integrations"

step "Installing Python workspace"
uv sync --all-packages

step "Installing IntentFrame plugin into Hermes"
"${IF}" integrate hermes --copy

step "Installing intentframe-integrations on PATH (${LOCAL_BIN})"
mkdir -p "${LOCAL_BIN}"
ln -sf "${IF}" "${LOCAL_BIN}/intentframe-integrations"

# 4. Env so CLI + web + gateway all hit the adapter
step "Writing plugin env to ${HERMES_ENV}"
mkdir -p "${HOME}/.hermes"; touch "${HERMES_ENV}"
for line in \
  "IF_AGENT_ADAPTER_SOCKET=~/.intentframe/integrations/hermes/adapter.sock" \
  "HERMES_GOVERNANCE_YAML=~/.intentframe/integrations/hermes/governance/tools.yaml" \
  "IF_DYNAMIC_BUNDLE_MANIFEST=~/.intentframe/integrations/hermes/governance/generic_actions.manifest"; do
  key="${line%%=*}"
  grep -q "^${key}=" "${HERMES_ENV}" || echo "${line}" >> "${HERMES_ENV}"
done

cat <<EOF

Done.

  export OPENAI_API_KEY=sk-...
  intentframe-integrations start hermes
  hermes dashboard        # http://localhost:9119  → Chat

Verify gating:  tail -f ~/.intentframe/integrations/hermes/adapter.log

(${LOCAL_BIN} is on PATH if you opened a new shell, or run: export PATH="${LOCAL_BIN}:\$PATH")
EOF