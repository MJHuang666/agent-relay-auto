import unittest

from tests.shared.agent_relay_runtime_loader import load_runtime_module


notifications = load_runtime_module("notifications")


class NotificationsTests(unittest.TestCase):
    def test_recording_notifier_does_not_steal_focus(self):
        notifier = notifications.RecordingNotifier()
        notifier.notify("demo", "TASK-001", "WAITING_USER", "question")
        self.assertEqual(notifier.events[0]["state"], "WAITING_USER")


if __name__ == "__main__":
    unittest.main()
