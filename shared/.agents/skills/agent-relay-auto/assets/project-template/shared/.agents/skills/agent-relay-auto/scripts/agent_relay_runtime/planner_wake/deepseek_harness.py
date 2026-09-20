"""Wake an exact persisted DeepSeek Harness Planner session over ACP."""

from __future__ import annotations

import importlib.util
import json
import selectors
import subprocess
import sys
import threading
import time
from pathlib import Path


def _base():
    path = Path(__file__).with_name("base.py")
    spec = importlib.util.spec_from_file_location("planner_wake_dsh_base", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_types = _base()


def _command_prefix(executable) -> tuple[str, ...]:
    if isinstance(executable, (tuple, list)):
        return tuple(str(value) for value in executable)
    return (str(executable),)


def _present(command, cwd):
    subprocess.Popen(command, cwd=cwd)


class DeepSeekHarnessPlannerWakeAdapter:
    """ACP client bridge; capability stays static-only until a real smoke passes."""

    def __init__(
        self,
        executable="dsh",
        presenter=None,
        real_session_verified: bool = False,
        timeout_seconds: float = 300,
    ):
        self.executable = executable
        self.presenter = presenter or _present
        self.real_session_verified = real_session_verified
        self.timeout_seconds = timeout_seconds

    def probe(self, channel):
        transport = "verified" if self.real_session_verified else "static_only"
        end_to_end = "verified" if self.real_session_verified else "static_only"
        return _types.WakeCapabilities(transport, transport, "experimental", end_to_end)

    def resume(self, channel):
        return None

    def _request(self, process, selector, request_id: int, method: str, params: dict):
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
        }) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError(f"DeepSeek Harness ACP timed out waiting for {method}")
            raw = process.stdout.readline()
            if not raw:
                raise RuntimeError(f"DeepSeek Harness ACP closed while waiting for {method}")
            message = json.loads(raw)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"DeepSeek Harness ACP {method} failed: {message['error']}")
            return message.get("result", {})

    def submit_report(self, channel, request):
        prompt = _types.build_reporting_prompt(request)
        command = _command_prefix(self.executable) + ("--profile", "acp")
        process = subprocess.Popen(
            command,
            cwd=request.repo,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )
        stderr_tail: list[str] = []

        def drain_stderr():
            assert process.stderr is not None
            for line in process.stderr:
                stderr_tail.append(line.rstrip())
                del stderr_tail[:-40]

        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stderr_thread.start()
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        failure = None
        try:
            initialized = self._request(
                process, selector, 1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
            )
            capabilities = initialized.get("agentCapabilities", {}).get("sessionCapabilities", {})
            if "resume" not in capabilities:
                raise RuntimeError("DeepSeek Harness ACP does not advertise session/resume")
            self._request(process, selector, 2, "session/resume", {
                "sessionId": channel.conversation_id, "cwd": str(request.repo), "mcpServers": [],
            })
            result = self._request(process, selector, 3, "session/prompt", {
                "sessionId": channel.conversation_id,
                "prompt": [{"type": "text", "text": prompt}],
            })
            if result.get("stopReason") not in {"end_turn", "max_tokens"}:
                raise RuntimeError(f"DeepSeek Harness Planner did not reach idle: {result!r}")
        except Exception as error:
            failure = error
        finally:
            selector.close()
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            stderr_thread.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        if failure is not None:
            raise failure
        if process.returncode != 0:
            raise RuntimeError(
                f"DeepSeek Harness ACP exited {process.returncode}: {' | '.join(stderr_tail[-40:])}"
            )
        remote_id = f"acp:{channel.conversation_id}:{request.wake_key}"
        return _types.SubmissionReceipt(
            request.wake_key,
            "deepseek-harness",
            channel.conversation_id,
            remote_id,
            "submitted",
            command,
        )

    def observe(self, receipt):
        return _types.ObservationResult("completed")

    def present(self, channel):
        command = _command_prefix(self.executable) + (
            "--profile", "tui", "--resume", channel.conversation_id,
        )
        self.presenter(command, channel.project_path)
        return _types.PresentationResult("presented")
