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
current_participant: implementer-main
writer_session: null
execution: idle
```
"""


class CrossProjectConcurrencyTests(unittest.TestCase):
    def test_two_projects_start_without_global_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supervisors = []
            for name in ("one", "two"):
                repo = root / name
                (repo / ".git").mkdir(parents=True)
                task = repo / "docs/agent/tasks/TASK-001"
                task.mkdir(parents=True)
                (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
                (task / "STATE.md").write_text(STATE, encoding="utf-8")
                fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
                supervisors.append(supervisor_module.ProjectSupervisor(repo, fake_module.FakeAdapter(sys.executable, fixture, sleep=0.2)))
            started = time.monotonic()
            self.assertEqual(supervisors[0].tick().action, "started")
            self.assertEqual(supervisors[1].tick().action, "started")
            pending = set(range(len(supervisors)))
            deadline = time.monotonic() + 2
            while pending and time.monotonic() < deadline:
                for index in tuple(pending):
                    if supervisors[index].tick().action not in {"already_running", "started"}:
                        pending.remove(index)
                time.sleep(0.01)
            self.assertFalse(pending)
            self.assertLess(time.monotonic() - started, 0.6)


if __name__ == "__main__":
    unittest.main()
