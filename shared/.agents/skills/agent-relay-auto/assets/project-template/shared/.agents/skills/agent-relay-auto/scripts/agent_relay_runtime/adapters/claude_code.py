"""Claude Code print-mode adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from .base import AdapterCapabilities, LaunchContext, LaunchRequest, build_role_prompt
except ImportError:
    import importlib.util

    _path = Path(__file__).with_name("base.py")
    _spec = importlib.util.spec_from_file_location("agent_relay_claude_base", _path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load {_path}")
    _base = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _base
    _spec.loader.exec_module(_base)
    AdapterCapabilities = _base.AdapterCapabilities
    LaunchRequest = _base.LaunchRequest
    LaunchContext = _base.LaunchContext
    build_role_prompt = _base.build_role_prompt


class ClaudeCodeAdapter:
    def __init__(self, executable: str = "claude", fixture: Path | None = None):
        self.executable = executable
        self.fixture = fixture

    def _command(self, *args: str) -> list[str]:
        return [self.executable, str(self.fixture), *args] if self.fixture else [self.executable, *args]

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(True, False, True, True, True)

    def build_command(self, request: LaunchRequest, context: LaunchContext) -> tuple[str, ...]:
        prompt = build_role_prompt(request, context)
        return tuple(self._command("-p", "--output-format", "stream-json", "--model", request.model, "--effort", request.reasoning or "medium", prompt))

    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]:
        prompt = f"Resume task {request.task_id} as {request.role} from the latest checkpoint."
        return tuple(self._command("-p", "--output-format", "stream-json", "--resume", session_id, prompt))

    def parse_event(self, line: str) -> dict[str, object]:
        return json.loads(line)
