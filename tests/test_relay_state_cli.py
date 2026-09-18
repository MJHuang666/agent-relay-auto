import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
run_id: null
run_status: idle
run_attempt: 0
rework_round: 0
auto_replan_count: 0
agent_failure_count: 0
runtime_snapshot_ref: null
current_role: reviewer
current_participant: reviewer-a
writer_session: null
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
            expected=2,
        )
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
        )
        report = self.repo / "report.md"
        report.write_text("# Final Report\n\nGoal\nDelivery\nTests\nReviewer evidence\nLimitations\nUsage\nNot executed: merge, push, release, deploy\n", encoding="utf-8")
        self.run_cli(
            "report-done",
            "--task",
            "TASK-001",
            "--expected-revision",
            "5",
            "--report",
            str(report),
        )
        self.assertIn("status: DONE", (self.repo / "docs/agent/tasks/TASK-001/STATE.md").read_text())


if __name__ == "__main__":
    unittest.main()
