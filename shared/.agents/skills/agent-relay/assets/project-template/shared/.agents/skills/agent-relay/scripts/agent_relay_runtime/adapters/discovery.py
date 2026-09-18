"""Shared CLI detection and conservative failure classification."""

from __future__ import annotations

import re

try:
    from .base import ExitClassification, FailureKind
except ImportError:
    import importlib.util
    from pathlib import Path
    import sys

    _path = Path(__file__).with_name("base.py")
    _spec = importlib.util.spec_from_file_location("agent_relay_discovery_base", _path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load {_path}")
    _base = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _base
    _spec.loader.exec_module(_base)
    ExitClassification = _base.ExitClassification
    FailureKind = _base.FailureKind


def classify_failure(exit_code: int, stderr: str) -> ExitClassification:
    if exit_code == 0:
        return ExitClassification(True)
    text = stderr.lower()
    if "quota" in text or "usage limit" in text or "credit" in text:
        return ExitClassification(False, FailureKind.QUOTA_EXHAUSTED, stderr)
    if "rate limit" in text or "429" in text or "temporarily unavailable" in text:
        return ExitClassification(False, FailureKind.RATE_LIMIT, stderr)
    if "login" in text or "credential" in text or "authentication" in text:
        return ExitClassification(False, FailureKind.AUTH, stderr)
    if "model" in text and ("not found" in text or "unknown" in text or "invalid" in text):
        return ExitClassification(False, FailureKind.MODEL_UNAVAILABLE, stderr)
    if "permission" in text or "denied" in text:
        return ExitClassification(False, FailureKind.PERMISSION, stderr)
    if "unsupported" in text or "non-interactive" in text:
        return ExitClassification(False, FailureKind.UNSUPPORTED, stderr)
    return ExitClassification(False, FailureKind.TRANSIENT, stderr)
