import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


state_store = load_runtime_module("relay_cli_state_store", "state_store.py")


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "shared/.agents/skills/agent-relay-auto/scripts/relay_state.py"
)


PROJECT = """# Project Status

```yaml
project: Demo
active_task: TASK-001
tasks:
  active: ["TASK-001"]
  queued: []
  blocked: []
  completed: []
```
"""


STATE = """# Task State

```yaml
task: TASK-001
title: Demo
language: en-US
status: REVIEWING
revision: 4
stage_round: 2
run_status: idle
run_attempt: 0
rework_round: 0
auto_replan_count: 0
agent_failure_count: 0
runtime_snapshot_ref: null
current_role: reviewer
current_participant: reviewer-a
writer_session: run-review-1
assignments:
  planner: planner-a
  implementer: impl-a
  reviewer: reviewer-a
run_id: run-review-1
execution: idle
next_expected_output: review.md
question_id: null
question_ref: null
suspended_status: null
resume_role: null
blocked_reason: null
```
"""


class RelayStateCliTests(unittest.TestCase):
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

    def run_cli(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_wait_user_requires_matching_revision_and_answer_restores_status(self):
        question = self.repo / "question.md"
        question.write_text("Choose deployment target.\n", encoding="utf-8")
        self.run_cli(
            "wait-user",
            "--task",
            "TASK-001",
            "--expected-revision",
            "4",
            "--question-file",
            str(question),
            "--resume-role",
            "reviewer",
        )
        state = (self.repo / "docs/agent/tasks/TASK-001/STATE.md").read_text()
        self.assertIn("status: WAITING_USER", state)
        self.assertIn("question_id:", state)
        question_id = next(line.split(":", 1)[1].strip() for line in state.splitlines() if line.startswith("question_id:"))
        answer = self.repo / "answer.md"
        answer.write_text("staging\n", encoding="utf-8")
        self.run_cli(
            "answer",
            "--task",
            "TASK-001",
            "--expected-revision",
            "5",
            "--question-id",
            question_id,
            "--answer-file",
            str(answer),
        )
        self.assertIn("status: REVIEWING", (self.repo / "docs/agent/tasks/TASK-001/STATE.md").read_text())

    def test_reviewer_cannot_pass_without_evidence_and_report_is_required_for_done(self):
        self.run_cli(
            "verdict",
            "--task",
            "TASK-001",
            "--expected-revision",
            "4",
            "--verdict",
            "PASS",
            "--evidence",
            str(self.repo / "missing.md"),
            "--participant-id",
            "reviewer-a",
            "--run-id",
            "run-review-1",
            "--delivery-ref",
            "execution.md#delivery-1",
            expected=2,
        )
        (self.repo / "docs/agent/tasks/TASK-001/execution.md").write_text("delivery evidence\n", encoding="utf-8")
        evidence = self.repo / "evidence.md"
        evidence.write_text("tests passed\n", encoding="utf-8")
        self.run_cli(
            "verdict",
            "--task",
            "TASK-001",
            "--expected-revision",
            "4",
            "--verdict",
            "PASS",
            "--evidence",
            str(evidence),
            "--participant-id",
            "reviewer-a",
            "--run-id",
            "run-review-1",
            "--delivery-ref",
            "execution.md#delivery-1",
        )
        state_store.StateStore(self.repo).finish_run("TASK-001", "run-review-1", 0)
        state_path = self.repo / "docs/agent/tasks/TASK-001/STATE.md"
        state_text = state_path.read_text(encoding="utf-8")
        state_text = state_text.replace(
            "blocked_reason: null",
            "blocked_reason: null\ndelivery_id: delivery-1\nreporting:\n  phase: active\n  wake_key: wake-1",
        )
        state_path.write_text(state_text, encoding="utf-8")
        report = self.repo / "report.md"
        report.write_text("# Final Report\n\nGoal\nDelivery\nTests\nReviewer evidence\nLimitations\nUsage\nNot executed: merge, push, release, deploy\n", encoding="utf-8")
        self.run_cli(
            "report-done",
            "--task",
            "TASK-001",
            "--expected-revision",
            "6",
            "--report",
            str(report),
            "--participant-id",
            "planner-a",
            "--wake-key",
            "wake-1",
            "--review-delivery-id",
            "delivery-1",
            "--review-ref",
            str(evidence),
        )
        completed_state = (self.repo / "docs/agent/tasks/TASK-001/STATE.md").read_text()
        completed_project = (self.repo / "docs/agent/PROJECT_STATUS.md").read_text()
        self.assertIn("status: DONE", completed_state)
        self.assertIn('reporting: {"phase":"completed","wake_key":"wake-1"}', completed_state)
        self.assertIn("active_task: null", completed_project)
        self.assertIn('active: []', completed_project)
        self.assertIn('completed: ["TASK-001"]', completed_project)

    def test_report_done_rejects_mismatched_wake_delivery_and_runner_identity_without_mutation(self):
        task = self.repo / "docs/agent/tasks/TASK-001"
        review = task / "review.md"
        review.write_text("Reviewer PASS evidence for delivery-1\n", encoding="utf-8")
        report = task / "final-report.md"
        report.write_text(
            "Goal\nDelivery\nTests\nReviewer evidence\nLimitations\nUsage\n"
            "Not executed: merge, push, release, deploy\n",
            encoding="utf-8",
        )
        state_path = task / "STATE.md"
        state_path.write_text(
            STATE.replace("status: REVIEWING", "status: REPORTING")
            .replace("current_role: reviewer", "current_role: planner")
            .replace("current_participant: reviewer-a", "current_participant: planner-a")
            .replace("revision: 4", "revision: 9")
            .replace(
                "blocked_reason: null",
                "blocked_reason: null\nreview_ref: review.md\ndelivery_id: delivery-1\n"
                "reporting:\n  phase: active\n  wake_key: wake-9",
            ),
            encoding="utf-8",
        )
        project_path = self.repo / "docs/agent/PROJECT_STATUS.md"

        for participant, wake_key, delivery_id, expected_message in (
            ("planner-a", "wrong", "delivery-1", "wake_key"),
            ("planner-a", "wake-9", "delivery-2", "delivery_id"),
            ("runner", "wake-9", "delivery-1", "Runner"),
        ):
            before_state = state_path.read_bytes()
            before_project = project_path.read_bytes()
            result = self.run_cli(
                "report-done", "--task", "TASK-001", "--expected-revision", "9",
                "--participant-id", participant, "--wake-key", wake_key,
                "--review-delivery-id", delivery_id, "--report", str(report),
                "--review-ref", "review.md", expected=3,
            )
            self.assertIn(expected_message, result.stderr)
            self.assertEqual(state_path.read_bytes(), before_state)
            self.assertEqual(project_path.read_bytes(), before_project)

    def test_subagent_answer_updates_policy_and_rejects_invalid_value_without_artifact(self):
        question = self.repo / "question.md"
        question.write_text("USE or DO_NOT_USE\n", encoding="utf-8")
        self.run_cli(
            "wait-user", "--task", "TASK-001", "--expected-revision", "4",
            "--question-file", str(question), "--resume-role", "reviewer",
        )
        state_path = self.repo / "docs/agent/tasks/TASK-001/STATE.md"
        state = state_path.read_text(encoding="utf-8")
        question_id = next(line.split(":", 1)[1].strip() for line in state.splitlines() if line.startswith("question_id:"))
        answer = self.repo / "answer.md"
        answer.write_text("DO_NOT_USE\n", encoding="utf-8")
        self.run_cli(
            "answer", "--task", "TASK-001", "--expected-revision", "5",
            "--question-id", question_id, "--answer-file", str(answer),
            "--decision-key", "subagent_policy", "--decision-value", "MAYBE", expected=2,
        )
        decisions = self.repo / "docs/agent/tasks/TASK-001/decisions"
        self.assertFalse(decisions.exists())
        self.run_cli(
            "answer", "--task", "TASK-001", "--expected-revision", "5",
            "--question-id", question_id, "--answer-file", str(answer),
            "--decision-key", "subagent_policy", "--decision-value", "DO_NOT_USE",
        )
        updated = state_path.read_text(encoding="utf-8")
        self.assertIn("subagent_policy: DO_NOT_USE", updated)
        self.assertIn(f"subagent_decision_ref: decisions/{question_id}.md", updated)


if __name__ == "__main__":
    unittest.main()
