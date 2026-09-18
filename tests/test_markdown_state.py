import unittest
from pathlib import Path
import tempfile

from tests.shared_dot_agents_skill_loader import load_module


markdown_state = load_module(
    "markdown_state",
    Path(__file__).resolve().parents[1]
    / "shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/markdown_state.py",
)
workflow_state = load_module(
    "workflow_state_compat",
    Path(__file__).resolve().parents[1]
    / "shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py",
)


class MarkdownStateTests(unittest.TestCase):
    def test_round_trip_preserves_markdown_and_reads_inline_task_lists(self):
        text = (
            "# State\n\n"
            "```yaml\n"
            "tasks:\n"
            "  active: [\"TASK-001\"]\n"
            "  queued: [\"TASK-002\"]\n"
            "enabled: true\n"
            "```\n\n"
            "Human notes.\n"
        )
        data = markdown_state.parse_fenced_yaml(text)
        self.assertEqual(data["tasks"]["active"], ["TASK-001"])
        self.assertTrue(data["enabled"])
        updated = markdown_state.set_yaml_value(
            text, ("tasks", "queued"), ["TASK-003"]
        )
        self.assertIn('queued: ["TASK-003"]', updated)
        self.assertTrue(updated.endswith("Human notes.\n"))

    def test_atomic_write_replaces_file_and_creates_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "STATE.md"
            markdown_state.atomic_write_text(path, "hello\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello\n")

    def test_legacy_helper_reads_the_new_inline_array_schema(self):
        text = "# State\n\n```yaml\ntasks:\n  active: [\"TASK-001\"]\n```\n"
        self.assertEqual(
            workflow_state.parse_simple_yaml(text)["tasks"]["active"],
            ["TASK-001"],
        )


if __name__ == "__main__":
    unittest.main()
