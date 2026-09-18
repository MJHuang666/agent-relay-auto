"""Codex CLI/app-server adapter."""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
import time
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

    @staticmethod
    def _send(process: subprocess.Popen[str], payload: dict[str, object]) -> None:
        if process.stdin is None:
            raise RuntimeError("Codex app-server stdin is unavailable")
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()

    @staticmethod
    def _read_response(process: subprocess.Popen[str], request_id: str, timeout: float = 10) -> dict[str, object]:
        if process.stdout is None:
            raise RuntimeError("Codex app-server stdout is unavailable")
        deadline = time.monotonic() + timeout
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Codex app-server timed out waiting for response {request_id}")
                if not selector.select(remaining):
                    raise TimeoutError(f"Codex app-server timed out waiting for response {request_id}")
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError("Codex app-server exited before returning a response")
                payload = json.loads(line)
                if str(payload.get("id")) == request_id:
                    if "error" in payload:
                        raise RuntimeError(f"Codex app-server request failed: {payload['error']}")
                    return payload
        finally:
            selector.close()

    def list_models(self) -> tuple[ModelOption, ...]:
        process = subprocess.Popen(
            self._command("app-server"), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        initialize_id = str(uuid.uuid4())
        model_list_id = str(uuid.uuid4())
        try:
            self._send(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": initialize_id,
                    "method": "initialize",
                    "params": {
                        "clientInfo": {"name": "agent-relay-auto", "version": "1.6.2"},
                        "capabilities": {},
                    },
                },
            )
            self._read_response(process, initialize_id)
            self._send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
            self._send(
                process,
                {"jsonrpc": "2.0", "id": model_list_id, "method": "model/list", "params": {}},
            )
            payload = self._read_response(process, model_list_id)
            result = payload.get("result", {})
            models = result.get("data", []) if isinstance(result, dict) else []
            return tuple(
                ModelOption(item["id"], item.get("displayName", item.get("display_name", item["id"])))
                for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
        finally:
            if process.stdin is not None:
                process.stdin.close()
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def build_command(self, request: LaunchRequest) -> tuple[str, ...]:
        prompt = f"Read docs/agent/tasks/{request.task_id}/STATE.md and perform the {request.role} stage."
        arguments = ["exec", "--json", "--model", request.model]
        if request.reasoning:
            arguments.extend(["--config", f'model_reasoning_effort="{request.reasoning}"'])
        arguments.extend(["--cd", str(request.repo), prompt])
        return tuple(self._command(*arguments))

    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]:
        prompt = f"Resume task {request.task_id} as {request.role} from the latest checkpoint."
        return tuple(self._command("exec", "resume", session_id, "--json", "--model", request.model, prompt))
