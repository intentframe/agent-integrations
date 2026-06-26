#!/usr/bin/env bash
# User journey: install plugin → seed OpenAI config → start stack → Hermes dashboard.
set -euo pipefail

export PATH="/root/.local/bin:/usr/local/bin:${PATH}"

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
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
  if [[ -f /install-hermes-plugin.sh ]]; then
    step "Installing from mounted /install-hermes-plugin.sh"
    bash /install-hermes-plugin.sh
  else
    version="${VERSION:-main}"
    url="https://github.com/intentframe/agent-integrations/raw/${version}/scripts/install-hermes-plugin.sh"
    step "Installing from ${url}"
    curl -fsSL "${url}" | bash
  fi
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY must be set" >&2
  exit 1
fi

export PATH="/root/.local/bin:/usr/local/bin:${PATH}"

seed_hermes_openai_config() {
  step "Seeding Hermes OpenAI config (provider=${HERMES_PROVIDER}, model=${HERMES_MODEL})"
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
  OPENAI_API_KEY="${OPENAI_API_KEY}" \
  "${python_bin}" - <<'PY'
import os
from pathlib import Path

import yaml

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

seed_hermes_openai_config

step "Starting IntentFrame backend + Hermes adapter"
intentframe-integrations start hermes

step "Starting Hermes dashboard on 0.0.0.0:9119"
echo ""
echo "  Open http://localhost:9119/chat"
echo "  Verify gating: docker compose -f tests/docker/docker-compose.test.yml exec hermes-intentframe \\"
echo "    tail -f /root/.intentframe/integrations/hermes/adapter.log"
echo ""

exec hermes dashboard --host 0.0.0.0 --insecure --no-open
