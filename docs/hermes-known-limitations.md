# Hermes integration — known limitations

Community install path: [README.md](../README.md#install). CLI reference: [hermes-cli.md](hermes-cli.md).

These are current gaps in the `curl | bash` installer and `uninstall` flow. Safe to promote the install command; call out these caveats when describing a **full wipe** or **version pinning**.

---

## `--remove-hermes` does not remove root FHS Hermes code

**Affects:** Linux installs where the [official Hermes installer](https://hermes-agent.nousresearch.com/docs/getting-started/installation) ran as **root** (Docker smoke test, `sudo curl … | bash`).

Hermes uses two layouts:

| Layout | Hermes code | Data (`HERMES_HOME`) | `hermes` CLI |
|--------|-------------|----------------------|--------------|
| Per-user (default) | `~/.hermes/hermes-agent/` | `~/.hermes/` | `~/.local/bin/hermes` |
| Root FHS (Linux) | `/usr/local/lib/hermes-agent/` | `~/.hermes/` (or `$HERMES_HOME`) | `/usr/local/bin/hermes` |

`intentframe-integrations uninstall hermes --remove-hermes` today removes:

- Entire `~/.hermes/` (config, sessions, logs, plugins, legacy checkout under home)
- `hermes` symlinks in `~/.local/bin` and `/usr/local/bin`

It does **not** remove `/usr/local/lib/hermes-agent/` (or uv Python under `/usr/local/share/uv/` when Hermes installed that way).

**After `--remove-hermes` on a root/FHS install**, manually remove Hermes code if you want a true greenfield:

```bash
sudo rm -rf /usr/local/lib/hermes-agent
# optional, if Hermes installed uv Python system-wide:
sudo rm -rf /usr/local/share/uv
```

Per-user installs (`curl … | bash` without sudo) are fully covered by `--remove-hermes` for user data and CLI symlinks.

---

## `VERSION=` pins branches only, not git tags

The install script downloads the integration pack from:

```text
https://github.com/intentframe/agent-integrations/archive/refs/heads/${VERSION}.tar.gz
```

So:

| `VERSION` value | Works? |
|-----------------|--------|
| `main` (default) | yes |
| `my-feature-branch` | yes |
| `v1.0.0` or other **tag** | **no** (404 — tags use `refs/tags/`, not implemented yet) |

**Promote with:** `…/raw/main/scripts/install-hermes-plugin.sh` or `VERSION=your-branch` for pre-merge testing.

---

## Roadmap (planned improvements)

| Item | Status |
|------|--------|
| Uninstall removes `/usr/local/lib/hermes-agent` when present (root FHS layout) | planned |
| `VERSION=` supports git tags (`refs/tags/…`) as well as branches | planned |
| Document or automate cleanup of Homebrew deps installed during Hermes setup (`ffmpeg`, etc.) | under consideration |

---

## Related docs

- [hermes-cli.md#uninstall](hermes-cli.md#uninstall) — removal tables and verify commands
- [tests/docker/README.md](../tests/docker/README.md) — Docker runs as root; uses `--headless` and `VERSION=branch`
