"""Non-focus-stealing notification implementations."""

from __future__ import annotations

import json
import subprocess
from typing import Protocol


class Notifier(Protocol):
    def notify(self, project: str, task_id: str, state: str, reason: str) -> None: ...


class RecordingNotifier:
    def __init__(self):
        self.events: list[dict[str, str]] = []

    def notify(self, project: str, task_id: str, state: str, reason: str) -> None:
        self.events.append({"project": project, "task_id": task_id, "state": state, "reason": reason})


class MacOSNotifier:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def notify(self, project: str, task_id: str, state: str, reason: str) -> None:
        title = f"Agent Relay · {state}"
        body = f"{project} / {task_id}: {reason}"
        script = "display notification " + json.dumps(body) + " with title " + json.dumps(title)
        self.runner(["osascript", "-e", script], check=False, capture_output=True, text=True)
