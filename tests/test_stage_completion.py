import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "shared/.agents/skills/agent-relay-auto/scripts/relay_state.py"


class StageCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        (self.repo / ".git").mkdir()
        self.task = self.repo / "docs/agent/tasks/TASK-001"
        self.task.mkdir(parents=True)
        (self.repo / "docs/agent/PROJECT_STATUS.md").write_text(
            """# Project\n\n```yaml\nactive_task: TASK-001\ntasks:\n  active: [\"TASK-001\"]\n  queued: []\n  blocked: []\n  completed: []\n```\n""",
            encoding="utf-8",
        )
        self.state_path = self.task / "STATE.md"
        self.write_implementing_state()
        for name, content in {
            "execution.md": "# Execution\n\ndelivery_id: delivery-1\ntests: pass\n",
            "progress.md": "# Progress\n\nimplementation complete\n",
            "plan.md": "# Plan\n\napproved\n",
            "approval.md": "approved by user\n",
            "review.md": "# Review\n\nPASS with tests\n",
            "report.md": "Goal\nDelivery\nTests\nReviewer\nLimitations\nUsage\nNot executed: merge push release deploy\n",
        }.items():
            (self.task / name).write_text(content, encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def write_implementing_state(self):
        self.state_path.write_text(
            """# Task State\n\n```yaml\ntask: TASK-001\nstatus: IMPLEMENTING\nrevision: 5\nstage_round: 2\nrun_id: run-impl-1\nrun_status: running\nrun_attempt: 1\nrework_round: 0\nauto_replan_count: 0\nagent_failure_count: 0\ncurrent_role: implementer\ncurrent_participant: impl-a\nwriter_session: run-impl-1\nassignments:\n  planner: planner-a\n  implementer: impl-a\n  reviewer: reviewer-a\nplan_version: 1\ncode_delivery_ref: null\n```\n""",
            encoding="utf-8",
        )

    def run_cli(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def implementation_done(self, participant="impl-a", run_id="run-impl-1", revision="5", expected=0):
        return self.run_cli(
            "implementation-done", "--task", "TASK-001", "--expected-revision", revision,
            "--participant-id", participant, "--run-id", run_id,
            "--execution", str(self.task / "execution.md"),
            "--delivery-ref", "execution.md#delivery-1",
            "--progress", str(self.task / "progress.md"), expected=expected,
        )

    def test_implementation_done_requires_same_participant_and_run(self):
        before = self.state_path.read_bytes()
        self.implementation_done(participant="other", expected=3)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.implementation_done(run_id="run-other", expected=3)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_implementation_done_moves_to_reviewer_and_keeps_run_lease(self):
        self.implementation_done()
        state = self.state_path.read_text(encoding="utf-8")
        self.assertIn("status: REVIEWING", state)
        self.assertIn("current_role: reviewer", state)
        self.assertIn("current_participant: reviewer-a", state)
        self.assertIn("run_id: run-impl-1", state)
        self.assertIn("writer_session: run-impl-1", state)
        self.assertIn('code_delivery_ref: "execution.md#delivery-1"', state)

    def test_stale_revision_is_all_or_nothing(self):
        before = self.state_path.read_bytes()
        self.implementation_done(revision="4", expected=3)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_plan_done_rejects_missing_plan(self):
        self.state_path.write_text(self.state_path.read_text().replace("status: IMPLEMENTING", "status: PLANNING").replace("current_role: implementer", "current_role: planner").replace("current_participant: impl-a", "current_participant: planner-a").replace("run_id: run-impl-1", "run_id: null").replace("writer_session: run-impl-1", "writer_session: null"), encoding="utf-8")
        (self.task / "plan.md").unlink()
        self.run_cli(
            "plan-done", "--task", "TASK-001", "--expected-revision", "5",
            "--participant-id", "planner-a", "--plan", str(self.task / "plan.md"),
            "--approval-ref", "approval.md", "--progress", str(self.task / "progress.md"), expected=2,
        )

    def test_report_done_requires_matching_persisted_reviewer_evidence(self):
        self.state_path.write_text(
            self.state_path.read_text(encoding="utf-8")
            .replace("status: IMPLEMENTING", "status: REPORTING")
            .replace("revision: 5", "revision: 8")
            .replace("current_role: implementer", "current_role: planner")
            .replace("current_participant: impl-a", "current_participant: planner-a")
            .replace("writer_session: run-impl-1", "writer_session: null")
            .replace(
                "code_delivery_ref: null",
                "code_delivery_ref: execution.md#delivery-1\nreview_ref: review.md\n"
                "delivery_id: delivery-1\nreporting:\n  phase: active\n  wake_key: wake-8",
            ),
            encoding="utf-8",
        )
        before = self.state_path.read_bytes()
        (self.task / "other-review.md").write_text("different review evidence\n", encoding="utf-8")
        self.run_cli(
            "report-done", "--task", "TASK-001", "--expected-revision", "8",
            "--participant-id", "planner-a", "--wake-key", "wake-8",
            "--review-delivery-id", "delivery-1", "--report", str(self.task / "report.md"),
            "--review-ref", "other-review.md", expected=3,
        )
        self.assertEqual(self.state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
