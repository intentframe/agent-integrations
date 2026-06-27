# Govern your AI agent's tools
### The IntentFrame security plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent)

<p align="center">
  <a href="https://github.com/intentframe/agent-integrations/releases"><img alt="Release" src="https://img.shields.io/github/v/release/intentframe/agent-integrations?label=release"></a>
  <a href="https://github.com/intentframe/agent-integrations/actions/workflows/pr.yml"><img alt="CI" src="https://github.com/intentframe/agent-integrations/actions/workflows/pr.yml/badge.svg"></a>
  <a href="https://github.com/NousResearch/hermes-agent"><img alt="Hermes Agent" src="https://img.shields.io/badge/Hermes-Agent-6f42c1"></a>
  <a href="https://github.com/intentframe/intentframe"><img alt="IntentFrame" src="https://img.shields.io/badge/IntentFrame-policy%20runtime-2563eb"></a>
</p>

**Put an external checkpoint in front of the tools [Hermes Agent](https://github.com/NousResearch/hermes-agent) runs on your machine — terminal, code, file writes, cron — powered by [IntentFrame](https://github.com/intentframe/intentframe).**

IntentFrame is a separate policy runtime, not part of the agent: it judges Hermes's risky actions from *outside* the agent, against rules you set, before they run. Hermes proposes; IntentFrame judges; a governed action runs only on **ALLOW**. (IntentFrame's integration layer is agent-agnostic — Hermes is the first integration.)

