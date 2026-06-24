"""Map Hermes tool calls to IntentFrame validate requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from hermes_governance import load_governed_tools

IntentDict = dict[str, Any]
MapperFn = Callable[[dict[str, Any]], list[IntentDict]]
GenericMapperFn = Callable[..., list[IntentDict]]

_V4A_OP_RE = re.compile(
    r"^\*\*\*\s+(Update|Add|Delete)\s+File:\s*(.+)$",
    re.MULTILINE,
)
_V4A_END_PATCH_RE = re.compile(r"\s*\*\*\* End Patch\s*\Z", re.MULTILINE)

PatchOpKind = Literal["update", "add", "delete"]


@dataclass(frozen=True)
class PatchOperation:
    kind: PatchOpKind
    path: str
    body: str = ""


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


def hermes_args_remainder(
    args: dict[str, Any],
    mapped_keys: frozenset[str],
) -> dict[str, Any]:
    """Hermes args not already promoted or absorbed by the dedicated mapper."""
    skip = mapped_keys | {"reason"}
    return {
        key: value
        for key, value in args.items()
        if key not in skip and value is not None
    }


def _attach_hermes_args(
    intent: IntentDict,
    args: dict[str, Any],
    mapped_keys: frozenset[str],
) -> IntentDict:
    remainder = hermes_args_remainder(args, mapped_keys)
    if remainder:
        intent["hermes_args"] = remainder
    return intent


def _host_file_intent(
    *,
    action: str,
    path: str,
    reason: str,
    content: str | None = None,
    irreversible: bool | None = None,
    patch_op_index: int | None = None,
    patch_op_count: int | None = None,
    patch_operations: list[dict[str, str]] | None = None,
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
    if patch_op_index is not None:
        intent["patch_op_index"] = patch_op_index
    if patch_op_count is not None:
        intent["patch_op_count"] = patch_op_count
    if patch_operations is not None:
        intent["patch_operations"] = patch_operations
    return intent


def map_terminal(args: dict[str, Any]) -> list[IntentDict]:
    command = _require_str(args, "command")
    reason = validate_reason(args.get("reason"))
    intent = {
        "action": "RUN_COMMAND",
        "command": command,
        "reason": reason,
        "target": command[:200],
    }
    return [_attach_hermes_args(intent, args, frozenset({"command"}))]


def map_process(args: dict[str, Any]) -> list[IntentDict]:
    action = _require_str(args, "action")
    reason = validate_reason(args.get("reason"))
    session_id = args.get("session_id")
    session_part = f" session_id={session_id}" if session_id is not None else ""
    data = args.get("data")
    data_part = f" data={data!r}" if data is not None else ""
    command = f"process:{action}{session_part}{data_part}"
    intent = {
        "action": "RUN_COMMAND",
        "command": command,
        "reason": reason,
        "target": command[:200],
    }
    absorbed = frozenset({"action", "session_id", "data"})
    return [_attach_hermes_args(intent, args, absorbed)]


def map_write_file(args: dict[str, Any]) -> list[IntentDict]:
    path = _require_str(args, "path")
    content = args.get("content")
    if not isinstance(content, str):
        raise ValidationError("Missing or invalid content")
    reason = validate_reason(args.get("reason"))
    intent = _host_file_intent(
        action="WRITE_HOST_FILE",
        path=path,
        reason=reason,
        content=content,
    )
    return [_attach_hermes_args(intent, args, frozenset({"path", "content"}))]


def _parse_v4a_operations(patch_content: str) -> list[PatchOperation]:
    matches = list(_V4A_OP_RE.finditer(patch_content))
    if not matches:
        raise ValidationError("Could not extract file operations from V4A patch content")

    operations: list[PatchOperation] = []
    for index, match in enumerate(matches):
        kind_raw = match.group(1).lower()
        path = match.group(2).strip()
        if not path:
            raise ValidationError("V4A patch contains empty file path")
        if kind_raw not in {"update", "add", "delete"}:
            raise ValidationError(f"Unsupported V4A operation: {kind_raw!r}")

        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(patch_content)
        body = patch_content[body_start:body_end]
        if index + 1 == len(matches):
            body = _V4A_END_PATCH_RE.sub("", body)
        operations.append(
            PatchOperation(kind=kind_raw, path=path, body=body.strip("\n"))  # type: ignore[arg-type]
        )
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


def _v4a_op_header(kind: PatchOpKind, path: str) -> str:
    label = {"update": "Update", "add": "Add", "delete": "Delete"}[kind]
    return f"*** {label} File: {path}"


def _scoped_v4a_fragment(operation: PatchOperation) -> str:
    header = _v4a_op_header(operation.kind, operation.path)
    if operation.kind == "delete":
        return f"*** Begin Patch\n{header}\n*** End Patch"
    inner = header
    if operation.body:
        inner = f"{inner}\n{operation.body}"
    return f"*** Begin Patch\n{inner}\n*** End Patch"


def _patch_op_reason(
    base_reason: str,
    *,
    index: int,
    total: int,
    operation: PatchOperation,
) -> str:
    return f"{base_reason} [patch op {index}/{total}: {operation.kind} {operation.path}]"


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

    if operation.kind == "delete":
        return None
    return _scoped_v4a_fragment(operation)


def _patch_operations_manifest(operations: list[PatchOperation]) -> list[dict[str, str]]:
    """Fresh manifest list per intent (no shared references across sub-intents)."""
    return [{"kind": op.kind, "path": op.path} for op in operations]


def _patch_mapped_arg_keys(mode: str) -> frozenset[str]:
    if mode == "patch":
        return frozenset({"mode", "patch"})
    return frozenset({"mode", "path", "old_string", "new_string"})


def map_patch(args: dict[str, Any]) -> list[IntentDict]:
    reason = validate_reason(args.get("reason"))
    mode = args.get("mode", "replace")
    if not isinstance(mode, str):
        raise ValidationError("Missing or invalid mode")
    mapped_arg_keys = _patch_mapped_arg_keys(mode)
    operations = _extract_patch_operations(args)
    total = len(operations)
    is_v4a = mode == "patch"

    intents: list[IntentDict] = []
    for index, operation in enumerate(operations, start=1):
        op_reason = (
            _patch_op_reason(reason, index=index, total=total, operation=operation)
            if is_v4a
            else reason
        )
        patch_context: dict[str, Any] = {}
        if is_v4a:
            patch_context = {
                "patch_op_index": index,
                "patch_op_count": total,
                "patch_operations": _patch_operations_manifest(operations),
            }

        if operation.kind == "delete":
            intent = _host_file_intent(
                action="DELETE_HOST_FILE",
                path=operation.path,
                reason=op_reason,
                irreversible=True,
                **patch_context,
            )
        else:
            intent = _host_file_intent(
                action="WRITE_HOST_FILE",
                path=operation.path,
                reason=op_reason,
                content=_patch_content_for_operation(args, operation),
                **patch_context,
            )
        intents.append(_attach_hermes_args(intent, args, mapped_arg_keys))
    return intents


def map_generic(tool: str, args: dict[str, Any], *, action: str) -> list[IntentDict]:
    reason = validate_reason(args.get("reason"))
    intent: IntentDict = {
        "action": action,
        "reason": reason,
        "target": tool,
        "hermes_tool": tool,
    }
    return [_attach_hermes_args(intent, args, frozenset())]


MAPPERS: dict[str, MapperFn | GenericMapperFn] = {
    "terminal": map_terminal,
    "process": map_process,
    "write_file": map_write_file,
    "patch": map_patch,
}


def supported_tools() -> dict[str, str]:
    return {name: spec.action for name, spec in load_governed_tools().items()}


def map_tool(tool: str, args: dict[str, Any]) -> list[IntentDict]:
    governed = load_governed_tools()
    spec = governed.get(tool)
    if spec is None:
        raise ValidationError(f"Unsupported tool for validation: {tool!r}")

    if spec.mapper == "generic":
        return map_generic(tool, args, action=spec.action)

    mapper = MAPPERS.get(spec.mapper)
    if mapper is None:
        raise ValidationError(
            f"Governed tool {tool!r} references unknown mapper {spec.mapper!r}"
        )
    return mapper(args)
