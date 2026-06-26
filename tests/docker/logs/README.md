# Docker test session logs

Captured audit trails from manual Hermes + IntentFrame dashboard runs in Docker. Each report is a full chat transcript plus tool payloads and IntentFrame intent audit.

**Related docs**

- [README.md](../../../README.md) — install + run (end users)
- [tests/docker/README.md](../README.md) — Docker smoke test, log paths, chat probes
- [docs/hermes-intentframe-integration-guide.md](../../../docs/hermes-intentframe-integration-guide.md) — architecture and troubleshooting
- [docs/agent-tool-gating.md](../../../docs/agent-tool-gating.md) — what “governed” means

## Reports

| Report | Description |
|--------|-------------|
| [2026-06-26-hermes-gating-session.md](./2026-06-26-hermes-gating-session.md) | Nine governed tool calls: deterministic ALLOW/BLOCK, semantic ALLOW/BLOCK (`sudo`, path probe, `.env` read, cronjob, `.bashrc` patch) |

To reproduce probes or run log commands yourself, see [../README.md#logs-and-analysis-inside-the-container](../README.md#logs-and-analysis-inside-the-container) and [../README.md#example-chat-probes](../README.md#example-chat-probes).
