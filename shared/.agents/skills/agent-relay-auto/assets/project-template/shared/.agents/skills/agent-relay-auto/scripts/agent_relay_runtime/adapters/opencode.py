"""OpenCode CLI adapter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    from .base import AdapterCapabilities, LaunchContext, LaunchRequest, build_role_prompt
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
    LaunchContext = _base.LaunchContext
    build_role_prompt = _base.build_role_prompt


class OpenCodeAdapter:
    def __init__(self, executable: str = "opencode", fixture: Path | None = None):
        self.executable = executable
        self.fixture = fixture

    def _command(self, *args: str) -> list[str]:
        return [self.executable, str(self.fixture), *args] if self.fixture else [self.executable, *args]

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(True, True, True, True, True)

    def list_models(self) -> tuple[str, ...]:
        result = subprocess.run(self._command("models"), capture_output=True, text=True, check=True)
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip().count("/") == 1)

    def build_command(self, request: LaunchRequest, context: LaunchContext) -> tuple[str, ...]:
        prompt = build_role_prompt(request, context)
        arguments = ["run", "--format", "json", "--model", request.model]
        if request.reasoning:
            arguments.extend(["--variant", request.reasoning])
        arguments.append(prompt)
        return tuple(self._command(*arguments))

    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]:
        prompt = f"Resume task {request.task_id} as {request.role} from the latest checkpoint."
        return tuple(self._command("run", "--format", "json", "--session", session_id, prompt))

    def parse_event(self, line: str) -> dict[str, object]:
        return json.loads(line)
