import sys
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


process_manager = load_runtime_module("process_manager")
recovery = load_runtime_module("recovery")


class InterruptRecoveryTests(unittest.TestCase):
    def test_interrupt_uses_sigint_and_records_checkpoint_output(self):
        fixture = Path(__file__).resolve().parent / "fixtures/signal_agent_cli.py"
        manager = process_manager.ProcessManager()
        managed = manager.start((sys.executable, str(fixture)), Path.cwd(), "run-001")
        time.sleep(0.05)
        result = recovery.RecoveryManager(manager).interrupt(managed, grace_seconds=0.2)
        self.assertEqual(result.exit_code, 130)
        self.assertIn("checkpoint-written", result.stdout)

    def test_reconcile_rejects_pid_reuse_and_unknown_remote(self):
        manager = recovery.RecoveryManager(process_manager.ProcessManager())
        result = manager.reconcile({"pid": 123, "process_started_at": 10.0, "run_id": "run-1"}, process_exists=True, observed_started_at=11.0)
        self.assertEqual(result.status, "blocked")
        remote = manager.reconcile({"pid": None, "process_started_at": None, "run_id": "run-2", "remote": True}, process_exists=False, observed_started_at=None)
        self.assertEqual(remote.status, "blocked")


if __name__ == "__main__":
    unittest.main()
