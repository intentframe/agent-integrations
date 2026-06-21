"""Health checks for IntentFrame UDS services."""

from __future__ import annotations

import httpx

from if_security_backend.runtime.paths import run_dir


def core_healthy(timeout: float = 5.0) -> bool:
    sock = run_dir() / "intentframe.sock"
    if not sock.exists():
        return False
    try:
        transport = httpx.HTTPTransport(uds=str(sock))
        with httpx.Client(
            transport=transport,
            base_url="http://core",
            timeout=timeout,
        ) as client:
            resp = client.get("/health")
            return resp.status_code == 200
    except Exception:
        return False


def policy_registry_healthy(timeout: float = 5.0) -> bool:
    sock = run_dir() / "policy-registry.sock"
    if not sock.exists():
        return False
    try:
        transport = httpx.HTTPTransport(uds=str(sock))
        with httpx.Client(
            transport=transport,
            base_url="http://policy-registry",
            timeout=timeout,
        ) as client:
            resp = client.get("/health")
            return resp.status_code == 200
    except Exception:
        return False


def wait_for_core(
    timeout_seconds: float = 90.0,
    poll_interval: float = 1.0,
    *,
    supervisor_pid: int | None = None,
) -> bool:
    import os
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if supervisor_pid is not None:
            try:
                os.kill(supervisor_pid, 0)
            except OSError:
                return False
        if core_healthy():
            return True
        time.sleep(poll_interval)
    return False
