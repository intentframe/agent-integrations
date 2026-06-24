# Hermes governance: `execute_code`, schema hooks, and `read_terminal` lessons

> Session knowledge (June 2026): adding governed `execute_code`, fixing model-facing
> schema finalization, and why the toolsets contract must stay strict.
>
> Related: [`hermes-plugin-registration-order.md`](./hermes-plugin-registration-order.md),
> [`hermes-intentframe-integration-guide.md`](./hermes-intentframe-integration-guide.md),
> [`hermes-outbound-messaging-and-cronjob-governance.md`](./hermes-outbound-messaging-and-cronjob-governance.md),
> [`integrations/hermes/plugin/intentframe-gate/README.md`](../integrations/hermes/plugin/intentframe-gate/README.md).

---

## TL;DR

| Topic | Decision |
|-------|----------|
| **`execute_code` governance** | Reuse `RUN_COMMAND` + `map_execute_code()` — encode Python as `python -c …` so `command_shield` sees inline-edge + AST analysis |
| **Schema `reason` injection** | Two hooks at Hermes schema **composition** points — not at plugin `register()` via `import model_tools` |
| **`read_terminal` in toolsets** | Canary for accidental full `discover_builtin_tools()` — **do not relax** the contract |
| **What we rejected** | Wrapping `model_tools.get_tool_definitions` at plugin load; `importlib` meta_path hooks; relaxing toolsets assertions |

---

## Part 1 — Governed `execute_code`

### What Hermes `execute_code` is

- **Python-only** sandbox tool (`tools/code_execution_tool.py`).
- Runs user Python in a child process with RPC access to a subset of Hermes tools.
- Different from `terminal` (shell) but both are high-risk execution surfaces.

### What we added

**Governance yaml** (`integrations/hermes/governance/tools.yaml`):

```yaml
execute_code:
  enabled: true
  action: RUN_COMMAND
  risk: code_execution
  mapper: execute_code
  blocked_response: generic_json
  builtin_module: tools.code_execution_tool
```

**Mapper** (`hermes_adapter/mapper.py` — `map_execute_code`):

- Maps `{code, reason}` → `RUN_COMMAND` intent.
- Encodes Python as `python -c {shlex.quote(code)}` (not a fake `execute_code:python\n…` string) so Guardian **`command_shield`** applies inline-edge + AST rules to the script body.
- Truncates body at `_EXECUTE_CODE_MAX_BODY` (9500 chars) — below Hermes `command_shield` `max_command_length` (10k).

**Why reuse `RUN_COMMAND`?**

- No new action bundle, executor row, or policy shape.
- Same IntentFrame path as `terminal` for command analysis.
- BLOCK probes can use deterministic substrings (e.g. `sudo` in generated shell) mirroring terminal E2E.

**Probes / tests**

- `tests/hermes_tool_probes.py` — `execute_code_allow_args`, `execute_code_block_args`
- Gateway E2E helpers in `tests/hermes_gateway/api_client.py`
- Removed `execute_code` from `UNGATED_DISTRACTOR_TOOLS` in `toolsets_contract.py` (it is governed, not a distractor)

### ALLOW vs BLOCK probe behavior

- **BLOCK** via `sudo` substring in generated `python -c` command — deterministic (`CATASTROPHIC`).
- **ALLOW** for benign scripts — AE-dependent (`NEEDS_REVIEW` for many `python -c` scripts); not as deterministic as terminal ALLOW.

---

## Part 2 — Schema finalization (`reason` in model-facing JSON)

The model must see `reason` in `parameters.required` for every **governed** tool. Execution still strips `reason` before the native Hermes handler runs (`gate.py`).

### Two layers (do not conflate)

| Layer | Responsibility | Files |
|-------|----------------|-------|
| **Handler gate** | Validate via adapter; strip `reason`; delegate | `gate.py`, snapshot loop, `registry.register` hook |
| **Schema finalization** | Inject `reason` into JSON schemas the LLM receives | `registry.get_definitions` hook + `build_execute_code_schema` hook |

