#!/usr/bin/env python3
"""Generate GitHub Release notes for tag pushes (used by release.yml)."""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO = "intentframe/agent-integrations"


def main() -> None:
    tag = os.environ["TAG"]
    release = json.loads(Path("RELEASE.json").read_text(encoding="utf-8"))
    version = release["version"]
    base = f"https://github.com/{REPO}"

    notes = f"""## Install (pinned release)

```bash
curl -fsSL {base}/raw/{tag}/scripts/install-hermes-plugin.sh | bash -s -- --ref {tag}
```

Headless (CI / Docker):

```bash
curl -fsSL {base}/raw/{tag}/scripts/install-hermes-plugin.sh | bash -s -- --headless --ref {tag}
```

Pack version: **{version}**. See [README]({base}/blob/{tag}/README.md) and [hermes-cli.md]({base}/blob/{tag}/docs/hermes-cli.md).
"""
    Path("release-notes.md").write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
