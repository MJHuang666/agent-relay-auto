import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


fake_module = load_runtime_module("hybrid_fake", "adapters/fake.py")
markdown = load_runtime_module("hybrid_markdown", "markdown_state.py")
runner_module = load_runtime_module("hybrid_runner", "runner.py")
RELAY = Path(__file__).resolve().parents[1] / "shared/.agents/skills/agent-relay-auto/scripts/relay_state.py"


class HybridRelayE2ETests(unittest.TestCase):
    def run_cli(self, repo, *args):
        result = subprocess.run(
            [sys.executable, str(RELAY), "--repo", str(repo), *map(str, args)],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def read_state(self, task):
        return markdown.parse_fenced_yaml((task / "STATE.md").read_text(encoding="utf-8"))

    def drain_until(self, runner, task, status, timeout=4, settled=False):
        deadline = time.time() + timeout
        while time.time() < deadline:
            runner.run_once()
            state = self.read_state(task)
            if state["status"] == status and (not settled or state.get("run_id") is None):
                return
            time.sleep(0.01)
        self.fail(f"workflow did not reach {status}: {self.read_state(task)}")

    def test_foreground_planner_background_roles_foreground_report_reaches_done(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(
                "# Project\n\n```yaml\nproject: E2E\nactive_task: TASK-001\ntasks:\n"
                "  active: [\"TASK-001\"]\n  queued: []\n  blocked: []\n  completed: []\n```\n"
            )
            (task / "STATE.md").write_text(
                "# State\n\n```yaml\ntask: TASK-001\nstatus: PLANNING\nrevision: 1\n"
                "stage_round: 1\nrun_id: null\nrun_status: idle\nrun_attempt: 0\n"
                "rework_round: 0\nauto_replan_count: 0\nagent_failure_count: 0\n"
                "current_role: planner\ncurrent_participant: planner-a\nwriter_session: null\n"
                "plan_version: 1\nsubagent_policy: DO_NOT_USE\nassignments:\n"
                "  planner: planner-a\n  implementer: impl-a\n  reviewer: reviewer-a\n```\n"
            )
            requirement = task / "requirement.md"
            plan = task / "plan.md"
            progress = task / "progress-planner.md"
            requirement.write_text("approved requirement\n")
            plan.write_text("approved plan\n")
            progress.write_text("planning completed\n")
            registry = runner_module.ProjectRegistry(repo / "projects.json")
            registry.register(repo)
            runner = runner_module.RelayRunner(
                registry, lambda _: fake_module.FakeAdapter(sys.executable, sleep=0)
            )

            self.assertEqual(runner.run_once()[0].action, "waiting_foreground_planner")
            self.run_cli(
                repo, "plan-done", "--task", "TASK-001", "--expected-revision", "1",
                "--participant-id", "planner-a", "--plan", plan,
                "--approval-ref", "requirement.md", "--progress", progress,
            )
            self.drain_until(runner, task, "REVIEWING")
            self.drain_until(runner, task, "REPORTING", settled=True)
            self.assertEqual(runner.run_once()[0].action, "waiting_foreground_planner")

            roles = []
            for metadata in (repo / ".agent-relay-auto/runs/TASK-001").glob("*/metadata.json"):
                import json
                roles.append(json.loads(metadata.read_text())["role"])
            self.assertEqual(sorted(roles), ["implementer", "reviewer"])

            report = task / "final-report.md"
            report.write_text(
                "Goal\nDelivery\nTests\nReviewer evidence\nLimitations\nUsage\n"
                "Not executed: merge, push, release, deploy\n"
            )
            state = self.read_state(task)
            self.run_cli(
                repo, "report-done", "--task", "TASK-001",
                "--expected-revision", state["revision"], "--participant-id", "planner-a",
                "--report", report, "--review-ref", state["review_ref"],
            )
            self.assertEqual(self.read_state(task)["status"], "DONE")
            for forbidden in ("MERGE", "RELEASE", "DEPLOY"):
                self.assertFalse((repo / forbidden).exists())

    def test_recreated_runner_consumes_durable_worker_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(
                "# Project\n\n```yaml\nactive_task: TASK-001\ntasks:\n  active: [\"TASK-001\"]\n```\n"
            )
            (task / "STATE.md").write_text(
                "# State\n\n```yaml\ntask: TASK-001\nstatus: IMPLEMENTING\nrevision: 1\n"
                "stage_round: 1\nrun_id: null\nrun_status: idle\nrun_attempt: 0\n"
                "agent_failure_count: 0\ncurrent_role: implementer\ncurrent_participant: impl-a\n"
                "writer_session: null\nplan_version: 1\nsubagent_policy: DO_NOT_USE\nassignments:\n"
                "  planner: planner-a\n  implementer: impl-a\n  reviewer: reviewer-a\n```\n"
            )
            registry = runner_module.ProjectRegistry(repo / "projects.json")
            registry.register(repo)
            first = runner_module.RelayRunner(
                registry, lambda _: fake_module.FakeAdapter(sys.executable, sleep=0.1)
            )
            self.assertEqual(first.run_once()[0].action, "started")
            old_managed = next(iter(first.supervisors.values()))._active["TASK-001"]
            second = runner_module.RelayRunner(
                registry, lambda _: fake_module.FakeAdapter(sys.executable, sleep=0.1)
            )
            deadline = time.time() + 4
            while time.time() < deadline:
                decision = second.run_once()[0]
                if decision.action == "finished":
                    break
                time.sleep(0.01)
            self.assertEqual(decision.action, "finished")
            old_managed.process.wait(timeout=1)
            self.assertEqual(self.read_state(task)["status"], "REVIEWING")


if __name__ == "__main__":
    unittest.main()