Registry-time `schema=entry.schema` in the snapshot loop intentionally does **not** inject `reason`. Schema finalization happens on the paths Hermes uses when building the OpenAI payload.

### Why not wrap `model_tools.get_tool_definitions` at plugin load?

We briefly added `install_tool_definitions_hook()` that did `import model_tools` during `register()`.

**Problem:** Hermes runs full builtin discovery at `model_tools` import time:

```python
# external-reference-only-libs/hermes-agent/model_tools.py (module level)
discover_builtin_tools()
```

That imports **every** self-registering tool module, including `read_terminal_tool.py`, which registers desktop-only `read_terminal` into the `terminal` toolset **before** the gateway’s intended lazy load order.

**Symptom:**

```
Toolset 'terminal' tools mismatch.
  expected: ['process', 'terminal']
  actual:   ['process', 'read_terminal', 'terminal']
```

**Fix (current):** Do **not** import `model_tools` during plugin registration. Finalize schemas at narrower composition points instead.

### Current schema hooks (June 2026)

**1. `registry.get_definitions`** (`registry_hook.py`)

- Wraps every call to `registry.get_definitions`.
- Runs `finalize_governed_tool_schemas()` on the returned OpenAI-format tool list.
- Covers: `terminal`, `write_file`, `patch`, `cronjob`, and future governed tools with static registry schemas.

**2. `build_execute_code_schema`** (`tool_definitions_hook.py`)

- Hermes **rebuilds** `execute_code` schema **after** `get_definitions` inside `_compute_tool_definitions()` — listing only sandbox tools that actually passed `check_fn`.
- That rebuild **overwrites** any `reason` added by the `get_definitions` hook.
- Therefore we patch `tools.code_execution_tool.build_execute_code_schema` to call `inject_reason()` on its return value.
- Installed **after** `preload_governed_builtins()` (when `code_execution_tool` is already loaded for governed `execute_code`).

**Plugin `register()` order:**

```
install_registry_hook()          # register + get_definitions patches; NO model_tools
preload_governed_builtins()    # selective imports from governance yaml only
install_execute_code_schema_hook()
snapshot loop                  # wrap handlers; schema=entry.schema (no inject here)
```

### Does patching `build_execute_code_schema` affect Hermes execution?

**No.** That function returns a **schema dict** for the LLM. It does not run code.

- `inject_reason()` deep-copies and adds `reason` to `parameters` + description suffix.
- `execute_code()` handler only reads `args.get("code")`.
- `wrap_handler` strips `reason` before delegation.

Patching affects **what the model is told to send**, not how Hermes executes after the gate allows the call.

### Alternatives we considered and rejected

| Approach | Why rejected |
|----------|----------------|
| **`import model_tools` at plugin load** | Triggers `discover_builtin_tools()` → `read_terminal` leak |
| **`importlib` meta_path lazy hook on `model_tools`** | Works but over-engineered for this codebase |
| **`wrapt` post-import hook (`model_tools?`)** | Industry-standard for APM; adds dependency we do not have |
| **Relax toolsets contract to allow extras** | Hides registration-order bugs; `read_terminal` is not intended api_server surface |
| **Inject `reason` only in `registry.register` hook** | Insufficient — `execute_code` schema is rebuilt later without `reason` |
| **Only wrap `get_definitions`** | Insufficient alone — `execute_code` dynamic rebuild wipes `reason` |

---

## Part 3 — Three test surfaces (do not conflate)

| Surface | What it proves | Harness |
|---------|----------------|---------|
| **`GET /v1/toolsets`** | Pinned api_server **tool names** per toolset (guardrail) | `toolsets_contract.py` |
| **Registry schemas** | Governed tools have `reason` + gated handlers | `probe_hermes_tool_schemas.py` |
| **OpenAI `tools=` payload** | What Hermes actually sends upstream | `provider_request_contract.py` / toolsets live test |

