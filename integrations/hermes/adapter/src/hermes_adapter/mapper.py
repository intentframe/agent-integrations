"""Map Hermes tool calls to IntentFrame validate requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from hermes_governance import load_governed_tools

IntentDict = dict[str, Any]
MapperFn = Callable[[dict[str, Any]], list[IntentDict]]

_V4A_OP_RE = re.compile(
    r"^\*\*\*\s+(Update|Add|Delete)\s+File:\s*(.+)$",
    re.MULTILINE,
)

PatchOpKind = Literal["update", "add", "delete"]


@dataclass(frozen=True)
class PatchOperation:
    kind: PatchOpKind
    path: str


class ValidationError(ValueError):
    """Local preflight failure before calling the IntentFrame bridge."""


def validate_reason(reason: object) -> str:
    if reason is None:
        raise ValidationError("Missing required field: reason")
    if not isinstance(reason, str):
        raise ValidationError("reason must be a string")
    stripped = reason.strip()
    if not stripped:
        raise ValidationError("Missing required field: reason (empty string)")
    if len(stripped) < 3:
        raise ValidationError("reason must be at least 3 characters")
    return stripped


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Missing or invalid {key}")
    return value.strip()


def _host_file_intent(
    *,
    action: str,
    path: str,
    reason: str,
    content: str | None = None,
    irreversible: bool | None = None,
) -> IntentDict:
    intent: IntentDict = {
        "action": action,
        "path": path,
        "reason": reason,
        "target": path,
    }
    if content is not None:
        intent["content"] = content
    if irreversible is not None:
        intent["irreversible"] = irreversible
    return intent


def map_terminal(args: dict[str, Any]) -> list[IntentDict]:
    command = _require_str(args, "command")
    reason = validate_reason(args.get("reason"))
    return [
        {
            "action": "RUN_COMMAND",
            "command": command,
            "reason": reason,
            "target": command[:200],
        }
    ]


def map_process(args: dict[str, Any]) -> list[IntentDict]:
    action = _require_str(args, "action")
    reason = validate_reason(args.get("reason"))
    session_id = args.get("session_id")
    session_part = f" session_id={session_id}" if session_id is not None else ""
    data = args.get("data")
    data_part = f" data={data!r}" if data is not None else ""
    command = f"process:{action}{session_part}{data_part}"
    return [
        {
            "action": "RUN_COMMAND",
            "command": command,
            "reason": reason,
            "target": command[:200],
        }
    ]


def map_write_file(args: dict[str, Any]) -> list[IntentDict]:
    path = _require_str(args, "path")
    content = args.get("content")
    if not isinstance(content, str):
        raise ValidationError("Missing or invalid content")
    reason = validate_reason(args.get("reason"))
    return [
        _host_file_intent(
            action="WRITE_HOST_FILE",
            path=path,
            reason=reason,
            content=content,
        )
    ]


def map_delete_file(args: dict[str, Any]) -> list[IntentDict]:
    path = _require_str(args, "path")
    reason = validate_reason(args.get("reason"))
    return [
        _host_file_intent(
            action="DELETE_HOST_FILE",
            path=path,
            reason=reason,
            irreversible=True,
        )
    ]


def _parse_v4a_operations(patch_content: str) -> list[PatchOperation]:
    operations: list[PatchOperation] = []
    for match in _V4A_OP_RE.finditer(patch_content):
        kind_raw = match.group(1).lower()
        path = match.group(2).strip()
        if not path:
            raise ValidationError("V4A patch contains empty file path")
        if kind_raw not in {"update", "add", "delete"}:
            raise ValidationError(f"Unsupported V4A operation: {kind_raw!r}")
        operations.append(PatchOperation(kind=kind_raw, path=path))  # type: ignore[arg-type]
    if not operations:
        raise ValidationError("Could not extract file operations from V4A patch content")
    return operations


def _extract_patch_operations(args: dict[str, Any]) -> list[PatchOperation]:
    mode = args.get("mode", "replace")
    if not isinstance(mode, str):
        raise ValidationError("Missing or invalid mode")

    if mode == "replace":
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValidationError("Missing or invalid path for patch replace mode")
        return [PatchOperation(kind="update", path=path.strip())]

    if mode == "patch":
        patch_content = args.get("patch")
        if not isinstance(patch_content, str) or not patch_content.strip():
            raise ValidationError("Missing or invalid patch content for patch mode")
        return _parse_v4a_operations(patch_content)

    raise ValidationError(f"Unsupported patch mode: {mode!r}")


def _patch_content_for_operation(args: dict[str, Any], operation: PatchOperation) -> str | None:
    mode = args.get("mode", "replace")
    if mode == "replace":
        old_string = args.get("old_string")
        new_string = args.get("new_string")
        if not isinstance(old_string, str):
            raise ValidationError("Missing or invalid old_string for patch replace mode")
        if not isinstance(new_string, str):
            raise ValidationError("Missing or invalid new_string for patch replace mode")
        return f"--- {operation.path}\n-old\n+{new_string}\n(replace {old_string!r})"

    patch_content = args.get("patch")
    if not isinstance(patch_content, str):
        raise ValidationError("Missing or invalid patch content")
    return patch_content if operation.kind != "delete" else None


def map_patch(args: dict[str, Any]) -> list[IntentDict]:
    reason = validate_reason(args.get("reason"))
    operations = _extract_patch_operations(args)
    intents: list[IntentDict] = []
    for operation in operations:
        if operation.kind == "delete":
            intents.append(
                _host_file_intent(
                    action="DELETE_HOST_FILE",
                    path=operation.path,
                    reason=reason,
                    irreversible=True,
                )
            )
            continue

        intents.append(
            _host_file_intent(
                action="WRITE_HOST_FILE",
                path=operation.path,
                reason=reason,
                content=_patch_content_for_operation(args, operation),
            )
        )
    return intents


MAPPERS: dict[str, MapperFn] = {
    "terminal": map_terminal,
    "process": map_process,
    "write_file": map_write_file,
    "delete_file": map_delete_file,
    "patch": map_patch,
}


def supported_tools() -> dict[str, str]:
    return {name: spec.action for name, spec in load_governed_tools().items()}


def map_tool(tool: str, args: dict[str, Any]) -> list[IntentDict]:
    governed = load_governed_tools()
    spec = governed.get(tool)
    if spec is None:
        raise ValidationError(f"Unsupported tool for validation: {tool!r}")

    mapper = MAPPERS.get(spec.mapper)
    if mapper is None:
        raise ValidationError(
            f"Governed tool {tool!r} references unknown mapper {spec.mapper!r}"
        )
    return mapper(args)
