import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


wake_store = load_runtime_module("wake_store")


class WakeStoreTests(unittest.TestCase):
    def test_wake_key_is_stable_and_latest_event_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            key = wake_store.WakeKey("TASK-001", 18, "planner-codex", "thr_1")
            store = wake_store.WakeEventStore(repo)
            store.append({"wake_key": key.value(), "status": "submitting", "attempt": 1})
            store.append(
                {"wake_key": key.value(), "status": "submitted", "attempt": 1, "receipt_id": "turn_9"}
            )

            self.assertEqual(key.value(), "TASK-001:18:planner-codex:thr_1")
            self.assertEqual(store.latest(key.value())["status"], "submitted")
            self.assertEqual(store.find_submission(key.value())["receipt_id"], "turn_9")

    def test_missing_journal_is_empty_and_malformed_line_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            store = wake_store.WakeEventStore(repo)
            self.assertIsNone(store.latest("missing"))
            path = repo / ".agent-relay-auto/wake-events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text('{"wake_key":"ok","status":"submitted"}\nnot-json\n', encoding="utf-8")
            with self.assertRaises(wake_store.WakeStoreError):
                store.latest("ok")

    def test_append_rejects_missing_wake_key_or_status(self):
        with tempfile.TemporaryDirectory() as directory:
            store = wake_store.WakeEventStore(Path(directory))
            with self.assertRaises(wake_store.WakeStoreError):
                store.append({"status": "submitted"})
            with self.assertRaises(wake_store.WakeStoreError):
                store.append({"wake_key": "wk"})


if __name__ == "__main__":
    unittest.main()
