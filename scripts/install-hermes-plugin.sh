#!/usr/bin/env bash
# Install Hermes (if missing) + IntentFrame plugin.
#
#   curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
#
# Docker / CI (skip Hermes setup wizard + browser engine):
#   curl -fsSL .../install-hermes-plugin.sh | bash -s -- --headless
#
# Then:
#   export OPENAI_API_KEY=sk-...
#   intentframe-integrations up hermes
#   hermes dashboard            # http://localhost:9119
set -euo pipefail

HEADLESS=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --headless)
      HEADLESS=true
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: install-hermes-plugin.sh [--headless]

  --headless   Skip Hermes setup wizard and browser engine (faster; for testers/CI/Docker).
               Default: full Hermes install for end users.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

ORG="${ORG:-intentframe}"
REPO="${REPO:-agent-integrations}"
VERSION="${VERSION:-main}"
INSTALL_DIR="${INSTALL_DIR:-${HOME}/.intentframe/agent-integrations}"
LOCAL_BIN="${HOME}/.local/bin"
SYSTEM_BIN="/usr/local/bin"
HERMES_ENV="${HOME}/.hermes/.env"
CLI_SYSTEM=""
HERMES_SUMMARY=""

step() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

ensure_local_bin_on_path() {
  local path_line='export PATH="$HOME/.local/bin:$PATH"'
  local rc
  for rc in "${HOME}/.zshrc" "${HOME}/.bashrc" "${HOME}/.profile"; do
    [[ -f "${rc}" ]] || continue
    grep -qF '.local/bin' "${rc}" && continue
    {
      echo ''
      echo '# Added by IntentFrame Hermes installer'
      echo "${path_line}"
    } >> "${rc}"
  done
  export PATH="${LOCAL_BIN}:${SYSTEM_BIN}:${PATH}"
}

install_cli_on_path() {
  mkdir -p "${LOCAL_BIN}"
  ln -sf "${IF_CLI}" "${LOCAL_BIN}/intentframe-integrations"

  if [[ "$(id -u)" -eq 0 ]] && [[ ! -d "${SYSTEM_BIN}" ]]; then
    mkdir -p "${SYSTEM_BIN}"
  fi
  if [[ -d "${SYSTEM_BIN}" && ( -w "${SYSTEM_BIN}" || "$(id -u)" -eq 0 ) ]]; then
    ln -sf "${IF_CLI}" "${SYSTEM_BIN}/intentframe-integrations" 2>/dev/null || true
    if [[ -e "${SYSTEM_BIN}/intentframe-integrations" ]]; then
      CLI_SYSTEM="${SYSTEM_BIN}/intentframe-integrations"
    fi
  fi

  ensure_local_bin_on_path
}

# 1. uv
if ! have uv; then
  step "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"

# 2. Hermes: use existing, else official install
if have hermes && hermes --version >/dev/null 2>&1; then
  HERMES_VER="$(hermes --version 2>/dev/null || true)"
  step "Using existing Hermes: ${HERMES_VER}"
  HERMES_SUMMARY="Reused existing Hermes (${HERMES_VER})"
else
  if [[ "${HEADLESS}" == true ]]; then
    step "Installing latest Hermes (headless: skip setup wizard + browser engine)"
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser
    HERMES_SUMMARY="Installed Hermes 0.17+ (headless — no setup wizard; configure API keys yourself)"
  else
    step "Installing latest Hermes (official installer — full setup)"
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
    HERMES_SUMMARY="Installed Hermes (full install — setup wizard runs when needed)"
  fi
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# 3. IntentFrame pack (tarball, no git needed)
step "Downloading IntentFrame integration pack (${VERSION})"
rm -rf "${INSTALL_DIR}"; mkdir -p "${INSTALL_DIR}"
curl -fsSL "https://github.com/${ORG}/${REPO}/archive/refs/heads/${VERSION}.tar.gz" \
  | tar -xz -C "${INSTALL_DIR}" --strip-components=1
export INTENTFRAME_INTEGRATIONS_ROOT="${INSTALL_DIR}"
cd "${INSTALL_DIR}"

IF_DEV="${INSTALL_DIR}/bin/intentframe-integrations"
IF_CLI="${INSTALL_DIR}/.venv/bin/intentframe-integrations"

step "Installing Python workspace"
uv sync --all-packages

step "Installing IntentFrame plugin into Hermes"
"${IF_CLI}" integrate hermes --copy

step "Installing intentframe-integrations on PATH"
install_cli_on_path

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

PATH_HINT='intentframe-integrations is on PATH in this shell.'
if ! have intentframe-integrations; then
  PATH_HINT='Open a new terminal, or run: source ~/.zshrc   # if intentframe-integrations is not found'
fi

CLI_LINES="  CLI:     ${LOCAL_BIN}/intentframe-integrations"
if [[ -n "${CLI_SYSTEM}" ]]; then
  CLI_LINES="  CLI:     ${CLI_SYSTEM}
  CLI:     ${LOCAL_BIN}/intentframe-integrations"
fi

HERMES_NEXT=""
if [[ "${HEADLESS}" == true ]]; then
  HERMES_NEXT="
Hermes (headless): run hermes setup if API keys are not configured yet."
fi

cat <<EOF

Done.

Hermes:
  ${HERMES_SUMMARY}
  Plugin:  ~/.hermes/plugins/intentframe-gate (enabled in ~/.hermes/config.yaml)
  Config:  ~/.hermes/config.yaml
  Env:     ~/.hermes/.env (adapter socket + governance paths)

IntentFrame:
${CLI_LINES}
  Pack:    ${INSTALL_DIR}
  Policy:  ~/.intentframe/integrations/hermes/policy.yaml
  Tools:   ~/.intentframe/integrations/hermes/governance/tools.yaml

Next:
  export OPENAI_API_KEY=sk-...
  intentframe-integrations up hermes
  hermes dashboard        # http://localhost:9119  → Chat
${HERMES_NEXT}

Verify gating:  tail -f ~/.intentframe/integrations/hermes/adapter.log

${PATH_HINT}
EOF
