import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


runner_module = load_runtime_module("runner")
fake_module = load_runtime_module("fake", "adapters/fake.py")


class AutomatedRelayE2ETests(unittest.TestCase):
    def test_reviewer_to_planner_reporting_reaches_done_without_git_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            task = repo / "docs/agent/tasks/TASK-001"
            task.mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(
                """# Project Status

```yaml
project: E2E
active_task: TASK-001
tasks:
  active: [\"TASK-001\"]
  queued: []
  blocked: []
  completed: []
```
""",
                encoding="utf-8",
            )
            (task / "STATE.md").write_text(
                """# Task State

```yaml
task: TASK-001
title: E2E
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
current_participant: planner-main
writer_session: null
execution: idle
```
""",
                encoding="utf-8",
            )
            registry = runner_module.ProjectRegistry(repo / "projects.json")
            registry.register(repo)
            runner = runner_module.RelayRunner(registry, lambda _: fake_module.FakeAdapter(sys.executable, sleep=0))
            for _ in range(80):
                runner.run_once()
                time.sleep(0.01)
            self.assertIn("status: DONE", (task / "STATE.md").read_text(encoding="utf-8"))
            self.assertFalse((repo / "MERGE").exists())
            self.assertFalse((repo / "RELEASE").exists())
            self.assertFalse((repo / "DEPLOY").exists())


if __name__ == "__main__":
    unittest.main()
