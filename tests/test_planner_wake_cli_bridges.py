import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.shared.agent_relay_runtime_loader import load_runtime_module


base = load_runtime_module("wake_bridge_base", "planner_wake/base.py")
opencode = load_runtime_module("wake_bridge_opencode", "planner_wake/opencode.py")
claude = load_runtime_module("wake_bridge_claude", "planner_wake/claude_code.py")
codex = load_runtime_module("wake_bridge_codex", "planner_wake/codex.py")


class RecordingRunner:
    def __init__(self, payload):
        self.payload = payload
        self.commands = []

    def __call__(self, command, cwd):
        self.commands.append((tuple(command), Path(cwd)))
        return self.payload


class FakeCodexTransport:
    def __init__(self, thread_id, turn_id, turns=None):
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.turns = turns or []
        self.methods = []

    def request(self, method, params):
        self.methods.append(method)
        if method == "thread/read":
            return {"thread": {"id": self.thread_id, "turns": self.turns}}
        if method == "thread/resume":
            return {"thread": {"id": self.thread_id}}
        return {"turn": {"id": self.turn_id}}

    def close(self):
        pass


class PlannerWakeCliBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.directory.name)
        self.request = base.WakeRequest(self.repo, "TASK-1", 7, "planner-a", "wake-7")

    def tearDown(self):
        self.directory.cleanup()

    def channel(self, tool, conversation_id):
        return SimpleNamespace(tool=tool, conversation_id=conversation_id, project_path=str(self.repo))

    def test_opencode_uses_exact_session_without_fork(self):
        runner = RecordingRunner({"session_id": "ses_1", "message_id": "msg_1"})
        adapter = opencode.OpenCodePlannerWakeAdapter(command_runner=runner)
        receipt = adapter.submit_report(self.channel("opencode", "ses_1"), self.request)
        self.assertEqual(receipt.conversation_id, "ses_1")
        self.assertIn("--session", receipt.debug_command)
        self.assertNotIn("--fork", receipt.debug_command)

    def test_claude_never_uses_continue_and_rejects_session_mismatch(self):
        runner = RecordingRunner({"session_id": "ses_1", "result": "ok"})
        receipt = claude.ClaudeCodePlannerWakeAdapter(command_runner=runner).submit_report(
            self.channel("claude-code", "ses_1"), self.request
        )
        self.assertIn("--resume", receipt.debug_command)
        self.assertNotIn("--continue", receipt.debug_command)
        bad = RecordingRunner({"session_id": "other", "result": "ok"})
        with self.assertRaisesRegex(RuntimeError, "session"):
            claude.ClaudeCodePlannerWakeAdapter(command_runner=bad).submit_report(
                self.channel("claude-code", "ses_1"), self.request
            )

    def test_codex_resumes_exact_thread_and_returns_turn_receipt(self):
        transport = FakeCodexTransport("thr_1", "turn_9")
        adapter = codex.CodexPlannerWakeAdapter(transport_factory=lambda: transport)
        receipt = adapter.submit_report(self.channel("codex", "thr_1"), self.request)
        self.assertEqual(receipt.conversation_id, "thr_1")
        self.assertEqual(receipt.remote_id, "turn_9")
        self.assertEqual(transport.methods, ["thread/read", "thread/resume", "turn/start"])
        self.assertEqual(adapter.present(self.channel("codex", "thr_1")).status, "experimental")

    def test_codex_reconciles_ambiguous_submission_by_wake_key_in_exact_thread(self):
        transport = FakeCodexTransport(
            "thr_1", "unused", turns=[{"id": "turn_existing", "input": "wake-7"}]
        )
        adapter = codex.CodexPlannerWakeAdapter(transport_factory=lambda: transport)
        receipt = adapter.reconcile(self.channel("codex", "thr_1"), "wake-7")
        self.assertEqual(receipt.remote_id, "turn_existing")
        self.assertEqual(receipt.conversation_id, "thr_1")


if __name__ == "__main__":
    unittest.main()
