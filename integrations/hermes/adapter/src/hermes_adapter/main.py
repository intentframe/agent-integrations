"""Uvicorn entrypoint for the Hermes adapter sidecar."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn


def run_server(*, socket_path: Path) -> None:
    from hermes_adapter.server import create_app

    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)

    app = create_app()
    uvicorn.run(
        app,
        uds=str(socket_path),
        log_level="info",
        access_log=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="hermes-adapter")
    parser.add_argument(
        "--socket",
        type=Path,
        required=True,
        help="Unix domain socket path for the adapter HTTP server",
    )
    args = parser.parse_args()
    run_server(socket_path=args.socket.expanduser().resolve())


if __name__ == "__main__":
    main()
