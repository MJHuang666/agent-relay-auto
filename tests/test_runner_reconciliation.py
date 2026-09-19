import unittest

from tests.shared.agent_relay_runtime_loader import load_runtime_module


recovery = load_runtime_module("recovery")


class RunnerReconciliationTests(unittest.TestCase):
    def test_same_pid_start_time_and_run_id_is_resumable(self):
        manager = recovery.RecoveryManager(None)
        result = manager.reconcile({"pid": 123, "process_started_at": 10.0, "run_id": "run-1"}, process_exists=True, observed_started_at=10.0)
        self.assertEqual(result.status, "monitor")

    def test_exit_record_wins_after_runner_restart(self):
        manager = recovery.RecoveryManager(None)
        result = manager.reconcile(
            {"pid": 123, "process_started_at": 10.0, "run_id": "run-1"},
            process_exists=True,
            observed_started_at=10.0,
            exit_record={"run_id": "run-1", "exit_code": 0, "termination_reason": "exit"},
        )
        self.assertEqual(result.status, "finish")

    def test_missing_worker_without_exit_is_interrupted(self):
        manager = recovery.RecoveryManager(None)
        result = manager.reconcile(
            {"pid": 123, "process_started_at": 10.0, "run_id": "run-1"},
            process_exists=False,
            observed_started_at=None,
            exit_record=None,
        )
        self.assertEqual(result.status, "interrupted")

    def test_pid_start_mismatch_is_blocked(self):
        manager = recovery.RecoveryManager(None)
        result = manager.reconcile(
            {"pid": 123, "process_started_at": 10.0, "run_id": "run-1"},
            process_exists=True,
            observed_started_at=11.0,
            exit_record=None,
        )
        self.assertEqual(result.status, "blocked")


if __name__ == "__main__":
    unittest.main()
