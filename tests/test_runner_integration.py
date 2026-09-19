import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


runner_module = load_runtime_module("runner")
fake_module = load_runtime_module("fake", "adapters/fake.py")
notifications = load_runtime_module("notifications")


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
status: IMPLEMENTING
revision: 1
stage_round: 1
run_id: null
run_status: idle
run_attempt: 0
rework_round: 0
auto_replan_count: 0
agent_failure_count: 0
runtime_snapshot_ref: null
current_role: implementer
current_participant: implementer-a
writer_session: null
execution: idle
```
"""


class RunnerIntegrationTests(unittest.TestCase):
    def test_fake_runner_advances_background_stages_to_foreground_reporting(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            (task / "STATE.md").write_text(STATE, encoding="utf-8")
            registry = runner_module.ProjectRegistry(repo / "projects.json")
            registry.register(repo)
            notifier = notifications.RecordingNotifier()
            adapter = fake_module.FakeAdapter(sys.executable, sleep=0)
            runner = runner_module.RelayRunner(registry, lambda _: adapter, notifier)
            for _ in range(20):
                runner.run_once()
                time.sleep(0.02)
            state = (task / "STATE.md").read_text(encoding="utf-8")
            self.assertIn("status: REPORTING", state)
            self.assertNotIn("status: DONE", state)

    def test_broken_project_does_not_stop_later_registered_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = root / "broken"
            broken.mkdir()
            healthy = root / "healthy"
            task = healthy / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (healthy / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            (task / "STATE.md").write_text(STATE, encoding="utf-8")
            registry = runner_module.ProjectRegistry(root / "projects.json")
            registry.register(broken)
            registry.register(healthy)
            adapter = fake_module.FakeAdapter(sys.executable, sleep=0.1)

            def factory(repo):
                if repo == broken.resolve():
                    raise PermissionError("external volume denied")
                return adapter

            notifier = notifications.RecordingNotifier()
            runner = runner_module.RelayRunner(registry, factory, notifier)
            decisions = runner.run_once()
            self.assertEqual(decisions[0].action, "project_error")
            self.assertIn("external volume denied", decisions[0].detail)
            self.assertTrue(decisions[0].report)
            self.assertEqual(decisions[1].action, "started")
            time.sleep(0.15)
            repeated = runner.run_once()
            self.assertFalse(repeated[0].report)
            self.assertEqual(len([event for event in notifier.events if event["state"] == "PROJECT_ERROR"]), 1)


if __name__ == "__main__":
    unittest.main()
