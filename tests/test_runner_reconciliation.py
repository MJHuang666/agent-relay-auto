import unittest

from tests.shared.agent_relay_runtime_loader import load_runtime_module


recovery = load_runtime_module("recovery")


class RunnerReconciliationTests(unittest.TestCase):
    def test_same_pid_start_time_and_run_id_is_resumable(self):
        manager = recovery.RecoveryManager(None)
        result = manager.reconcile({"pid": 123, "process_started_at": 10.0, "run_id": "run-1"}, process_exists=True, observed_started_at=10.0)
        self.assertEqual(result.status, "monitor")


if __name__ == "__main__":
    unittest.main()
