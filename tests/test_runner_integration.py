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
status: PLANNING
revision: 1
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


class RunnerIntegrationTests(unittest.TestCase):
    def test_fake_runner_advances_all_stages_to_done(self):
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
            self.assertIn("status: DONE", state)


if __name__ == "__main__":
    unittest.main()
