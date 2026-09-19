import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.shared.agent_relay_runtime_loader import load_runtime_module


supervisor_module = load_runtime_module("supervisor")
fake_module = load_runtime_module("fake", "adapters/fake.py")


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
```
"""


class SupervisorTests(unittest.TestCase):
    @staticmethod
    def implementing_state():
        return STATE.replace("status: PLANNING", "status: IMPLEMENTING").replace(
            "current_role: planner", "current_role: implementer"
        ).replace("current_participant: planner-a", "current_participant: impl-a")

    def test_same_revision_starts_only_one_process(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            (task / "STATE.md").write_text(self.implementing_state(), encoding="utf-8")
            fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
            adapter = fake_module.FakeAdapter(sys.executable, fixture, sleep=0.25)
            supervisor = supervisor_module.ProjectSupervisor(repo, adapter)
            first = supervisor.tick()
            second = supervisor.tick()
            self.assertEqual(first.action, "started")
            self.assertEqual(second.action, "already_running")
            time.sleep(0.35)
            supervisor.tick()

    def test_changes_requested_is_dispatched_to_implementer(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            state = STATE.replace("status: PLANNING", "status: CHANGES_REQUESTED").replace(
                "current_role: planner", "current_role: implementer"
            ).replace("current_participant: planner-a", "current_participant: impl-a")
            (task / "STATE.md").write_text(state, encoding="utf-8")
            fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
            adapter = fake_module.FakeAdapter(sys.executable, fixture, sleep=0.1)
            supervisor = supervisor_module.ProjectSupervisor(repo, adapter)
            decision = supervisor.tick()
            self.assertEqual(decision.action, "started")
            time.sleep(0.15)
            supervisor.tick()

    def test_process_exit_is_finished_and_output_is_persisted_without_adapter_callback(self):
        class AdapterWithoutCallback:
            def capabilities(self):
                return SimpleNamespace(noninteractive=True)

            def build_command(self, request):
                fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
                return (sys.executable, str(fixture))

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            (task / "STATE.md").write_text(self.implementing_state(), encoding="utf-8")
            supervisor = supervisor_module.ProjectSupervisor(repo, AdapterWithoutCallback())
            started = supervisor.tick()
            deadline = time.time() + 3
            finished = None
            while time.time() < deadline:
                finished = supervisor.tick()
                if finished.action == "finished":
                    break
                time.sleep(0.01)
            self.assertEqual(finished.action, "finished")
            state = (task / "STATE.md").read_text(encoding="utf-8")
            self.assertIn("run_status: finished", state)
            self.assertIn("run_id: null", state)
            stdout_log = repo / ".agent-relay-auto/runs/TASK-001" / started.run_id / "stdout.log"
            self.assertIn("fake-agent-finish", stdout_log.read_text(encoding="utf-8"))

    def test_planning_waits_for_foreground_planner_without_starting_process(self):
        class NeverStartAdapter:
            def capabilities(self):
                raise AssertionError("foreground planner must not inspect adapter capabilities")

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            (task / "STATE.md").write_text(STATE, encoding="utf-8")
            decision = supervisor_module.ProjectSupervisor(repo, NeverStartAdapter()).tick()
            self.assertEqual(decision.action, "waiting_foreground_planner")
            self.assertEqual(decision.detail, "PLANNING")

    def test_reporting_waits_for_foreground_planner_without_starting_process(self):
        class NeverStartAdapter:
            def capabilities(self):
                raise AssertionError("foreground planner must not inspect adapter capabilities")

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            reporting = STATE.replace("status: PLANNING", "status: REPORTING")
            (task / "STATE.md").write_text(reporting, encoding="utf-8")
            decision = supervisor_module.ProjectSupervisor(repo, NeverStartAdapter()).tick()
            self.assertEqual(decision.action, "waiting_foreground_planner")
            self.assertEqual(decision.detail, "REPORTING")


if __name__ == "__main__":
    unittest.main()
