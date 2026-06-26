# IntentFrame × Hermes

**Structural security for [Hermes Agent](https://github.com/NousResearch/hermes-agent)** — validate tool calls before they touch your machine.

Hermes gives you a capable agent with terminal, files, and tools. IntentFrame adds the governance layer: every dangerous action crosses a policy boundary first. The model proposes; IntentFrame judges; only then does Hermes execute.

[Install](#install) · [Run](#run-three-commands) · [Uninstall](#uninstall) · [CLI reference](docs/hermes-cli.md) · [Integration guide](docs/hermes-intentframe-integration-guide.md) · [IntentFrame core](https://github.com/intentframe/intentframe)

---

## Who is this for?

| If you are… | What this gives you |
|-------------|---------------------|
| Running Hermes on your own machine | Governed `terminal`, `write_file`, `patch`, and `cronjob` — with a required **reason** on each call |
| Shipping agents to users who need guardrails | Policy-driven ALLOW/BLOCK before side effects, not prompt-only hope |
| Evaluating IntentFrame with a real agent | Production-shaped plugin + adapter + CLI — not a toy wrapper |
| Contributing to the integration | Monorepo with plugin, adapter, backend bridge, and E2E tests |

---

## What you get

When Hermes calls a **governed** tool, IntentFrame sits in the path:

| Hermes tool | IntentFrame action |
|-------------|-------------------|
| `terminal` | `RUN_COMMAND` |
| `write_file`, `patch` | `WRITE_HOST_FILE` / `DELETE_HOST_FILE` |
| `cronjob` | `HERMES_CRONJOB` |

```
You → hermes dashboard → LLM → intentframe-gate → adapter → IntentFrame policy → ALLOW → Hermes runs
```

Ungoverned Hermes tools work as usual. Toggle which tools are governed with the CLI — [docs/hermes-cli.md](docs/hermes-cli.md).

---

## Install

No git clone. One script installs Hermes (if needed), the integration pack, and the `intentframe-gate` plugin:

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
```

**Requires:** Linux or macOS, network, `curl`. Installs [uv](https://github.com/astral-sh/uv) when missing. Runs the **full** Hermes installer by default (setup wizard when needed).

**PATH:** symlinks `intentframe-integrations` to `~/.local/bin` and `/usr/local/bin` when writable. May append `~/.local/bin` to shell rc only if it is not already there — see [docs/hermes-cli.md#install](docs/hermes-cli.md#install).

**Headless install** (skip Hermes setup wizard + browser engine — for testers who already have API keys):

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash -s -- --headless
```

From a git clone (same flags):

```bash
bash scripts/install-hermes-plugin.sh --headless
```

After headless install, set `OPENAI_API_KEY` (and run `hermes setup` if chat returns 401). Then the same [three commands](#run-three-commands) as below.

---

## Run (three commands)

```bash
export OPENAI_API_KEY=sk-...
intentframe-integrations up hermes
hermes dashboard
```

Open **http://localhost:9119/chat**. Ask Hermes to run a terminal command — IntentFrame gates it in the background.

**Smoke-test gating:**

```bash
tail -f ~/.intentframe/integrations/hermes/adapter.log
```

Try something policy should block (e.g. `sudo …`) and look for `BLOCK` in the log.

---

## Uninstall

```bash
intentframe-integrations stop || true
intentframe-integrations uninstall hermes              # IntentFrame only; Hermes stays
intentframe-integrations uninstall hermes --remove-hermes   # IntentFrame + all of Hermes
```

| Command | Effect |
|---------|--------|
| `uninstall hermes` | Remove IntentFrame (`~/.intentframe`, plugin, CLI). **Hermes stays** at `~/.hermes`. |
| `+ --remove-hermes` | Also delete all of `~/.hermes` (config, agent source, sessions, logs) and `hermes` CLI symlinks. |

Uninstall removes the `intentframe-integrations` CLI and pack — there is no `integrate` afterward. To use IntentFrame again, run the [install script](#install) again (not `integrate`).

**Verify** (new terminal):

```bash
command -v intentframe-integrations || echo "IF CLI: gone"
command -v hermes || echo "hermes CLI: gone"
test -e ~/.intentframe || echo "~/.intentframe: gone"
test -e ~/.hermes || echo "~/.hermes: gone"
grep -F 'IntentFrame Hermes installer' ~/.zshrc ~/.bashrc ~/.profile 2>/dev/null \
  || echo "IntentFrame installer rc block: gone (or never added)"
```

After `uninstall hermes` only: `~/.hermes` should still exist. After `--remove-hermes`: all checks should report **gone**.

Full tables (what is / is not removed): [docs/hermes-cli.md#uninstall](docs/hermes-cli.md#uninstall).

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| `OPENAI_API_KEY` | Required for `up hermes` and chat |
| Hermes LLM config | Full install runs `hermes setup` when needed. If chat returns **401**, run `hermes setup` or edit `~/.hermes/config.yaml` |
| `intentframe-integrations` on PATH | Installer symlinks `~/.local/bin` and `/usr/local/bin` (when writable); may skip shell rc if `~/.local/bin` already present |

---

## What `up hermes` starts

| Component | Role |
|-----------|------|
| IntentFrame backend | Policy registry, bridge, executor |
| Hermes adapter | Maps tool args → IntentFrame `/validate` |
| Hermes gateway | Hermes tool runtime + `intentframe-gate` plugin |

`hermes dashboard` is the web UI — run it after `up hermes` (same or another terminal).

---

## Docker smoke test

Same install script, inside a container:

```bash
export OPENAI_API_KEY=sk-...
docker compose -f tests/docker/docker-compose.test.yml up
```

→ **http://localhost:9119/chat** (default login `hermes` / `docker-test`). Details: [tests/docker/README.md](tests/docker/README.md).

**Example session** (chat probes + full IntentFrame audit trail): [tests/docker/logs/2026-06-26-hermes-gating-session.md](tests/docker/logs/2026-06-26-hermes-gating-session.md) · [all session logs](tests/docker/logs/README.md).

---

## Documentation

| Doc | Audience |
|-----|----------|
| [docs/hermes-cli.md](docs/hermes-cli.md) | CLI commands — governance, policy, gateway, env vars |
| [docs/hermes-intentframe-integration-guide.md](docs/hermes-intentframe-integration-guide.md) | Architecture, adding tools, troubleshooting |
| [tests/docker/logs/](tests/docker/logs/README.md) | Captured Docker chat + gating audit sessions (example probes) |
| [integrations/hermes/README.md](integrations/hermes/README.md) | Monorepo dev reference |
| [IntentFrame](https://github.com/intentframe/intentframe) | Core runtime — threat model, principles, Actor SDK |

Terminology: [what “governed” means](docs/agent-tool-gating.md#terminology-what-governed-means).

---

## For contributors

```bash
git clone https://github.com/intentframe/agent-integrations.git
cd agent-integrations
uv sync --all-packages
./scripts/e2e.sh
```

| Path | Purpose |
|------|---------|
| `intentframe-integrations-cli/` | `intentframe-integrations` CLI |
| `integrations/hermes/` | Plugin, adapter, governance templates |
| `if-integration-backend/` | IntentFrame runtime supervisor |
| `if-integration-clients/` | Bridge clients (Python + TypeScript) |
| `tests/hermes_gateway/` | Opt-in gateway E2E (isolated sandbox) |
| `tests/docker/` | Production-like Docker user journey |
| `tests/docker/logs/` | Captured manual gating sessions (chat + audit trail) |

```bash
RUN_HERMES_GATEWAY_E2E=1 ./scripts/e2e.sh   # optional, slow + networked
./scripts/clean-project.sh                  # reset local runtime state
```

Package docs: `if-integration-backend/README.md`, `if-integration-clients/README.md`.
