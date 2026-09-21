"""Non-focus-stealing notification implementations."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


class Notifier(Protocol):
    def notify(
        self, project: str, task_id: str, state: str, reason: str,
        revision: int = 0, state_path: str = "",
    ) -> None: ...


@dataclass(frozen=True)
class NotificationKey:
    project: str
    task_id: str
    state: str
    revision: int


class NotificationJournal:
    def __init__(self, repo: Path):
        self.path = Path(repo) / ".agent-relay-auto/notifications.jsonl"

    def emit_once(self, key: NotificationKey, state_path: str) -> bool:
        existing: set[tuple[object, ...]] = set()
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    existing.add((item["project"], item["task_id"], item["state"], item["revision"]))
        identity = (key.project, key.task_id, key.state, key.revision)
        if identity in existing:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {**asdict(key), "state_path": state_path}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


class RecordingNotifier:
    def __init__(self):
        self.events: list[dict[str, str]] = []

    def notify(
        self, project: str, task_id: str, state: str, reason: str,
        revision: int = 0, state_path: str = "",
    ) -> None:
        self.events.append({
            "project": project, "task_id": task_id, "state": state, "reason": reason,
            "revision": revision, "state_path": state_path,
        })


class MacOSNotifier:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def notify(
        self, project: str, task_id: str, state: str, reason: str,
        revision: int = 0, state_path: str = "",
    ) -> None:
        title = f"Agent Relay Auto · {state}"
        body = f"{project} / {task_id}: {reason}"
        script = "display notification " + json.dumps(body) + " with title " + json.dumps(title)
        try:
            self.runner(["osascript", "-e", script], check=False, capture_output=True, text=True)
        except FileNotFoundError:
            # CI and non-macOS hosts do not provide osascript. Notifications are
            # advisory; a missing desktop notifier must not break the workflow.
            return
