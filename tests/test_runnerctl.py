import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


runnerctl = load_runtime_module("runnerctl", "../runnerctl.py")


class RunnerCtlTests(unittest.TestCase):
    def test_dry_run_actions_are_json_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runnerctl.command_status(Path(directory), dry_run=True)
            self.assertEqual(result["status"], "dry-run")
            self.assertIn("actions", result)


if __name__ == "__main__":
    unittest.main()
