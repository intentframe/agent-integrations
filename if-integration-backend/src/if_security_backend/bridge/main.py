"""Uvicorn entrypoint for the validate bridge."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn


def run_server(*, socket_path: Path, config_path: Path) -> None:
    from if_security_backend.bridge.server import create_app

    app = create_app(config_path=config_path)
    uvicorn.run(
        app,
        uds=str(socket_path),
        log_level="info",
        access_log=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="intentframe-bridge")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    args.socket.parent.mkdir(parents=True, exist_ok=True)
    args.socket.unlink(missing_ok=True)
    run_server(socket_path=args.socket, config_path=args.config)


if __name__ == "__main__":
    main()
