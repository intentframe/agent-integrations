# Hermes integration — known limitations

Community install path: [README.md](../README.md#install). CLI reference: [hermes-cli.md](hermes-cli.md).

These are current gaps in the `curl | bash` installer and `uninstall` flow. Safe to promote the install command; call out these caveats when describing a **full wipe**.

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

## Version pinning

The installer supports git **branches**, **tags**, and **commit SHAs** via `--ref` (or `REF=`). `VERSION=` is a deprecated alias.

**Rule:** use the **same ref** in the install script URL and `--ref` so the script and integration pack match.

| Tier | Example |
|------|---------|
| Latest (default) | `curl …/raw/main/scripts/install-hermes-plugin.sh \| bash` |
| Pre-merge / branch | `curl …/raw/my-branch/… \| bash -s -- --ref my-branch --headless` |
| Stable release | `curl …/raw/v0.2.1/… \| bash -s -- --ref v0.2.1` |
| Locked / reproducible | `curl …/raw/<commit-sha>/… \| bash -s -- --ref <commit-sha>` |

Install provenance is written to `~/.intentframe/agent-integrations/.install-manifest.json` and shown by `intentframe-integrations doctor hermes`.

Details: [hermes-cli.md#install](hermes-cli.md#install).

---

## Roadmap (planned improvements)

| Item | Status |
|------|--------|
| Uninstall removes `/usr/local/lib/hermes-agent` when present (root FHS layout) | planned |
| Document or automate cleanup of Homebrew deps installed during Hermes setup (`ffmpeg`, etc.) | under consideration |

---

## Related docs

- [hermes-cli.md#uninstall](hermes-cli.md#uninstall) — removal tables and verify commands
- [tests/docker/README.md](../tests/docker/README.md) — Docker runs as root; uses `--headless` and `REF=`
