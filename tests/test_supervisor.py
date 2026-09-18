import sys
import tempfile
import time
import unittest
from pathlib import Path

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
    def test_same_revision_starts_only_one_process(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            (task / "STATE.md").write_text(STATE, encoding="utf-8")
            fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
            adapter = fake_module.FakeAdapter(sys.executable, fixture, sleep=0.25)
            supervisor = supervisor_module.ProjectSupervisor(repo, adapter)
            first = supervisor.tick()
            second = supervisor.tick()
            self.assertEqual(first.action, "started")
            self.assertEqual(second.action, "already_running")
            time.sleep(0.35)
            supervisor.tick()


if __name__ == "__main__":
    unittest.main()
