import json
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


planner_channel = load_runtime_module("planner_channel")


class PlannerChannelTests(unittest.TestCase):
    def test_round_trip_preserves_exact_conversation_and_project(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            channel = planner_channel.PlannerChannel(
                "planner-codex", "codex", "thr_123", str(repo), "2026-09-20T00:00:00Z"
            )
            store = planner_channel.PlannerChannelStore(repo)
            store.save(channel)

            self.assertEqual(store.load(), channel)
            payload = json.loads((repo / ".agent-relay-auto/planner-channel.json").read_text())
            self.assertEqual(payload["conversation_id"], "thr_123")

    def test_channel_rejects_repository_move(self):
        channel = planner_channel.PlannerChannel(
            "planner-codex", "codex", "thr_1", "/old/repo", "2026-09-20T00:00:00Z"
        )
        with self.assertRaisesRegex(planner_channel.PlannerChannelError, "project_path"):
            channel.validate_for(Path("/new/repo"))

    def test_channel_rejects_empty_identity_and_unsupported_tool(self):
        with self.assertRaisesRegex(planner_channel.PlannerChannelError, "conversation_id"):
            planner_channel.PlannerChannel("planner", "codex", "", "/repo", "now")
        with self.assertRaisesRegex(planner_channel.PlannerChannelError, "tool"):
            planner_channel.PlannerChannel("planner", "cursor", "chat", "/repo", "now")

    def test_missing_store_returns_none_and_malformed_store_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            store = planner_channel.PlannerChannelStore(repo)
            self.assertIsNone(store.load())
            path = repo / ".agent-relay-auto/planner-channel.json"
            path.parent.mkdir(parents=True)
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(planner_channel.PlannerChannelError):
                store.load()


if __name__ == "__main__":
    unittest.main()
