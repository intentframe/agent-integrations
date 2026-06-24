# IntentFrame native-kit integration guide (Hermes)

> Linux and macOS compatible guidance for wiring Hermes tools through IntentFrame
> **native action bundles** — validate-only, no platform executor pack required.

This document captures design decisions, current repo state, bundle expectations,
and a checklist for adding new governed tools. It complements:

- [`integrations/hermes/README.md`](../integrations/hermes/README.md) — install, commands, quick start
- [`agent-tool-gating.md`](./agent-tool-gating.md) — general gating pattern
- [`governance/tools.yaml`](../integrations/hermes/governance/tools.yaml) — governed-tool contract (source of truth)

---

## 1. What we are doing

Hermes runs tools **locally** (shell, files, browser, etc.). IntentFrame does **not**
replace Hermes execution. Instead:

1. The **plugin** (`intentframe-gate`) intercepts selected Hermes tools, injects a
   required `reason` field into the tool schema, and calls the adapter before the
   real handler runs.
2. The **adapter** maps each tool call to one or more IntentFrame intents and calls
   the bridge `/validate` endpoint.
3. The **backend** loads native-kit **validation bundles** (pure Python policy +
   structural gates). The **validate-only executor** returns synthetic success on
   ALLOW — Hermes still executes the side effect.

```
LLM → governed tool(args + reason)
  → intentframe-gate plugin (Hermes process)
  → POST /validate-tool on adapter UDS
  → hermes-adapter → bridge /validate
  → native bundles (TerminalActionBundle, HostFilesActionBundle, …)
  → validate_only executor (noop)
  → ALLOW → Hermes original handler
  → BLOCK → JSON error, no side effect
```

**Key insight:** validation bundles and policy are **cross-platform**. macOS-only
*executor* packs are not loaded in this integration profile.

### Terminology: governed vs Hermes-enabled

**Governed** = IntentFrame validate-only gate active for a Hermes tool name.
**Not** the same as Hermes exposing or enabling a tool on `/v1/toolsets`.

| | Governed (`enabled: true` in yaml) | Ungoverned |
|---|-----------------------------------|------------|
| Plugin wraps handler | yes | no |
| Schema requires `reason` | yes | no |
| Adapter `/validate` before side effect | yes | no |
| Hermes may still show tool to LLM | often yes | yes |