A passing `/v1/toolsets` does **not** prove `terminal` is in the OpenAI request. Always verify the provider dump or Platform logs for the payload that matters.

### Why `read_terminal` fails the contract but `vision_analyze` does not

The contract is **not** “reject all ungoverned tools.” It is an **exact allowlist** per toolset for the intended `hermes-api-server` composite.

| Tool | Ungoverned? | In contract? | Why |
|------|-------------|--------------|-----|
| `read_file`, `vision_analyze`, `skill_manage` | Yes | **Expected** | Part of api_server surface; some are E2E distractors |
| `read_terminal` | Yes | **Must not appear** | Desktop-only; appears only when full discovery runs too early |

`read_terminal` is a **canary**: if it shows up at `GET /v1/toolsets` before first lazy `model_tools` load, the plugin imported too much at registration time.

---

## Part 4 — Verification

### Unit tests

```bash
.venv/bin/python tests/hermes_plugin/test_gate.py
.venv/bin/python tests/hermes_plugin/test_registry_hook.py
.venv/bin/python tests/hermes_plugin/test_builtin_preload.py
```

Key regression tests added in this work:

- `test_install_registry_hook_does_not_import_model_tools`
- `test_get_definitions_injects_reason_for_governed_tools`
- `test_execute_code_schema_hook_injects_reason`

### Live toolsets + provider payload (passed June 2026)

```bash
RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
```

Expected highlights:

- `terminal: ['process', 'terminal']` — no `read_terminal`
- All governed tools: `reason_in_schema: true` in schema probe
- Provider dump: `cronjob`, `execute_code`, `patch`, `terminal`, `write_file` with `reason_required=True`

---

## Adding a future governed tool — checklist

1. Add entry to `integrations/hermes/governance/tools.yaml` with `builtin_module: tools.<module>`.
2. Implement mapper in `hermes_adapter/mapper.py` (or use `generic`).
3. Add probe args in `tests/hermes_tool_probes.py` if gateway E2E will cover it.
4. Extend `test_builtin_preload.py` if new module path.
5. **Schema hook:** if Hermes rebuilds the tool schema **after** `get_definitions` (like `execute_code`), add a dedicated builder wrap — do not assume `get_definitions` alone is enough.
6. **Never** call `discover_builtin_tools()` or `import model_tools` in the plugin.
7. Run toolsets live test — confirm no unexpected tool names in pinned toolsets.

---

## File index

| File | Role |
|------|------|
| [`integrations/hermes/governance/tools.yaml`](../integrations/hermes/governance/tools.yaml) | Governed catalog + `builtin_module` preload map |
| [`integrations/hermes/adapter/src/hermes_adapter/mapper.py`](../integrations/hermes/adapter/src/hermes_adapter/mapper.py) | `map_execute_code` |
| [`integrations/hermes/plugin/intentframe-gate/__init__.py`](../integrations/hermes/plugin/intentframe-gate/__init__.py) | Plugin load order |
| [`integrations/hermes/plugin/intentframe-gate/registry_hook.py`](../integrations/hermes/plugin/intentframe-gate/registry_hook.py) | `register` + `get_definitions` hooks |
| [`integrations/hermes/plugin/intentframe-gate/tool_definitions_hook.py`](../integrations/hermes/plugin/intentframe-gate/tool_definitions_hook.py) | `finalize_governed_tool_schemas` + `execute_code` builder hook |
| [`integrations/hermes/plugin/intentframe-gate/schema.py`](../integrations/hermes/plugin/intentframe-gate/schema.py) | `inject_reason()` |
| [`tests/hermes_gateway/toolsets_contract.py`](../tests/hermes_gateway/toolsets_contract.py) | Strict api_server name surface |
| [`tests/hermes_gateway/probe_hermes_tool_schemas.py`](../tests/hermes_gateway/probe_hermes_tool_schemas.py) | Schema + gate marker probe |
| [`tests/hermes_gateway/provider_request_contract.py`](../tests/hermes_gateway/provider_request_contract.py) | OpenAI payload assertions |
