from __future__ import annotations

from typing import Any


class BridgeError(Exception):
    """Base error for bridge client failures."""


class BridgeHttpError(BridgeError):
    """Bridge returned a non-success HTTP status."""

    def __init__(self, status_code: int, body: Any, *, expected: int | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.expected = expected
        if expected is not None:
            super().__init__(
                f"expected HTTP {expected}, got {status_code}: {body!r}"
            )
        else:
            super().__init__(f"HTTP {status_code}: {body!r}")
