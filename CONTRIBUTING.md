# Contributing to IntentFrame Agent Integrations

Thanks for your interest in contributing. This repository ships integration packs
that connect AI agents to the [IntentFrame](https://github.com/intentframe/intentframe)
policy runtime. [Hermes Agent](https://github.com/NousResearch/hermes-agent) is the
first supported integration.

## Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** — dependency management and virtual environments
- **Node.js 22+** and **npm** — TypeScript bridge client build
- **Linux or macOS** — matches the supported install path

Optional for full-stack tests:

- `OPENAI_API_KEY` — gateway E2E and live integration probes
- Local clones of upstream repos under `external-reference-only-libs/` (gitignored;
  not required for CI)

## Setup

```bash
git clone https://github.com/intentframe/agent-integrations.git
cd agent-integrations
uv sync --all-packages
npm ci && npm run build
cd intentframe-control-plane/web && npm ci && npm run build
```

The dev launcher is `./bin/intentframe-integrations`.

### Control plane frontend

When you change `intentframe-control-plane/web/`, rebuild and **commit** the output:

```bash
cd intentframe-control-plane/web && npm run build
git add ../src/intentframe_control_plane/static/
```

Static assets under `src/intentframe_control_plane/static/` are git-tracked so installs and Docker work without Node.js. CI verifies `static/index.html` exists after build.

## Running tests

```bash
./scripts/e2e.sh
```

Targeted suites:

```bash
uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_integration_pack.py
uv run --directory integrations/hermes/adapter python tests/test_adapter.py
RUN_HERMES_GATEWAY_E2E=1 ./scripts/e2e.sh   # opt-in; slow + networked
```

Install regression tests:

```bash
bash tests/install/test_ref_resolution.sh
bash tests/install/test_installer_bootstrap_docker.sh
bash tests/install/test_installer_curl_docker.sh
bash tests/docker/test_control_plane_smoke.sh   # local throwaway CP lifecycle smoke
```

## Project structure

| Path | Purpose |
|------|---------|
| `intentframe-integrations-cli/` | User-facing CLI |
| `intentframe-control-plane/` | Operator UI (React) + FastAPI server on :9720 |
| `if-integration-backend/` | Validate-only IntentFrame runtime supervisor |
| `if-integration-clients/` | Bridge clients (Python + TypeScript) |
| `integrations/hermes/` | Hermes plugin, adapter, governance templates |
| `integrations/_template/` | Scaffold for new agent integrations |
| `tests/intentframe_control_plane/` | Control plane lifecycle + API unit tests |
| `tests/docker/` | Production-like Docker user journey (CP :9720 + chat :9119) |
| `tests/` | Unit, install, Docker, and gateway E2E tests |

Use `uv sync --all-packages` from the repo root. Do not install workspace members
in isolation with plain `pip install -e .`.

## Making changes

1. Branch from `main`
2. Make focused changes — one logical concern per commit when possible
3. Run relevant tests locally
4. Open a pull request with a clear description of what changed and why

Update docs when you change governed tools, CLI commands, install behavior, or
policy contracts. Keep `RELEASE.json` and package versions aligned when cutting
a release (see `.github/workflows/release.yml`).

## Style

- Match surrounding code — naming, types, and documentation level
- Avoid comments that restate obvious code; explain non-obvious intent only
- Prefer minimal, focused diffs

## Security

Do not open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

Original code in this repository is licensed under [Apache-2.0](LICENSE). See
[NOTICE](NOTICE) for upstream IntentFrame runtime dependency licenses.

By contributing, you agree that your contributions are licensed under the same
Apache-2.0 terms as the rest of this repository.
