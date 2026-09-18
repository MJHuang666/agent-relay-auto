"""Small, loss-minimizing fenced-YAML helpers used by the Relay runtime.

The project deliberately keeps Markdown as the human-facing source of truth.
This parser handles the restricted schema used by the templates without
requiring an external YAML dependency.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


class StateFormatError(ValueError):
    """Raised when a Relay fenced-YAML block cannot be safely interpreted."""


_FENCE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
_KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_-]+):(?:\s*(?P<value>.*))?$")


def _fenced_block(text: str) -> tuple[str, int, int]:
    match = _FENCE.search(text)
    if not match:
        raise StateFormatError("missing YAML fenced block")
    return match.group(1), match.start(1), match.end(1)


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if value in {"", "null", "~"}:
        return None if value else {}
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise StateFormatError(f"invalid inline JSON value: {value}") from error
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        if value[0] == '"':
            try:
                return json.loads(value)
            except json.JSONDecodeError as error:
                raise StateFormatError(f"invalid quoted value: {value}") from error
        return value[1:-1].replace("''", "'")
    return value


def parse_fenced_yaml(text: str) -> dict[str, Any]:
    block, _, _ = _fenced_block(text)
    root: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    current_key: str | None = None
    for line_number, raw in enumerate(block.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _KEY.match(raw)
        if match is None:
            raise StateFormatError(f"unsupported YAML at line {line_number}: {raw}")
        indent = len(match.group("indent"))
        key = match.group("key")
        raw_value = match.group("value") or ""
        if indent == 0:
            parsed = _parse_value(raw_value)
            if raw_value.strip() == "":
                parsed = {}
                current = parsed
                current_key = key
            else:
                current = None
                current_key = None
            root[key] = parsed
        elif indent == 2 and current is not None and current_key is not None:
            current[key] = _parse_value(raw_value)
        else:
            raise StateFormatError(
                f"only one nested mapping level is supported at line {line_number}"
            )
    return root


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/+-]+", value):
        return value
    return json.dumps(str(value), ensure_ascii=False)


def set_yaml_value(text: str, path: tuple[str, ...], value: Any) -> str:
    if not path:
        raise ValueError("path must contain at least one key")
    block, start, end = _fenced_block(text)
    lines = block.splitlines()
    if len(path) == 1:
        prefix = f"{path[0]}:"
        for index, line in enumerate(lines):
            if line.startswith(prefix):
                lines[index] = f"{path[0]}: {_format_value(value)}"
                return text[:start] + "\n".join(lines) + text[end:]
        lines.append(f"{path[0]}: {_format_value(value)}")
        return text[:start] + "\n".join(lines) + text[end:]
    if len(path) != 2:
        raise ValueError("only root and one nested key are supported")
    section, key = path
    section_index = next(
        (index for index, line in enumerate(lines) if line == f"{section}:"), None
    )
    if section_index is None:
        lines.extend([f"{section}:", f"  {key}: {_format_value(value)}"])
    else:
        end_index = section_index + 1
        key_index = None
        while end_index < len(lines) and lines[end_index].startswith("  "):
            if lines[end_index].startswith(f"  {key}:"):
                key_index = end_index
            end_index += 1
        replacement = f"  {key}: {_format_value(value)}"
        if key_index is None:
            lines.insert(end_index, replacement)
        else:
            lines[key_index] = replacement
    return text[:start] + "\n".join(lines) + text[end:]


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
