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
        return (self.python, str(self.fixture), "--sleep", str(self.sleep))

    def on_result(self, supervisor, task_id: str, run_id: str, exit_code: int) -> None:
        result = supervisor.store.finish_run(task_id, run_id, exit_code)
        if exit_code != 0:
            return
        _, _, state = supervisor.store._read_task(task_id)
        event = {
            "PLANNING": "plan_completed",
            "IMPLEMENTING": "implementation_completed",
            "REVIEWING": "review_passed",
            "REPORTING": "report_completed",
        }.get(state.get("status"))
        if event is not None:
            supervisor.store.transition(task_id, result.output_revision, event, {})
