"""Wake an exact Claude Code Planner session."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _base():
    path = Path(__file__).with_name("base.py")
    spec = importlib.util.spec_from_file_location("planner_wake_claude_base", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_types = _base()


def _run(command, cwd):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


class ClaudeCodePlannerWakeAdapter:
    def __init__(self, executable="claude", command_runner=None):
        self.executable = executable
        self.command_runner = command_runner or _run

    def probe(self, channel):
        return _types.WakeCapabilities("verified", "verified", "verified", "experimental")

    def resume(self, channel):
        return None

    def submit_report(self, channel, request):
        prompt = _types.build_reporting_prompt(request)
        command = (self.executable, "-p", "--resume", channel.conversation_id, "--output-format", "json", prompt)
        payload = self.command_runner(command, request.repo)
        session_id = payload.get("session_id")
        if session_id != channel.conversation_id:
            raise RuntimeError(f"Claude Code returned mismatched session {session_id!r}")
        remote_id = payload.get("message_id")
        if not remote_id:
            remote_id = "session:" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
        return _types.SubmissionReceipt(
            request.wake_key, "claude-code", session_id, str(remote_id), "submitted", command
        )

    def observe(self, receipt):
        return _types.ObservationResult("completed")

    def reconcile(self, channel, wake_key):
        return None

    def present(self, channel):
        subprocess.Popen((self.executable, "--resume", channel.conversation_id), cwd=channel.project_path)
        return _types.PresentationResult("presented")
