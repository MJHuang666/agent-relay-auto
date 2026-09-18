"""Conservative output redaction for Runner logs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


_BEARER = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT = re.compile(r"(?i)(api[_-]?key|token|secret|password)(\s*[=:]\s*)([^\s,;]+)")


def redact_text(text: str, secret_names: Iterable[str], environment: Mapping[str, str]) -> str:
    result = _BEARER.sub(r"\1[REDACTED]", text)
    values = {value for name, value in environment.items() if name in set(secret_names) and value}
    values.update(value for name, value in environment.items() if "KEY" in name or "TOKEN" in name or "SECRET" in name)
    for value in sorted(values, key=len, reverse=True):
        result = result.replace(value, "[REDACTED]")
    return _ASSIGNMENT.sub(r"\1\2[REDACTED]", result)
