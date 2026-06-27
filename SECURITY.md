# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in IntentFrame Agent Integrations, please
report it responsibly. **Do not open a public GitHub issue.**

Email: **intentframe@gmail.com**

Please include:

- A description of the vulnerability
- Steps to reproduce it
- The potential impact
- Any suggested fix (optional)

We will acknowledge receipt within 48 hours and aim to provide an initial
assessment within 7 days.

## Scope

This repository integrates external agents with IntentFrame policy validation.
Vulnerabilities in the following are in scope for **this repo**:

- Policy bypass through the Hermes plugin, adapter, or CLI wiring
- Governance or policy YAML handling that allows ungoverned tool execution
- Bridge authentication or authorization flaws in integration clients
- Install/uninstall scripts that expose secrets, corrupt user config, or leave
  privileged state behind unexpectedly
- Incorrect tool mapping that sends unvalidated side effects to Hermes handlers

Core IntentFrame runtime vulnerabilities (Guardian, Analysis Engine, native bundles)
should be reported to the upstream [IntentFrame](https://github.com/intentframe/intentframe)
project as well, since this repo depends on those packages at runtime.

Hermes Agent vulnerabilities should be reported upstream to
[Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent).

## Out of scope

- Vulnerabilities in third-party dependencies (report upstream)
- Issues that require physical access to the host machine
- Social engineering attacks against users
- Bugs in ungoverned Hermes tools that are intentionally not routed through
  IntentFrame (documented in `docs/NATIVE_KIT_INTEGRATION.md`)

## Disclosure

We follow coordinated disclosure. We will work with you on a timeline and credit
you in the advisory unless you prefer to remain anonymous.
