import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


state_store = load_runtime_module("report_transaction_state_store", "state_store.py")


class ReportTransactionRecoveryTests(unittest.TestCase):
    def test_crash_between_task_and_project_write_is_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(
                '# Project\n\n```yaml\nactive_task: TASK-001\ntasks:\n  active: ["TASK-001"]\n'
                '  queued: []\n  blocked: []\n  completed: []\n```\n', encoding="utf-8",
            )
            (task / "STATE.md").write_text(
                '# State\n\n```yaml\ntask: TASK-001\nstatus: REPORTING\nrevision: 9\n'
                'stage_round: 3\ncurrent_role: planner\ncurrent_participant: planner-a\n'
                'assignments:\n  planner: planner-a\nreview_ref: review.md\ndelivery_id: delivery-1\n'
                'reporting:\n  phase: active\n  wake_key: wake-9\n```\n', encoding="utf-8",
            )
            store = state_store.StateStore(repo)
            original = store._write_state
            calls = 0

            def fail_second_write(path, text, values):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated project index write crash")
                return original(path, text, values)

            store._write_state = fail_second_write
            with self.assertRaises(OSError):
                store.complete_report(
                    "TASK-001", 9, "planner-a", "wake-9", "delivery-1", "review.md", "report.md"
                )
            self.assertIn("status: DONE", (task / "STATE.md").read_text())
            self.assertIn("active_task: TASK-001", (repo / "docs/agent/PROJECT_STATUS.md").read_text())

            recovered = state_store.StateStore(repo).recover_pending_transactions()
            self.assertEqual(recovered, ("TASK-001",))
            project = (repo / "docs/agent/PROJECT_STATUS.md").read_text()
            self.assertIn("active_task: null", project)
            self.assertIn('completed: ["TASK-001"]', project)
            self.assertFalse((repo / ".agent-relay-auto/transactions/report-TASK-001.json").exists())


if __name__ == "__main__":
    unittest.main()
