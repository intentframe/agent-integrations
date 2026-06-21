"""Subprocess wrapper for intentframe-integrations (production CLI only)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from isolation import IsolatedEnv


@dataclass(frozen=True)
class CliResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    streamed: bool = False


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cli_argv(args: list[str]) -> list[str]:
    """Cross-platform CLI invocation via uv (no bash launcher dependency)."""
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required on PATH to run intentframe-integrations E2E tests")
    return [
        uv,
        "run",
        "--package",
        "intentframe-integrations-cli",
        "intentframe-integrations",
        *args,
    ]


def _should_stream(*, stream: bool | None, timeout: float | None) -> bool:
    if stream is not None:
        return stream
    return timeout is not None and timeout >= 60.0


def run_cli(
    args: list[str],
    *,
    env: IsolatedEnv | None = None,
    expect_code: int = 0,
    timeout: float | None = None,
    stream: bool | None = None,
) -> CliResult:
    argv = cli_argv(args)
    label = f"intentframe-integrations {' '.join(args)}"
    step(f"$ {label}")
    started = time.monotonic()
    use_stream = _should_stream(stream=stream, timeout=timeout)

    if use_stream:
        proc = subprocess.Popen(
            argv,
            cwd=repo_root(),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        captured: list[str] = []
        assert proc.stdout is not None
        deadline = started + timeout if timeout is not None else None
        try:
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    proc.kill()
                    proc.wait()
                    raise subprocess.TimeoutExpired(argv, timeout)
                line = proc.stdout.readline()
                if line:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                    captured.append(line)
                elif proc.poll() is not None:
                    break
            remainder = proc.stdout.read()
            if remainder:
                sys.stderr.write(remainder)
                sys.stderr.flush()
                captured.append(remainder)
            returncode = proc.wait()
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            result = CliResult(
                argv=argv,
                returncode=-1,
                stdout="".join(captured),
                stderr="",
                streamed=True,
            )
            raise CliError(result, env=env, expected=expect_code, elapsed=elapsed) from None
        elapsed = time.monotonic() - started
        result = CliResult(
            argv=argv,
            returncode=returncode,
            stdout="".join(captured),
            stderr="",
            streamed=True,
        )
    else:
        proc = subprocess.run(
            argv,
            cwd=repo_root(),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        elapsed = time.monotonic() - started
        result = CliResult(
            argv=argv,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    if proc.returncode == expect_code:
        step(f"✓ {label} ({elapsed:.1f}s)")
        return result

    raise CliError(result, env=env, expected=expect_code, elapsed=elapsed)


def stop_everything(*, env: IsolatedEnv | None = None) -> None:
    step("Stopping gateway + IntentFrame runtime")
    try:
        run_cli(["gateway", "stop", "hermes"], env=env, expect_code=0, stream=False)
    except CliError:
        pass
    try:
        run_cli(["stop"], env=env, expect_code=0, stream=False)
    except CliError:
        pass


def _read_tail(path: Path, *, chars: int = 3000) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")[-chars:]
    except OSError:
        return None


_SECRET_ENV_KEYS = frozenset(
    {
        "OPENAI_API_KEY",
        "API_SERVER_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "HF_TOKEN",
        "HUGGINGFACE_HUB_TOKEN",
    }
)


def _redact_env_tail(path: Path, *, chars: int = 3000) -> str | None:
    tail = _read_tail(path, chars=chars)
    if tail is None:
        return None
    redacted: list[str] = []
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            redacted.append(line)
            continue
        key, _, _value = line.partition("=")
        if key.strip() in _SECRET_ENV_KEYS:
            redacted.append(f"{key.strip()}=<redacted>")
        else:
            redacted.append(line)
    return "\n".join(redacted)


def format_diagnostics(env: IsolatedEnv) -> str:
    lines: list[str] = []
    if env.tracked_pids:
        lines.append(f"tracked PIDs: {env.tracked_pids}")
    for label, path, reader in (
        ("gateway.log", env.gateway_log, _read_tail),
        ("adapter.log", env.adapter_log, _read_tail),
        ("bridge.log", env.bridge_log, _read_tail),
        ("supervisor.log", env.supervisor_log, _read_tail),
        ("executor.log", env.executor_log, _read_tail),
        ("Hermes config.yaml", env.hermes_config_path, _read_tail),
        ("Hermes .env", env.hermes_env_file, _redact_env_tail),
    ):
        tail = reader(path)
        if tail is not None:
            lines.append(f"{label} (tail):\n{tail}")
    return "\n".join(lines)


def format_failure(
    result: CliResult,
    *,
    env: IsolatedEnv | None = None,
    elapsed: float | None = None,
) -> str:
    lines = [
        f"Command failed: {' '.join(result.argv)}",
        f"Exit code: {result.returncode}",
    ]
    if elapsed is not None:
        lines.append(f"Elapsed: {elapsed:.1f}s")
    if result.streamed:
        lines.append("Output was streamed to the terminal (see above).")
    if result.stdout.strip():
        lines.append(f"stdout:\n{result.stdout}")
    if result.stderr.strip():
        lines.append(f"stderr:\n{result.stderr}")
    if env is not None:
        diagnostics = format_diagnostics(env)
        if diagnostics:
            lines.append(diagnostics)
    return "\n".join(lines)


class CliError(RuntimeError):
    def __init__(
        self,
        result: CliResult,
        *,
        env: IsolatedEnv | None = None,
        expected: int = 0,
        elapsed: float | None = None,
    ) -> None:
        self.result = result
        self.expected = expected
        super().__init__(format_failure(result, env=env, elapsed=elapsed))


def step(message: str) -> None:
    print(f"\n==> {message}", file=sys.stderr, flush=True)
