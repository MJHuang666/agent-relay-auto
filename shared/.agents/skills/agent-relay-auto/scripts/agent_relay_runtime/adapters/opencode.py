"""OpenCode CLI adapter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    from .base import AdapterCapabilities, LaunchRequest
except ImportError:
    import importlib.util

    _path = Path(__file__).with_name("base.py")
    _spec = importlib.util.spec_from_file_location("agent_relay_opencode_base", _path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load {_path}")
    _base = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _base
    _spec.loader.exec_module(_base)
    AdapterCapabilities = _base.AdapterCapabilities
    LaunchRequest = _base.LaunchRequest


class OpenCodeAdapter:
    def __init__(self, executable: str = "opencode", fixture: Path | None = None):
        self.executable = executable
        self.fixture = fixture

    def _command(self, *args: str) -> list[str]:
        return [self.executable, str(self.fixture), *args] if self.fixture else [self.executable, *args]

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(True, True, True, True, True)

    def list_models(self) -> tuple[str, ...]:
        result = subprocess.run(self._command("models", "--verbose"), capture_output=True, text=True, check=True)
        return tuple(line.strip() for line in result.stdout.splitlines() if "/" in line)

    def build_command(self, request: LaunchRequest) -> tuple[str, ...]:
        prompt = f"Read docs/agent/tasks/{request.task_id}/STATE.md and perform the {request.role} stage."
        return tuple(self._command("run", "--format", "json", "--model", request.model, prompt))

    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]:
        prompt = f"Resume task {request.task_id} as {request.role} from the latest checkpoint."
        return tuple(self._command("run", "--format", "json", "--session", session_id, prompt))

    def parse_event(self, line: str) -> dict[str, object]:
        return json.loads(line)
