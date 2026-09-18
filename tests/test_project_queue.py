import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


queue_module = load_runtime_module("queue")


class ProjectQueueTests(unittest.TestCase):
    def test_waiting_user_active_slot_does_not_activate_queued_task(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs/agent").mkdir(parents=True)
            path = repo / "docs/agent/PROJECT_STATUS.md"
            path.write_text(
                """# Project Status

```yaml
project: Demo
active_task: TASK-001
tasks:
  active: [\"TASK-001\"]
  queued: [\"TASK-002\"]
  blocked: []
  completed: []
```
""",
                encoding="utf-8",
            )
            self.assertIsNone(queue_module.activate_next_queued_task(repo, 1))

    def test_completed_active_task_activates_fifo_next_task(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs/agent").mkdir(parents=True)
            path = repo / "docs/agent/PROJECT_STATUS.md"
            path.write_text(
                """# Project Status

```yaml
project: Demo
active_task: null
tasks:
  active: []
  queued: [\"TASK-002\", \"TASK-003\"]
  blocked: []
  completed: [\"TASK-001\"]
```
""",
                encoding="utf-8",
            )
            self.assertEqual(queue_module.activate_next_queued_task(repo, 1), "TASK-002")
            text = path.read_text(encoding="utf-8")
            self.assertIn('active: ["TASK-002"]', text)
            self.assertIn('queued: ["TASK-003"]', text)


if __name__ == "__main__":
    unittest.main()
