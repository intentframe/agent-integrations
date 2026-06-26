# IntentFrame × Hermes

**Structural security for [Hermes Agent](https://github.com/NousResearch/hermes-agent)** — validate tool calls before they touch your machine.

Hermes gives you a capable agent with terminal, files, and tools. IntentFrame adds the governance layer: every dangerous action crosses a policy boundary first. The model proposes; IntentFrame judges; only then does Hermes execute.

[Install](#install) · [Run](#run-three-commands) · [CLI reference](docs/hermes-cli.md) · [Integration guide](docs/hermes-intentframe-integration-guide.md) · [IntentFrame core](https://github.com/intentframe/intentframe)

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

**Requires:** Linux or macOS, network, `curl`. Installs [uv](https://github.com/astral-sh/uv) when missing. Puts `intentframe-integrations` on PATH: `/usr/local/bin` when writable (root/Docker/Linux), always `~/.local/bin` (plus shell config on Mac when `/usr/local/bin` is not writable).

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

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| `OPENAI_API_KEY` | Required for `up hermes` and chat |
| Hermes LLM config | Install uses `--skip-setup` for speed. If chat returns **401**, run `hermes setup` and pick OpenAI, or edit `~/.hermes/config.yaml` |
| `intentframe-integrations` on PATH | Installer symlinks `/usr/local/bin` (when writable) and `~/.local/bin`; no manual `export PATH` on root/Docker |

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

---

## Documentation

| Doc | Audience |
|-----|----------|
| [docs/hermes-cli.md](docs/hermes-cli.md) | CLI commands — governance, policy, gateway, env vars |
| [docs/hermes-intentframe-integration-guide.md](docs/hermes-intentframe-integration-guide.md) | Architecture, adding tools, troubleshooting |
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

```bash
RUN_HERMES_GATEWAY_E2E=1 ./scripts/e2e.sh   # optional, slow + networked
./scripts/clean-project.sh                  # reset local runtime state
```

Package docs: `if-integration-backend/README.md`, `if-integration-clients/README.md`.
