import sys
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


codex = load_runtime_module("codex", "adapters/codex.py")
opencode = load_runtime_module("opencode", "adapters/opencode.py")
claude = load_runtime_module("claude_code", "adapters/claude_code.py")
base = load_runtime_module("base", "adapters/base.py")


class CliAdapterTests(unittest.TestCase):
    def request(self, model="test-model"):
        return base.LaunchRequest(Path("/tmp/repo"), "TASK-001", "implementer", "impl-1", model, "high", "run-1", 7)

    def context(self, request):
        return base.LaunchContext.from_state(
            request,
            {
                "status": "IMPLEMENTING", "revision": 8, "stage_round": 1,
                "writer_session": "run-1", "plan_version": 1,
                "subagent_policy": "DO_NOT_USE",
            },
        )

    def test_codex_discovers_models_and_builds_noninteractive_command(self):
        fixture = Path(__file__).resolve().parent / "fixtures/codex_app_server_fixture.py"
        adapter = codex.CodexAdapter(sys.executable, fixture)
        self.assertEqual(adapter.list_models()[0].model_id, "gpt-test")
        request = self.request()
        command = adapter.build_command(request, self.context(request))
        self.assertIn("exec", command)
        self.assertIn("--json", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("run-1", command[-1])
        self.assertIn('model_reasoning_effort="high"', command)

    def test_opencode_preserves_provider_model_and_resume_session(self):
        fixture = Path(__file__).resolve().parent / "fixtures/opencode_fixture.py"
        adapter = opencode.OpenCodeAdapter(sys.executable, fixture)
        self.assertEqual(adapter.list_models(), ("openai/gpt-test", "anthropic/claude-test"))
        request = self.request("openai/gpt-test")
        command = adapter.build_command(request, self.context(request))
        self.assertIn("run", command)
        self.assertIn("--variant", command)
        self.assertIn("high", command)
        self.assertIn("run-1", command[-1])
        resume = adapter.resume_command(self.request(), "session-1")
        self.assertIn("--session", resume)

    def test_claude_uses_print_stream_json_and_resume(self):
        fixture = Path(__file__).resolve().parent / "fixtures/claude_fixture.py"
        adapter = claude.ClaudeCodeAdapter(sys.executable, fixture)
        request = self.request("claude-test")
        command = adapter.build_command(request, self.context(request))
        self.assertIn("-p", command)
        self.assertIn("stream-json", command)
        self.assertIn("--effort", command)
        self.assertIn("run-1", command[-1])
        self.assertIn("--resume", adapter.resume_command(self.request(), "session-1"))


if __name__ == "__main__":
    unittest.main()