[Install](#install-intentframe-into-hermes) · [See a BLOCK](#see-it-work) · [Choose what's governed](#control-which-hermes-tools-are-governed) · [Write policy](#modify-intentframe-policy) · [Docs](#status-and-resources)

---

## Get started with Hermes

[Hermes Agent](https://github.com/NousResearch/hermes-agent) is Nous Research's self-improving agent — terminal, tools, memory, cron, and a chat dashboard. This IntentFrame plugin routes its tool calls through IntentFrame so each governed call is checked before it runs.

**Governed out of the box:** `terminal` · `execute_code` · `write_file` · `patch` · `cronjob`  
The tools that can actually touch your machine — all checked by default. Every other Hermes tool runs untouched.

```text
You → Hermes proposes an action → IntentFrame checks your policy
                                      ├─ ALLOW ✓  runs
                                      └─ BLOCK ✗  logged, never runs
```

## Why IntentFrame on top of Hermes?

Hermes already has command approval, allowlists, and container isolation — but those run *inside* the agent stack. A confused or hijacked model is asking the same process that's supposed to stop it. IntentFrame moves the decision out:

| | Hermes alone | Hermes + IntentFrame |
|---|---|---|
| Where the rules live | Prompts, config, allowlists inside Hermes | Policy you write, **outside** the agent |
| Who validates risky tools | The Hermes runtime | IntentFrame, before the action runs |
| If the model is tricked or wrong | Same process that wanted to act | An external judge blocks it + leaves an audit trail |

## What the Hermes integration installs

Without forking Hermes or rewriting its tools, the integration installs:

- A Hermes plugin that catches selected tool calls before Hermes runs them.
- A small adapter that translates Hermes actions into IntentFrame checks.
- An IntentFrame backend that decides **ALLOW** or **BLOCK**.
- CLI commands to install, start, stop, choose governed tools, and update policy.

This integration ships governance for the following Hermes tools, all enabled by default:

| Hermes tool | IntentFrame action | What it protects |
|-------------|-------------------|------------------|
| `terminal` | `RUN_COMMAND` | Shell commands before execution |
| `execute_code` | `RUN_COMMAND` | Generated code before execution |
| `write_file` | `WRITE_HOST_FILE` | Host file writes |
| `patch` | `WRITE_HOST_FILE` / `DELETE_HOST_FILE` | File edits and deletes |
| `cronjob` | `HERMES_CRONJOB` | Scheduled autonomous work |

Ungoverned Hermes tools continue to work normally.

## Install IntentFrame Into Hermes

No git clone required:

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
```

Then run Hermes with IntentFrame:

```bash
export OPENAI_API_KEY=sk-...
intentframe-integrations up hermes
hermes dashboard
```

Open:

```text
http://localhost:9119/chat
```

Ask Hermes to run a terminal command. If the tool is governed, IntentFrame validates it before Hermes executes it.

---

## See It Work

Example probes from the Docker gating session:

| Prompt | Expected result |
|--------|-----------------|
| `sudo echo test` | **BLOCK**: privilege escalation |
| write a file under `/etc` | **BLOCK**: path outside policy |
| read `~/.hermes/.env` | **BLOCK**: credential access |
| list cron jobs | **ALLOW** or semantic review, depending on policy |

Full captured session: [tests/docker/logs/2026-06-26-hermes-gating-session.md](tests/docker/logs/2026-06-26-hermes-gating-session.md)

---

## Governed Tools vs Policy

There are two separate controls:

| Control | What it means | Runtime file |
|---------|---------------|--------------|
| Governed tools | Which Hermes tools are routed through IntentFrame | `~/.intentframe/integrations/hermes/governance/tools.yaml` |
| Policy | Which routed actions are allowed or blocked | `~/.intentframe/integrations/hermes/policy.yaml` |

A tool must be **governed** for IntentFrame to see it.  
A governed tool must then pass **policy** before it executes.

---

## Control Which Hermes Tools Are Governed

List governed tools:

```bash
intentframe-integrations governance list hermes
```

Enable governance for a tool:

```bash
intentframe-integrations governance enable hermes terminal
```

Disable governance for a tool:

```bash
intentframe-integrations governance disable hermes terminal
```

Restart the Hermes gateway and adapter after changing governed tools:

```bash
intentframe-integrations stop
intentframe-integrations up hermes
```

---

## Modify IntentFrame Policy

Show the current Hermes policy:

```bash
intentframe-integrations policy show hermes
```

Use your own policy file:

```bash
intentframe-integrations policy set hermes /path/to/policy.yaml
```

Reload policy after editing:

```bash
intentframe-integrations policy reload hermes
```

Reset to the bundled default:

```bash
intentframe-integrations policy reset hermes
```

Policy changes apply immediately. You do not need to restart Hermes just to reload policy.

---

## Basic Policy Example

IntentFrame policy is deny-by-default: actions must appear under `allowed_actions`.

```yaml
intentframe_schema_version: 1
agent_id: hermes

allowed_actions:
  RUN_COMMAND:
    safe: false
    constraints:
      blocked_patterns:
        - sudo
        - "rm -rf /"
      deny_capabilities:
        - "capability:data_read:credential_material"
        - "capability:system_mutate:privilege_config"

  WRITE_HOST_FILE:
    safe: false
    constraints:
      allowed_host_paths:
        - "~/*"

  DELETE_HOST_FILE:
    safe: false
    constraints:
      allowed_host_paths:
        - "~/*"

  HERMES_CRONJOB:
    safe: false

intent_limits:
  - limit_id: no-secret-exfil
    domain: data_access
    description: Block reading secrets or credential material
    raw: Do not read credentials, tokens, cookies, secret files, or upload private data to untrusted destinations.
    effect: block
```

Useful policy concepts:

- `allowed_actions`: which IntentFrame actions can be considered at all.
- `safe: true`: action can pass through simpler checks.
- `safe: false`: action is consequential and should be reviewed more carefully.
- `constraints`: deterministic limits like allowed paths or blocked command patterns.
- `intent_limits`: plain-English rules the Guardian uses for semantic policy review.
- `domain_constraints`: structured rules for specific domains like deletion or spending.

Full IntentFrame policy guide:  
[docs/user_policy_yaml_guide.md](https://github.com/intentframe/intentframe/blob/main/docs/user_policy_yaml_guide.md)

---

## Install Options

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

**Pinned release** (script URL and pack ref should match):

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/v0.2.0/scripts/install-hermes-plugin.sh | bash -s -- --ref v0.2.0
```

After headless install, set `OPENAI_API_KEY` (and run `hermes setup` if chat returns 401). Then the same [three commands](#run-three-commands) as below.

**Known limitations** (full uninstall on root/Docker): [docs/hermes-known-limitations.md](docs/hermes-known-limitations.md).

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
| `+ --remove-hermes` | Also delete all of `~/.hermes` (config, sessions, logs) and `hermes` CLI symlinks. Root/Linux FHS code under `/usr/local/lib/hermes-agent/` is **not** removed yet — [caveats](docs/hermes-known-limitations.md). |

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

## Status and Resources

**Current release:** [v0.2.0](https://github.com/intentframe/agent-integrations/releases/tag/v0.2.0)  
**Integration maturity:** Hermes plugin + adapter + CLI; Docker E2E; known uninstall caveats on root/FHS — [limitations](docs/hermes-known-limitations.md).

### Documentation

| Doc | Audience |
|-----|----------|
| [docs/hermes-cli.md](docs/hermes-cli.md) | CLI commands — governance, policy, gateway, env vars |
| [docs/hermes-known-limitations.md](docs/hermes-known-limitations.md) | Install/uninstall caveats and roadmap |
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
| `integrations/_template/` | Scaffold for adding a new agent integration |
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

<!-- IntentFrame integrations for AI agents · Hermes Agent security plugin · Nous Research · agent tool gating · policy-as-code · ai governance -->
