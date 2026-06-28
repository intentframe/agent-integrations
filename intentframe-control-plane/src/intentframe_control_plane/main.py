"""CLI entrypoints for control plane lifecycle."""

from __future__ import annotations

import argparse
import sys

from intentframe_control_plane.lifecycle import (
    ControlPlaneError,
    format_status_line,
    control_plane_status,
    serve_control_plane,
    start_control_plane,
    stop_control_plane,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intentframe-control-plane",
        description="IntentFrame operator control plane (http://127.0.0.1:9720)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start control plane in background")
    p_start.add_argument("--host", default=None)
    p_start.add_argument("--port", type=int, default=None)

    sub.add_parser("stop", help="Stop control plane")
    sub.add_parser("status", help="Show control plane status")

    p_serve = sub.add_parser("serve", help="Run control plane in foreground")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)

    try:
        match args.command:
            case "start":
                status = start_control_plane(host=args.host, port=args.port)
                print(status.url)
                return 0
            case "stop":
                stop_control_plane()
                return 0
            case "status":
                print(format_status_line(control_plane_status()))
                return 0
            case "serve":
                serve_control_plane(host=args.host, port=args.port)
                return 0
            case _:
                parser.error(f"Unknown command: {args.command}")
                return 2
    except ControlPlaneError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
