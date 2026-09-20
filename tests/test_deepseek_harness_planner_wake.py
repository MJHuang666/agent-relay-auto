import sys
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


base = load_runtime_module("dsh_wake_base", "planner_wake/base.py")
dsh = load_runtime_module("dsh_wake_adapter", "planner_wake/deepseek_harness.py")
factory = load_runtime_module("dsh_wake_factory", "planner_wake/factory.py")


class Channel:
    tool = "deepseek-harness"
    conversation_id = "dsh-session-1"
    participant_id = "planner-dsh"

    def __init__(self, project_path):
        self.project_path = str(project_path)


class DeepSeekHarnessPlannerWakeTests(unittest.TestCase):
    def test_resumes_exact_session_submits_once_and_waits_for_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            fixture = Path(__file__).parent / "fixtures/deepseek_harness_fixture.py"
            presented = []
            adapter = dsh.DeepSeekHarnessPlannerWakeAdapter(
                executable=(sys.executable, str(fixture)),
                presenter=lambda command, cwd: presented.append((command, cwd)),
            )
            channel = Channel(repo)
            request = base.WakeRequest(repo, "TASK-1", 7, "planner-dsh", "wake-7")

            receipt = adapter.submit_report(channel, request)

            self.assertEqual(receipt.conversation_id, channel.conversation_id)
            self.assertTrue(receipt.remote_id)
            self.assertEqual(adapter.observe(receipt).status, "completed")
            self.assertIn("--profile", receipt.debug_command)
            self.assertIn("acp", receipt.debug_command)
            adapter.present(channel)
            self.assertEqual(
                presented[0][0],
                (sys.executable, str(fixture), "--profile", "tui", "--resume", "dsh-session-1"),
            )

    def test_static_probe_is_not_claimed_as_verified(self):
        adapter = dsh.DeepSeekHarnessPlannerWakeAdapter(real_session_verified=False)
        capabilities = adapter.probe(Channel("/tmp/project"))
        self.assertIn(capabilities.end_to_end_reporting, {"static_only", "experimental"})
        self.assertNotEqual(capabilities.end_to_end_reporting, "verified")

    def test_real_session_flag_only_upgrades_resume_and_submit(self):
        adapter = dsh.DeepSeekHarnessPlannerWakeAdapter(real_session_verified=True)
        capabilities = adapter.probe(Channel("/tmp/project"))
        self.assertEqual(capabilities.resume_original_conversation, "verified")
        self.assertEqual(capabilities.submit_turn, "verified")
        self.assertEqual(capabilities.reopen_original_ui, "experimental")

    def test_default_factory_registers_deepseek_harness(self):
        adapter = factory.create_planner_wake_factory()("deepseek-harness")
        self.assertEqual(type(adapter).__name__, "DeepSeekHarnessPlannerWakeAdapter")


if __name__ == "__main__":
    unittest.main()
