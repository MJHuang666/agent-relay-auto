import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


base = load_runtime_module("planner_wake_base", "planner_wake/base.py")
factory_module = load_runtime_module("planner_wake_factory", "planner_wake/factory.py")


class PlannerWakeContractTests(unittest.TestCase):
    def test_receipt_preserves_remote_identity(self):
        receipt = base.SubmissionReceipt("wk", "codex", "thr_1", "turn_9", "submitted")
        self.assertEqual(receipt.conversation_id, "thr_1")
        self.assertEqual(receipt.remote_id, "turn_9")

    def test_factory_does_not_fallback_to_another_tool(self):
        factory = factory_module.create_planner_wake_factory({"codex": lambda: object()})
        with self.assertRaisesRegex(factory_module.WakeAdapterUnavailable, "opencode"):
            factory("opencode")

    def test_default_factory_registers_three_verified_cli_tools(self):
        factory = factory_module.create_planner_wake_factory()
        self.assertEqual(type(factory("codex")).__name__, "CodexPlannerWakeAdapter")
        self.assertEqual(type(factory("opencode")).__name__, "OpenCodePlannerWakeAdapter")
        self.assertEqual(type(factory("claude-code")).__name__, "ClaudeCodePlannerWakeAdapter")

    def test_capability_labels_are_closed_and_prompt_has_authority_fields(self):
        with self.assertRaises(base.WakeContractError):
            base.WakeCapabilities("verified", "verified", "maybe", "verified")
        with tempfile.TemporaryDirectory() as directory:
            request = base.WakeRequest(Path(directory), "TASK-1", 7, "planner-a", "wake-7")
            prompt = base.build_reporting_prompt(request)
            for value in ("TASK-1", "7", "planner-a", "wake-7", "report-done"):
                self.assertIn(value, prompt)
            for forbidden in ("merge", "push", "release", "deploy"):
                self.assertIn(forbidden, prompt)


if __name__ == "__main__":
    unittest.main()
