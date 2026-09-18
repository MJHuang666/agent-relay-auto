import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


store_module = load_runtime_module("state_store")


PROJECT = """# Project Status

```yaml
project: Demo
goal: Test
language: en-US
active_task: TASK-001
tasks:
  active: ["TASK-001"]
  queued: []
  blocked: []
  completed: []
updated_at: null
```
"""

STATE = """# Task State

```yaml
task: TASK-001
title: Demo
language: en-US
status: PLANNING
revision: 4
stage_round: 1
run_id: null
run_status: idle
run_attempt: 0
rework_round: 0
auto_replan_count: 0
agent_failure_count: 0
runtime_snapshot_ref: null
current_role: planner
current_participant: planner-a
writer_session: null
execution: idle
next_expected_output: plan.md
question_id: null
question_ref: null
suspended_status: null
resume_role: null
blocked_reason: null
```
"""


class AutomationTransitionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        (self.repo / ".git").mkdir()
        task = self.repo / "docs/agent/tasks/TASK-001"
        task.mkdir(parents=True)
        (self.repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
        (task / "STATE.md").write_text(STATE, encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_valid_transition_increments_revision(self):
        store = store_module.StateStore(self.repo)
        result = store.transition("TASK-001", 4, "plan_completed", {})
        self.assertEqual(result.new_status, "IMPLEMENTING")
        self.assertEqual(result.output_revision, 5)
        self.assertIn(
            "status: IMPLEMENTING",
            (self.repo / "docs/agent/tasks/TASK-001/STATE.md").read_text(),
        )

    def test_invalid_direct_done_transition_is_rejected_without_write(self):
        store = store_module.StateStore(self.repo)
        with self.assertRaises(store_module.TransitionError):
            store.transition("TASK-001", 4, "review_passed", {})
        self.assertIn(
            "revision: 4",
            (self.repo / "docs/agent/tasks/TASK-001/STATE.md").read_text(),
        )

    def test_same_claim_key_is_idempotent(self):
        store = store_module.StateStore(self.repo)
        key = store_module.ClaimKey("TASK-001", 4, "planner-a", 1)
        first = store.claim(key, "run-001")
        second = store.claim(key, "run-001")
        self.assertFalse(first.idempotent_replay)
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(first.output_revision, second.output_revision)


if __name__ == "__main__":
    unittest.main()
