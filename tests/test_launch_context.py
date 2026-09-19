import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


base = load_runtime_module("launch_context_base", "adapters/base.py")


class LaunchContextTests(unittest.TestCase):
    def request(self):
        return base.LaunchRequest(
            Path("/tmp/repo"), "TASK-001", "implementer", "implementer-codex",
            "gpt-test", "high", "run-1", 7,
        )

    def state(self):
        return {
            "task": "TASK-001",
            "status": "IMPLEMENTING",
            "revision": 8,
            "stage_round": 2,
            "writer_session": "run-1",
            "plan_version": 1,
            "subagent_policy": "DO_NOT_USE",
        }

    def test_context_identifies_current_run_as_writer(self):
        context = base.LaunchContext.from_state(self.request(), self.state())
        self.assertEqual(context.run_id, "run-1")
        self.assertEqual(context.writer_session, "run-1")
        self.assertEqual(context.start_revision, 8)
        self.assertEqual(context.subagent_policy, "DO_NOT_USE")
        self.assertIn("execution.md", context.required_outputs)

    def test_prompt_contains_identity_evidence_and_completion_command(self):
        context = base.LaunchContext.from_state(self.request(), self.state())
        prompt = base.build_role_prompt(self.request(), context)
        for value in ("implementer-codex", "run-1", "writer_session", "implementation-done"):
            self.assertIn(value, prompt)
        self.assertIn("not a foreign writer", prompt)
        self.assertIn("final chat response alone does not complete", prompt)


if __name__ == "__main__":
    unittest.main()
