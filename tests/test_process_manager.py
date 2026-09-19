import sys
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


process_manager = load_runtime_module("process_manager")


class ProcessManagerTests(unittest.TestCase):
    def test_starts_and_polls_process_with_identity_snapshot(self):
        fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
        manager = process_manager.ProcessManager()
        managed = manager.start(
            (sys.executable, str(fixture), "--sleep", "0.01"),
            Path.cwd(),
            "run-001",
        )
        self.assertEqual(managed.run_id, "run-001")
        deadline = time.time() + 2
        result = None
        while time.time() < deadline and result is None:
            result = manager.poll(managed)
            time.sleep(0.01)
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("fake-agent-start", result.stdout)

    def test_large_stream_is_drained_without_deadlock_and_keeps_tail(self):
        fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
        manager = process_manager.ProcessManager(output_limit_chars=128 * 1024)
        managed = manager.start(
            (sys.executable, str(fixture), "--output-bytes", str(2 * 1024 * 1024)),
            Path.cwd(),
            "run-large",
        )
        deadline = time.time() + 5
        result = None
        while time.time() < deadline and result is None:
            result = manager.poll(managed)
            time.sleep(0.01)
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("fake-agent-finish", result.stdout)
        self.assertLessEqual(len(result.stdout), 128 * 1024)


if __name__ == "__main__":
    unittest.main()
