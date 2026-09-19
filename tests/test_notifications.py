import json
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


notifications = load_runtime_module("notifications")


class NotificationsTests(unittest.TestCase):
    def test_recording_notifier_does_not_steal_focus(self):
        notifier = notifications.RecordingNotifier()
        notifier.notify("demo", "TASK-001", "WAITING_USER", "question")
        self.assertEqual(notifier.events[0]["state"], "WAITING_USER")

    def test_notification_journal_emits_once_per_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            journal = notifications.NotificationJournal(repo)
            first = notifications.NotificationKey("demo", "TASK-001", "WAITING_FOREGROUND_PLANNER", 4)
            self.assertTrue(journal.emit_once(first, str(repo / "STATE.md")))
            self.assertFalse(journal.emit_once(first, str(repo / "STATE.md")))
            self.assertTrue(journal.emit_once(
                notifications.NotificationKey("demo", "TASK-001", "WAITING_FOREGROUND_PLANNER", 5),
                str(repo / "STATE.md"),
            ))
            records = [json.loads(line) for line in journal.path.read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["revision"], 4)
            self.assertEqual(records[0]["state_path"], str(repo / "STATE.md"))


if __name__ == "__main__":
    unittest.main()
