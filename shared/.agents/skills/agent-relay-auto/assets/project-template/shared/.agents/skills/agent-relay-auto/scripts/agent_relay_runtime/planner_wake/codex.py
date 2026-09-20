"""Wake an exact Codex Planner thread through App Server."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path


def _base():
    path = Path(__file__).with_name("base.py")
    spec = importlib.util.spec_from_file_location("planner_wake_codex_base", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_types = _base()


class CodexAppServerTransport:
    def __init__(self, executable="codex"):
        self.process = subprocess.Popen(
            (executable, "app-server"), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        self.request("initialize", {"clientInfo": {"name": "agent-relay-auto", "version": "1.8.0"}, "capabilities": {}})
        self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    def _send(self, payload):
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        request_id = str(uuid.uuid4())
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("Codex App Server exited before replying")
            payload = json.loads(line)
            if str(payload.get("id")) == request_id:
                if "error" in payload:
                    raise RuntimeError(f"Codex App Server error: {payload['error']}")
                return payload.get("result", {})

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)


class CodexPlannerWakeAdapter:
    def __init__(self, transport_factory=None):
        self.transport_factory = transport_factory or CodexAppServerTransport

    def probe(self, channel):
        return _types.WakeCapabilities("verified", "verified", "experimental", "experimental")

    def resume(self, channel):
        return None

    def submit_report(self, channel, request):
        transport = self.transport_factory()
        try:
            read = transport.request("thread/read", {"threadId": channel.conversation_id, "includeTurns": False})
            if read.get("thread", {}).get("id") != channel.conversation_id:
                raise RuntimeError("Codex thread/read returned a different thread")
            resumed = transport.request("thread/resume", {"threadId": channel.conversation_id})
            if resumed.get("thread", {}).get("id") != channel.conversation_id:
                raise RuntimeError("Codex thread/resume returned a different thread")
            turn = transport.request(
                "turn/start",
                {"threadId": channel.conversation_id, "input": [{"type": "text", "text": _types.build_reporting_prompt(request)}]},
            )
            turn_id = turn.get("turn", {}).get("id")
            if not isinstance(turn_id, str) or not turn_id:
                raise RuntimeError("Codex turn/start did not return a turn ID")
            return _types.SubmissionReceipt(request.wake_key, "codex", channel.conversation_id, turn_id, "submitted")
        finally:
            transport.close()

    def observe(self, receipt):
        return _types.ObservationResult("submitted")

    def reconcile(self, channel, wake_key):
        transport = self.transport_factory()
        try:
            result = transport.request("thread/read", {"threadId": channel.conversation_id, "includeTurns": True})
            thread = result.get("thread", {})
            if thread.get("id") != channel.conversation_id:
                raise RuntimeError("Codex reconciliation returned a different thread")
            for turn in reversed(thread.get("turns", [])):
                if wake_key in json.dumps(turn, ensure_ascii=False, sort_keys=True):
                    turn_id = turn.get("id")
                    if isinstance(turn_id, str) and turn_id:
                        return _types.SubmissionReceipt(
                            wake_key, "codex", channel.conversation_id, turn_id, "submitted"
                        )
            return None
        finally:
            transport.close()

    def present(self, channel):
        return _types.PresentationResult("experimental", "Exact Codex Desktop navigation is not yet verified")
