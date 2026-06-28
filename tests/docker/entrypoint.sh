#!/usr/bin/env bash
# Docker harness: GitHub install → control plane (9720) → up hermes → dashboard (9119).
set -euo pipefail

export PATH="/root/.local/bin:/usr/local/bin:${PATH}"

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
IF_ENV="${HOME:-/root}/.intentframe/.env"
CONTROL_PLANE_PORT="${INTENTFRAME_CONTROL_PLANE_PORT:-9720}"
HERMES_DASHBOARD_PORT="${HERMES_DASHBOARD_PORT:-9119}"
HERMES_PROVIDER="${HERMES_E2E_OPENAI_PROVIDER:-openai-api}"
HERMES_API_MODE="${HERMES_E2E_OPENAI_API_MODE:-chat_completions}"
HERMES_MODEL="${INTENTFRAME_HERMES_E2E_MODEL:-gpt-4o-mini}"

step() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

step "Installing OS packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl tar ca-certificates xz-utils git
rm -rf /var/lib/apt/lists/*

if ! have intentframe-integrations; then
  ref="${REF:-${VERSION:-main}}"
  url="https://github.com/intentframe/agent-integrations/raw/${ref}/scripts/install-hermes-plugin.sh"
  step "Installing from ${url} (ref=${ref})"
  curl -fsSL "${url}" | bash -s -- --headless --no-control-plane --ref "${ref}"
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY must be set" >&2
  exit 1
fi

export PATH="/root/.local/bin:/usr/local/bin:${PATH}"

seed_hermes_runtime_config() {
  step "Seeding Hermes config (provider=${HERMES_PROVIDER}, model=${HERMES_MODEL})"
  local python_bin=""
  for candidate in \
    /usr/local/lib/hermes-agent/venv/bin/python \
    "${HOME}/.intentframe/integrations/hermes/hermes-agent-venv/bin/python"; do
    if [[ -x "${candidate}" ]]; then
      python_bin="${candidate}"
      break
    fi
  done
  if [[ -z "${python_bin}" ]] && have python3; then
    python_bin="$(command -v python3)"
  fi
  if [[ -z "${python_bin}" ]]; then
    echo "ERROR: no Python found to seed Hermes config" >&2
    exit 1
  fi

  HERMES_HOME="${HERMES_HOME}" \
  HERMES_PROVIDER="${HERMES_PROVIDER}" \
  HERMES_API_MODE="${HERMES_API_MODE}" \
  HERMES_MODEL="${HERMES_MODEL}" \
  HERMES_DASHBOARD_USER="${HERMES_DASHBOARD_USER:-hermes}" \
  HERMES_DASHBOARD_PASSWORD="${HERMES_DASHBOARD_PASSWORD:-docker-test}" \
  OPENAI_API_KEY="${OPENAI_API_KEY}" \
  "${python_bin}" - <<'PY'
import os
from pathlib import Path

import yaml
from plugins.dashboard_auth.basic import hash_password

home = Path(os.environ["HERMES_HOME"])
config_path = home / "config.yaml"
env_path = home / ".env"

cfg: dict = {}
if config_path.is_file():
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        cfg = raw

model_cfg = cfg.get("model")
if not isinstance(model_cfg, dict):
    model_cfg = {}
    cfg["model"] = model_cfg
model_cfg["provider"] = os.environ["HERMES_PROVIDER"]
model_cfg["default"] = os.environ["HERMES_MODEL"]
model_cfg["api_mode"] = os.environ["HERMES_API_MODE"]
if os.environ["HERMES_PROVIDER"] == "openai-api":
    model_cfg.pop("base_url", None)

dashboard_cfg = cfg.get("dashboard")
if not isinstance(dashboard_cfg, dict):
    dashboard_cfg = {}
    cfg["dashboard"] = dashboard_cfg
dashboard_cfg["basic_auth"] = {
    "username": os.environ["HERMES_DASHBOARD_USER"],
    "password_hash": hash_password(os.environ["HERMES_DASHBOARD_PASSWORD"]),
}

home.mkdir(parents=True, exist_ok=True)
config_path.write_text(
    yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False),
    encoding="utf-8",
)

env_values: dict[str, str] = {}
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env_values[key.strip()] = value.strip()
env_values["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
env_path.write_text(
    "\n".join(f"{k}={v}" for k, v in env_values.items()) + "\n",
    encoding="utf-8",
)
PY
}

seed_hermes_runtime_config

seed_control_plane_docker_config() {
  step "Seeding IntentFrame Control Plane config (bind 0.0.0.0:${CONTROL_PLANE_PORT})"
  mkdir -p "$(dirname "${IF_ENV}")"
  touch "${IF_ENV}"
  for line in \
    "INTENTFRAME_CONTROL_PLANE_HOST=0.0.0.0" \
    "INTENTFRAME_CONTROL_PLANE_PORT=${CONTROL_PLANE_PORT}" \
    "INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1" \
    "HERMES_DASHBOARD_HOST=127.0.0.1" \
    "HERMES_DASHBOARD_PORT=${HERMES_DASHBOARD_PORT}"; do
    key="${line%%=*}"
    if grep -q "^${key}=" "${IF_ENV}"; then
      sed -i "s|^${key}=.*|${line}|" "${IF_ENV}"
    else
      echo "${line}" >> "${IF_ENV}"
    fi
  done
}

start_control_plane() {
  step "Starting IntentFrame Control Plane on 0.0.0.0:${CONTROL_PLANE_PORT}"
  export INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1
  if ! intentframe-integrations control-plane start --host 0.0.0.0 --port "${CONTROL_PLANE_PORT}"; then
    echo "WARNING: control plane failed to start (see /root/.intentframe/logs/control-plane.log)" >&2
  fi
}

seed_control_plane_docker_config
start_control_plane

step "Starting Hermes + IntentFrame stack (chat-ready)"
intentframe-integrations up hermes

step "Starting Hermes dashboard on 0.0.0.0:9119"
echo ""
echo "  IntentFrame Control Plane: http://localhost:${CONTROL_PLANE_PORT}"
echo "  Hermes chat:               http://localhost:${HERMES_DASHBOARD_PORT}/chat"
echo "  Dashboard auth: ${HERMES_DASHBOARD_USER:-hermes} / ${HERMES_DASHBOARD_PASSWORD:-docker-test}"
echo "  Logs / gating analysis: tests/docker/README.md#logs-and-analysis-inside-the-container"
echo "  Tail policy log: docker compose -f tests/docker/docker-compose.test.yml exec hermes-intentframe \\"
echo "    tail -f /root/.intentframe/logs/intentframe-server.log"
echo ""

exec hermes dashboard --host 0.0.0.0 --no-open
