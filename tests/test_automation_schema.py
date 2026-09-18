import unittest

from tests.shared.agent_relay_runtime_loader import load_runtime_module


schema = load_runtime_module("schema")


class AutomationSchemaTests(unittest.TestCase):
    def test_valid_project_queue_and_legacy_active_mirror(self):
        data = {
            "tasks": {
                "active": ["TASK-001"],
                "queued": ["TASK-002"],
                "blocked": [],
                "completed": [],
            },
            "active_task": "TASK-001",
        }
        queue = schema.validate_project_state(data)
        self.assertEqual(queue.active, ("TASK-001",))
        schema.validate_active_task_mirror(data)

    def test_rejects_multiple_active_tasks_and_mismatched_legacy_mirror(self):
        data = {
            "tasks": {
                "active": ["TASK-001", "TASK-002"],
                "queued": [],
                "blocked": [],
                "completed": [],
            },
            "active_task": "TASK-999",
        }
        with self.assertRaises(schema.SchemaError):
            schema.validate_project_state(data)

    def test_task_runtime_defaults_are_valid(self):
        schema.validate_task_state(
            {
                "task": "TASK-001",
                "status": "IMPLEMENTING",
                "revision": 4,
                "stage_round": 2,
                "run_id": None,
                "run_status": "idle",
                "run_attempt": 0,
                "rework_round": 0,
                "auto_replan_count": 0,
                "agent_failure_count": 0,
                "runtime_snapshot_ref": None,
            }
        )


if __name__ == "__main__":
    unittest.main()
