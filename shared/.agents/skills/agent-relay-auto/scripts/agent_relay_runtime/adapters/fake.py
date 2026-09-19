"""Deterministic adapter used by Runner unit and integration tests."""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

try:
    from .base import AdapterCapabilities, LaunchRequest
except ImportError:
    _path = Path(__file__).with_name("base.py")
    _spec = importlib.util.spec_from_file_location("agent_relay_runtime_fake_base", _path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load {_path}")
    _base = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _base
    _spec.loader.exec_module(_base)
    AdapterCapabilities = _base.AdapterCapabilities
    LaunchRequest = _base.LaunchRequest


class FakeAdapter:
    def __init__(self, python: str = sys.executable, fixture: Path | None = None, sleep: float = 0.0):
        self.python = python
        self.fixture = fixture or Path(__file__).resolve().parents[7] / "tests/fixtures/fake_agent_cli.py"
        self.sleep = sleep

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(True, False, False, False, True)

    def build_command(self, request: LaunchRequest, context=None) -> tuple[str, ...]:
        command = [
            self.python, str(self.fixture), "--sleep", str(self.sleep),
            "--repo", str(request.repo), "--task", request.task_id,
            "--role", request.role, "--participant-id", request.participant_id,
            "--run-id", request.run_id,
        ]
        return tuple(command)
