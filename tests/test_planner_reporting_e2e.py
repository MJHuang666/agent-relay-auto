import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


runner_module = load_runtime_module("planner_reporting_runner", "runner.py")
channel_module = load_runtime_module("planner_reporting_channel", "planner_channel.py")
base = load_runtime_module("planner_reporting_base", "planner_wake/base.py")
RELAY = Path(__file__).resolve().parents[1] / "shared/.agents/skills/agent-relay-auto/scripts/relay_state.py"


class CompletingPlanner:
    def __init__(self, fail_presentation=False, delay=0):
        self.submission_count = 0
        self.created_conversation_count = 0
        self.presented_conversation_id = None
        self.fail_presentation = fail_presentation
        self.delay = delay

    def submit_report(self, channel, request):
        self.submission_count += 1
        if self.delay:
            time.sleep(self.delay)
        task = request.repo / "docs/agent/tasks" / request.task_id
        report = task / "final-report.md"
        report.write_text(
            "Goal\nDelivery\nTests\nReviewer evidence\nLimitations\nUsage\n"
            "Not executed: merge, push, release, deploy\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable, str(RELAY), "--repo", str(request.repo), "report-done",
                "--task", request.task_id, "--expected-revision", str(request.expected_revision),
                "--participant-id", request.participant_id, "--wake-key", request.wake_key,
                "--review-delivery-id", "delivery-1", "--report", str(report),
                "--review-ref", "review.md",
            ],
            text=True, capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        return base.SubmissionReceipt(
            request.wake_key, channel.tool, channel.conversation_id, "turn-report-1", "submitted"
        )

    def observe(self, receipt):
        return base.ObservationResult("completed")

    def present(self, channel):
        self.presented_conversation_id = channel.conversation_id
        if self.fail_presentation:
            raise RuntimeError("application closed")
        return base.PresentationResult("presented")


class PlannerReportingE2ETests(unittest.TestCase):
    def make_repo(self, root: Path, name="repo", status="REPORTING"):
        repo = root / name
        task = repo / "docs/agent/tasks/TASK-001"
        task.mkdir(parents=True)
        (repo / "docs/agent/PROJECT_STATUS.md").write_text(
            "# Project\n\n```yaml\nactive_task: TASK-001\ntasks:\n"
            '  active: ["TASK-001"]\n  queued: []\n  blocked: []\n  completed: []\n```\n',
            encoding="utf-8",
        )
        (repo / "docs/agent/automation-policy.yaml").write_text("mode: automatic\n", encoding="utf-8")
        (task / "review.md").write_text("Reviewer PASS for delivery-1\n", encoding="utf-8")
        (task / "STATE.md").write_text(
            "# State\n\n```yaml\ntask: TASK-001\nstatus: " + status + "\nrevision: 9\n"
            "stage_round: 3\nrun_id: null\nrun_status: idle\nrun_attempt: 0\n"
            "rework_round: 0\nauto_replan_count: 0\nagent_failure_count: 0\n"
            "runtime_snapshot_ref: null\ncurrent_role: planner\ncurrent_participant: planner-a\n"
            "writer_session: null\nexecution: idle\nreview_ref: review.md\ndelivery_id: delivery-1\n"
            "assignments:\n  planner: planner-a\n  implementer: impl-a\n  reviewer: reviewer-a\n```\n",
            encoding="utf-8",
        )
        channel_module.PlannerChannelStore(repo).save(channel_module.PlannerChannel(
            "planner-a", "codex", f"thread-{name}", str(repo.resolve()), "2026-09-20T00:00:00Z"
        ))
        return repo

    def runner(self, registry, planner):
        return runner_module.RelayRunner(
            registry,
            lambda repo: object(),
            planner_wake_factory=lambda tool: planner,
        )

    def test_reviewer_pass_wakes_original_planner_without_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = self.make_repo(root)
            registry = runner_module.ProjectRegistry(root / "projects.json")
            registry.register(repo)
            planner = CompletingPlanner()
            decision = self.runner(registry, planner).run_once()[0]
            state = (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text(encoding="utf-8")
            self.assertEqual(decision.action, "report_completed")
            self.assertIn("status: DONE", state)
            self.assertEqual(planner.submission_count, 1)
            self.assertEqual(planner.created_conversation_count, 0)
            self.assertEqual(planner.presented_conversation_id, "thread-repo")
            journal = (repo / ".agent-relay-auto/wake-events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("thread-repo", journal)
            self.assertIn("sha256:", journal)

    def test_two_runners_submit_one_wake_for_one_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = self.make_repo(root)
            registry = runner_module.ProjectRegistry(root / "projects.json")
            registry.register(repo)
            planner = CompletingPlanner(delay=0.1)
            runners = [self.runner(registry, planner), self.runner(registry, planner)]
            threads = [threading.Thread(target=runner.run_once) for runner in runners]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(planner.submission_count, 1)
            self.assertIn("status: DONE", (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text())

    def test_done_survives_failed_presentation_and_idle_polling_uses_no_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = self.make_repo(root)
            registry = runner_module.ProjectRegistry(root / "projects.json")
            registry.register(repo)
            planner = CompletingPlanner(fail_presentation=True)
            runner = self.runner(registry, planner)
            runner.run_once()
            runner.run_once()
            self.assertEqual(planner.submission_count, 1)
            self.assertIn("status: DONE", (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text())

            idle_repo = self.make_repo(root, "idle", status="PLANNING")
            idle_registry = runner_module.ProjectRegistry(root / "idle-projects.json")
            idle_registry.register(idle_repo)
            idle_planner = CompletingPlanner()
            idle_runner = self.runner(idle_registry, idle_planner)
            for _ in range(5):
                idle_runner.run_once()
            self.assertEqual(idle_planner.submission_count, 0)

    def test_two_reporting_projects_progress_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repos = [self.make_repo(root, name) for name in ("one", "two")]
            planners = [CompletingPlanner(delay=0.05), CompletingPlanner(delay=0.05)]
            runners = []
            for index, repo in enumerate(repos):
                registry = runner_module.ProjectRegistry(root / f"projects-{index}.json")
                registry.register(repo)
                runners.append(self.runner(registry, planners[index]))
            threads = [threading.Thread(target=runner.run_once) for runner in runners]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([planner.submission_count for planner in planners], [1, 1])
            for repo in repos:
                self.assertIn("status: DONE", (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text())


if __name__ == "__main__":
    unittest.main()
