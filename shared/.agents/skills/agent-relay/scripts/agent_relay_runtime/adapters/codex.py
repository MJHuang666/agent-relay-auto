"""Codex CLI/app-server adapter."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

try:
    from .base import AdapterCapabilities, LaunchRequest, ModelOption
except ImportError:
    import importlib.util

    _path = Path(__file__).with_name("base.py")
    _spec = importlib.util.spec_from_file_location("agent_relay_codex_base", _path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load {_path}")
    _base = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _base
    _spec.loader.exec_module(_base)
    AdapterCapabilities = _base.AdapterCapabilities
    LaunchRequest = _base.LaunchRequest
    ModelOption = _base.ModelOption


class CodexAdapter:
    def __init__(self, executable: str = "codex", app_server_fixture: Path | None = None):
        self.executable = executable
        self.app_server_fixture = app_server_fixture

    def _command(self, *args: str) -> list[str]:
        if self.app_server_fixture is not None:
            return [self.executable, str(self.app_server_fixture), *args]
        return [self.executable, *args]

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(True, True, True, True, True)

    def list_models(self) -> tuple[ModelOption, ...]:
        request_id = str(uuid.uuid4())
        request = {"jsonrpc": "2.0", "id": request_id, "method": "model/list", "params": {}}
        process = subprocess.Popen(
            self._command("app-server"), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, _ = process.communicate(json.dumps(request) + "\n", timeout=10)
        for line in stdout.splitlines():
            payload = json.loads(line)
            models = payload.get("result", {}).get("data")
            if models is not None:
                return tuple(ModelOption(item["id"], item.get("display_name", item["id"])) for item in models)
        return ()

    def build_command(self, request: LaunchRequest) -> tuple[str, ...]:
        prompt = f"Read docs/agent/tasks/{request.task_id}/STATE.md and perform the {request.role} stage."
        return tuple(self._command("exec", "--json", "--model", request.model, "--cd", str(request.repo), prompt))

    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]:
        prompt = f"Resume task {request.task_id} as {request.role} from the latest checkpoint."
        return tuple(self._command("exec", "resume", session_id, "--json", "--model", request.model, prompt))