Full terminology table: [`agent-tool-gating.md`](./agent-tool-gating.md#terminology-what-governed-means).

---

## 2. Current repo state (v1)

### Governed Hermes tools

**Governed** here means the **intentframe-gate plugin** wraps the tool and the
adapter validates before Hermes executes. See [`agent-tool-gating.md`](../../docs/agent-tool-gating.md#terminology-what-governed-means).

Configured in [`governance/tools.yaml`](../integrations/hermes/governance/tools.yaml):

| Hermes tool | IntentFrame action(s) | Mapper kind | Notes |
|-------------|----------------------|-------------|-------|
| `terminal` | `RUN_COMMAND` | `terminal` | Full `command_shield` + capability analysis |
| `write_file` | `WRITE_HOST_FILE` | `write_file` | Path + content |
| `patch` | `WRITE_HOST_FILE`, `DELETE_HOST_FILE` | `patch` | Multi-intent from V4A diff |
| `cronjob` | `HERMES_CRONJOB` | `generic` | Semantic-only via dynamic bundle (AE + Guardian) |

**Ungoverned by design (v1):** reads — `read_file`, `search_files`, `browser_snapshot`,
`web_search`, etc. Ungoverned read + ungoverned outbound channel is an exfil risk;
document explicitly if you leave reads open.

### Agent profile

[`agent.json`](../integrations/hermes/agent.json):

```json
"action_types": ["RUN_COMMAND", "WRITE_HOST_FILE", "DELETE_HOST_FILE", "HERMES_CRONJOB"]
```

Every governed action must appear here **and** in shipped `policy.yaml` **and** in
`executor.yaml` `supported_actions` for validate-only. Generic action IDs are also
listed in committed `governance/generic_actions.manifest` (static superset; copied to runtime
on `integrate hermes`). Golden test:
`tests/intentframe_integrations/test_actions_manifest.py`.

User governance toggles (`enabled` in runtime `tools.yaml`) do **not** change manifest,
policy, or repo templates. Governance and policy are independent gates.

### Policy (seed)

[`policy.yaml`](../integrations/hermes/policy.yaml):

- `RUN_COMMAND`: `blocked_patterns`, `deny_capabilities`, optional `allowed_commands`
- `WRITE_HOST_FILE` / `DELETE_HOST_FILE`: `allowed_host_paths` (e.g. `~/*`)
- `domain_constraints.deletion`: structural deletion guards (paths, irreversibility flags)

### Backend profiles

| Profile | Path | Role |
|---------|------|------|
| Core | `if-integration-backend/.../profiles/core.yaml` | `bundles: [native, dynamic]` — native-kit deterministic bundles + generic dynamic bundle (reads `IF_DYNAMIC_BUNDLE_MANIFEST`) |
| Executor | `if-integration-backend/.../profiles/executor.yaml` | `validate_only` adapter; `supported_actions` list |

[`ValidateOnlyAdapter`](../if-integration-backend/src/if_security_backend/executor_pack/validate_adapter.py)
returns `{ validated_only: true }` without executing on either Linux or macOS.

### Plugin + shared contract

| Component | Location |
|-----------|----------|
| Plugin | `plugin/intentframe-gate/` (legacy key `intentframe-terminal` migrated on integrate; see [`hermes-intentframe-integration-guide.md`](./hermes-intentframe-integration-guide.md) and [`hermes-plugin-registration-order.md`](./hermes-plugin-registration-order.md)) |
| Governance loader | `shared/` → `hermes-governance` package |
| Mapper registry | `adapter/src/hermes_adapter/mapper.py` |
| Multi-intent validate | `adapter/src/hermes_adapter/service.py` — **all** mapped intents must ALLOW |
| CLI / doctor | `intentframe-integrations-cli/.../hermes_integrate.py` — contract vs agent.json vs policy alignment |

### Tests

- Unit: adapter mappers, governance loader, plugin wrap
- Probes: [`tests/hermes_tool_probes.py`](../tests/hermes_tool_probes.py)
- E2E: [`tests/scripts/test-hermes-gateway-e2e.sh`](../tests/scripts/test-hermes-gateway-e2e.sh) — terminal BLOCK today; expand for host-file probes

---

## 3. Linux / macOS compatibility model

### What makes this cross-platform

| Layer | macOS | Linux | Notes |
|-------|-------|-------|-------|
| Native validation bundles | ✅ | ✅ | Pure Python: `command_shield`, path canonicalization, fnmatch constraints |
| Validate-only executor | ✅ | ✅ | No shell/file execution in IF backend |
| Hermes local execution | ✅ | ✅ | Side effects happen in Hermes after ALLOW |
| macOS executor pack | ❌ not loaded | ❌ N/A | Not used in `core.yaml` / `executor.yaml` profile |

### Bundles loaded via `native` entry point

From `intentframe_native_bundles.register_bundles()`:

**Action bundles (15):** terminal, files, host_files, email, api, browser, message,
calendar, reminders, notes, contacts, clipboard, spotlight, system, user_io

**Domain bundles:** finance, deletion

### Platform-specific bundles (validation still runs; execution semantics differ)

These register in native-kit but are **macOS-centric** or need OS APIs at execution time.
For Hermes validate-only gating they can still **judge** intents if you add mappers,
but policy value on Linux may be limited:

- `SpotlightActionBundle` — `SEARCH_SPOTLIGHT`
- `MessageActionBundle` — macOS/iMessage-style contacts resolution
- `CalendarActionBundle`, `RemindersActionBundle`, `NotesActionBundle`
- `SystemActionBundle` — brightness/volume/dark mode (platform UI)

**Recommendation:** prioritize cross-platform Hermes tools (terminal, files, web, browser,
code execution) before macOS-only bundles.

### Path and floor checks (host files)

`HostFilesActionBundle` uses:

- `data.path` as the **executed** resource (not `intent.target` alone)
- `canonicalize_real_path` + deny-prefix floors (`/etc`, `/usr`, `~/.ssh`, …)
- Policy `allowed_host_paths` with fnmatch (e.g. `~/*`)

Works on both POSIX layouts; Windows paths are out of scope for Hermes today.

---

## 4. Responsibilities: plugin vs adapter vs bundles

| Concern | Owner |
|---------|--------|
| Require `reason` on tool schema | Plugin (`inject_reason`) |
| Intercept handler, strip `reason`, delegate | Plugin (`wrap_handler`, `gate_tool_call`) |
| Survive MCP / dynamic `registry.register` | Plugin (patches `registry.register`) |
| Map Hermes args → IntentFrame intent shape | Adapter (`mapper.py`) |
| Local preflight (missing reason, bad args) | Adapter |
| Call bridge `/validate` per intent | Adapter (`ValidateService`) |
| Policy constraints, capability tags, command_shield | Native bundles + `policy.yaml` |
| Structural / domain gates (deletion) | Domain bundles + `domain_constraints` |
| Actual tool execution | Hermes original handler |

**Do not** duplicate bundle logic in the plugin. Policy lives in `policy.yaml`; enforcement
lives in native-kit bundles.

---

## 5. Intent shape expectations (mapped fields)

The adapter must produce intents the bridge and bundles accept. Top-level fields
map into `IntentFrame.data` on the backend.

### `RUN_COMMAND` — `TerminalActionBundle`

**Required in intent:**

| Field | Source | Purpose |
|-------|--------|---------|
| `action` | `"RUN_COMMAND"` | Bundle routing |
| `reason` | Hermes `reason` | Audit / AE |
| `command` | Hermes `command` or synthetic | Executed command (`data.command`) |
| `target` | Truncated command | Display / audit only |

**Policy constraints** (`TerminalConstraints`):

- `blocked_patterns` — substring/regex guards (e.g. `sudo`, `rm -rf /`)
- `deny_capabilities` / `allow_capabilities` — capability tags from `command_shield`
- `allowed_commands` — optional allowlist patterns

**Hermes mappers:**

- `terminal` — passes real shell command → full terminal pipeline

### `WRITE_HOST_FILE` / `DELETE_HOST_FILE` — `HostFilesActionBundle`

**Required in intent:**

| Field | Writes | Deletes |
|-------|--------|---------|
| `action` | `WRITE_HOST_FILE` | `DELETE_HOST_FILE` |
| `reason` | ✅ | ✅ |
| `path` | ✅ | ✅ |
| `content` | ✅ required | omit |
| `target` | path (audit) | path (audit) |
| `irreversible` | optional | recommended for deletes |

**Policy constraints** (`HostFileConstraints`):

- `allowed_host_paths` — fnmatch list (e.g. `~/*`)

**Domain** (`DeletionDomainBundle` via `domain_constraints.deletion`):

- `allowed_paths`, `block_irreversible`, `require_confirmation` (describe-only today)

**Hermes mappers:**

- `write_file` — direct path + content
- `patch` — parses V4A; one intent per Update/Add/Delete (including `DELETE_HOST_FILE` for delete ops); batch metadata in
  `patch_op_index`, `patch_op_count`, `patch_operations`

**Patch caveat:** validation sees patch **body**, not post-merge file content. Path/floor
checks are sound; content analysis is less precise than `write_file`.

---

## 6. Adding a new governed tool (checklist)

Use this whenever you extend beyond the v1 set.

### 1. Pick IntentFrame action(s)

- Find the action in native-kit (`ActionType` or bundle `action_ids`).
- Confirm the action bundle’s `constraints.py` — know which policy keys are valid.
- If the Hermes tool can emit multiple effects (like `patch`), plan **multi-intent** mapping.

### 2. Extend backend validate-only support

Add the action to:

```yaml
# if-integration-backend/.../profiles/executor.yaml
pack_options:
  validate_only:
    supported_actions:
      - RUN_COMMAND
      - WRITE_HOST_FILE
      - DELETE_HOST_FILE
      - YOUR_NEW_ACTION   # ← add here
```

Without this, ALLOW may succeed at Guardian but executor negotiation can fail.

### 3. Governance contract

Add to [`governance/tools.yaml`](../integrations/hermes/governance/tools.yaml):

```yaml
your_tool:
  action: HTTP_POST          # primary action
  actions: [HTTP_POST]       # optional; required if multi-action
  risk: outbound_network     # descriptive
  mapper: your_mapper_kind   # must be in VALID_MAPPER_KINDS or extend loader
  blocked_response: generic_json
```

On first `integrate hermes`, runtime governance at
`~/.intentframe/integrations/hermes/governance/tools.yaml` is seeded from the repo
default template if missing. Later integrates do not overwrite user edits unless
you pass `--reset-governance`. `integrate hermes` prints `export HERMES_GOVERNANCE_YAML=…`
using the effective path (`os.environ` overrides the `agent.json` default).

Optional override: set `HERMES_GOVERNANCE_YAML` in the shell before
`start hermes` / `gateway start hermes`. The CLI preserves an existing value when
building adapter and gateway child environments (`setdefault` on `pack.agent.env`).
`gateway start` logs the effective path as `Hermes governance config: …`.

### 4. Mapper

In [`mapper.py`](../integrations/hermes/adapter/src/hermes_adapter/mapper.py):

- Implement `map_your_tool(args) -> list[IntentDict]`
- Register in `MAPPER_REGISTRY`
- Add mapper kind to `hermes_governance.loader.VALID_MAPPER_KINDS` if new
- Validate `reason` locally (`validate_reason`)
- Put **executed** fields in the shape bundles expect (`url`, `path`, `command`, …)

### 5. Agent profile + policy

- [`agent.json`](../integrations/hermes/agent.json) — add to `action_types`
- [`policy.yaml`](../integrations/hermes/policy.yaml) — `allowed_actions.<ACTION>.constraints` matching bundle schema
- Domain constraints if routed (e.g. deletion domain for file deletes)

### 6. Tests

- Mapper unit tests (ALLOW-shaped and BLOCK-shaped args)
- Probe entry in [`tests/hermes_tool_probes.py`](../tests/hermes_tool_probes.py)
- Gateway E2E script for deterministic BLOCK cases
- Run `bin/intentframe-integrations doctor hermes` — governance/policy/agent alignment

### 7. Plugin changes

**Usually none.** Plugin reads `governance/tools.yaml` and wraps by tool name. Only touch
plugin if you need a new `blocked_response` shape or schema injection behavior.

---

## 7. Other Hermes tools → native-kit actions (candidates)

Below: Hermes registry names mapped to **integrable** IntentFrame actions. Priority
reflects cross-platform value and outbound/state-change risk.

### Tier A — cross-platform, high value (recommended next)

| Hermes tool(s) | Suggested IF action(s) | Bundle | Policy knobs | Notes |
|----------------|------------------------|--------|--------------|-------|
| `web_extract` | `HTTP_GET` | ApiActionBundle | `allowed_endpoints` | Outbound fetch; passive read in bundle |
| `web_search` | `HTTP_GET` or ungoverned | ApiActionBundle | `allowed_endpoints` | Often lower risk if provider-fixed URL |
| `browser_navigate` | `OPEN_URL` | BrowserActionBundle | `allowed_urls` | State-changing navigation |
| `browser_click`, `browser_type`, `browser_press` | `OPEN_URL` or new action | BrowserActionBundle | URL/session context | May need composite intent or RUN_COMMAND fallback |
| `execute_code` | `RUN_COMMAND` | TerminalActionBundle | same as terminal | Map sandbox invocation to synthetic command |
| `cronjob` (create/enable) | `RUN_COMMAND` or system mutate caps | TerminalActionBundle | deny `capability:system_mutate:cron_mutation` | Persistence risk |
| `delegate_task` | Custom / `RUN_COMMAND` | Terminal or new | TBD | Delegation expands blast radius |
| `memory` (write) | `WRITE_HOST_FILE` or dedicated | HostFiles / Files | path scope | If writes agent memory files |
| `computer_use` | `RUN_COMMAND` + UI caps | TerminalActionBundle | deny_capabilities | High risk; treat like terminal |

### Tier B — outbound / comms (policy-heavy)

| Hermes tool(s) | Suggested IF action(s) | Bundle | Policy knobs |
|----------------|------------------------|--------|--------------|
| `discord`, `discord_admin` | `HTTP_POST` / `SEND_MESSAGE` | Api / Message | endpoints, contacts |
| `send_message` (channels) | `SEND_MESSAGE` | MessageActionBundle | `allowed_contacts`, `contact_sources` |
| `feishu_*`, `yb_send_*` | `HTTP_POST`, `SEND_MESSAGE` | Api / Message | endpoint allowlists |
| `text_to_speech`, `image_generate`, `video_generate` | `HTTP_POST` | ApiActionBundle | `allowed_endpoints`, `max_amount` |

### Tier C — reads (govern only if exfil-sensitive)

| Hermes tool(s) | IF action | Bundle | Default |
|----------------|-----------|--------|---------|
| `read_file`, `read_terminal` | `READ_HOST_FILE` | HostFiles / Files | Ungoverned v1 |
| `browser_snapshot`, `browser_get_images` | `GET_PAGE_CONTENT` | BrowserActionBundle | Ungoverned v1 |
| `ha_list_entities`, `ha_get_state` | `HTTP_GET` | ApiActionBundle | Ungoverned v1 |
| `session_search`, `memory` (read) | — | — | Ungoverned; exfil caveat |

### Tier D — macOS / niche (lower Linux priority)

| Hermes tool(s) | IF action | Bundle |
|----------------|-----------|--------|
| Spotlight-style search | `SEARCH_SPOTLIGHT` | SpotlightActionBundle |
| Calendar / Reminders / Notes | various | Calendar / Reminders / Notes |
| `ha_call_service` | `HTTP_POST` | ApiActionBundle |
| `SET_CLIPBOARD` / `GET_CLIPBOARD` | ClipboardActionBundle | clipboard |

### Not in native-kit today

Some Hermes tools (MCP passthrough, kanban, skills hub, mixture_of_agents) have no
1:1 native action. Options:

1. Map to closest action (`RUN_COMMAND` synthetic) with tight policy
2. Add a new native-kit action + bundle (heavier)
3. Leave ungoverned with documented risk

---

## 8. Things to keep in mind

### Validate-only ≠ execute in IF

Native bundles **judge**; Hermes **executes**. Never assume IF ran the command or wrote
the file. Tests must assert on Hermes behavior after ALLOW/BLOCK, not executor output.

### Three-way alignment

Every new action must agree across:

1. `governance/tools.yaml` (tool → action mapping)
2. `agent.json` `action_types`
3. `policy.yaml` `allowed_actions`
4. `executor.yaml` `supported_actions`

`doctor hermes` checks (1)–(3). Easy to forget (4).

### Multi-intent tools must all pass

`ValidateService` validates **sequentially**; one BLOCK fails the tool call. Design mappers
so each intent is independently judgeable (patch pattern).

### `reason` is governance input, not telemetry

Plugin injects it; adapter validates (min length); bridge sends to Guardian. Strip before
Hermes handler so native tools unchanged.

### Mapper quality = security quality

Mapping to intents that exercise the bundle’s real evidence pipeline improves policy
effectiveness (e.g. real shell strings for `RUN_COMMAND`).

### Passive reads in bundles

Many bundles mark read actions as `passive_read_action_ids`. IF may fast-path reads.
If you govern a read for exfil control, confirm passive-read behavior in your deployment.

### Registry lifecycle

Hermes MCP refresh re-registers tools. Plugin hooks `registry.register` to re-wrap.
Add tests that simulate re-registration clobber.

### Per-deployment overrides

- `HERMES_GOVERNANCE_YAML` — alternate governance yaml (which tools are **IntentFrame-governed**). Set in the parent shell before `start` / `gateway start`; CLI child env builders preserve it over `agent.json` defaults.
- `IF_DYNAMIC_BUNDLE_MANIFEST` — path to runtime `generic_actions.manifest` (generic `HERMES_*` action IDs). Default in `agent.json`; CLI applies via `load_and_activate_pack` for `start` and all `policy *` commands. Explicit shell export wins (`setdefault`).
- `HERMES_E2E_GOVERNED_TOOLS` — gateway E2E only; comma-separated subset for LLM probes (not Hermes toolsets). E2E also asserts env parity via `assert_governance_env_contract`.
- **Runtime policy** — `~/.intentframe/integrations/hermes/policy.yaml` (copied from shipped template on first `integrate` / `start`). Edit locally, then `bin/intentframe-integrations policy reload hermes`. Use `policy set`, `policy reset`, or `integrate hermes --reset-policy` to install or restore defaults.

### Platform executor packs are separate

`intentframe_executor_pack_macos` and similar are for **real IF execution**, not this
Hermes hybrid. Do not conflate “bundle registers on macOS” with “needs macOS executor.”

---

## 9. Known gaps (as of v1)

| Gap | Impact | Mitigation |
|-----|--------|------------|
| Ungoverned Hermes `process` tool | Background job manager runs without IF gate | Govern via `terminal` for shell execution; leave `process` ungoverned until a faithful mapper exists |
| `patch` validates diff hunks, not merged file | Weaker write content gates | Prefer `write_file` for sensitive paths; tighten path policy |
| E2E mostly terminal BLOCK | Host-file regressions possible | Add probes for `/etc` write, `~` delete |
| ValidateOnlyAdapter action list | New actions fail silently at executor | Extend `executor.yaml` with each new action |
| Reads ungoverned | Read + outbound exfil | Tier C governance when threat model requires |
| Registry lifecycle tests | MCP refresh could unwrap | Mock re-register tests |

---

## 10. Quick reference — key paths

```
docs/
  NATIVE_KIT_INTEGRATION.md     ← this doc
  agent-tool-gating.md          ← portable gating pattern

integrations/hermes/
  governance/tools.yaml         ← governed tools template (reference)
  agent.json                    ← action_types + adapter socket
  policy.yaml                   ← shipped policy template (reference)
  ~/.intentframe/integrations/hermes/
    governance/tools.yaml       ← runtime governed-tool config (user-owned)
    policy.yaml                 ← runtime policy (user-owned; policy reload hermes)
  adapter/src/hermes_adapter/
    mapper.py                   ← Hermes → IntentFrame intents
    service.py                  ← multi-intent validate
  plugin/intentframe-gate/      ← schema + intercept + lifecycle
  shared/                       ← hermes-governance loader

if-integration-backend/
  config/profiles/core.yaml     ← bundles: [native]
  config/profiles/executor.yaml ← validate_only supported_actions
  executor_pack/validate_adapter.py

external-reference-only-libs/intentframe/.../intentframe-native-kit/
  intentframe_native_bundles/   ← register_bundles(), action bundles

tests/hermes_tool_probes.py     ← BLOCK/ALLOW probe payloads
```

---

## 11. Minimal example — adding `web_extract`

1. **Governance** — add `web_extract` → `HTTP_GET`, mapper `web_extract`
2. **Mapper** — `{ action, reason, url: urls[0], target: url }`
3. **agent.json** — `"HTTP_GET"` in `action_types`
4. **policy.yaml** (shipped template and/or runtime copy under `~/.intentframe/integrations/hermes/`):

   ```yaml
   HTTP_GET:
     safe: false
     constraints:
       allowed_endpoints:
         - "https://*"
   ```

5. **executor.yaml** — add `HTTP_GET` to `supported_actions`
6. **Runtime policy** — `bin/intentframe-integrations policy reload hermes` after editing
   `~/.intentframe/integrations/hermes/policy.yaml`
7. **Tests** — mapper test + probe blocking disallowed host

No plugin edit if `generic_json` blocked response suffices.
