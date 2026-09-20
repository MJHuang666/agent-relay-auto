"""Append-only local journal for idempotent Planner wake requests."""

from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class WakeStoreError(ValueError):
    """Raised when wake history cannot be trusted."""


@dataclass(frozen=True)
class WakeKey:
    task_id: str
    revision: int
    participant_id: str
    conversation_id: str

    def __post_init__(self) -> None:
        for field in ("task_id", "participant_id", "conversation_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise WakeStoreError(f"{field} must be a non-empty string")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 0:
            raise WakeStoreError("revision must be a non-negative integer")

    def value(self) -> str:
        conversation_hash = hashlib.sha256(self.conversation_id.encode("utf-8")).hexdigest()[:16]
        return f"{self.task_id}:{self.revision}:{self.participant_id}:{conversation_hash}"


class WakeEventStore:
    def __init__(self, repo: Path):
        self.path = Path(repo).resolve() / ".agent-relay-auto/wake-events.jsonl"

    @staticmethod
    def _validated(event: Mapping[str, object]) -> dict[str, object]:
        payload = dict(event)
        for field in ("wake_key", "status"):
            value = payload.get(field)
            if not isinstance(value, str) or not value:
                raise WakeStoreError(f"wake event {field} must be a non-empty string")
        return payload

    def append(self, event: Mapping[str, object]) -> None:
        payload = self._validated(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _events(self) -> tuple[dict[str, object], ...]:
        if not self.path.is_file():
            return ()
        events = []
        try:
            for line_number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise TypeError("event is not an object")
                events.append(self._validated(payload))
        except (OSError, ValueError, TypeError) as error:
            raise WakeStoreError(f"cannot trust {self.path} at line {line_number}: {error}") from error
        return tuple(events)

    def latest(self, wake_key: str) -> dict[str, object] | None:
        matches = [event for event in self._events() if event["wake_key"] == wake_key]
        return matches[-1] if matches else None

    def find_submission(self, wake_key: str) -> dict[str, object] | None:
        matches = [
            event for event in self._events()
            if event["wake_key"] == wake_key and event["status"] in {"submitted", "active", "completed"}
        ]
        return matches[-1] if matches else None
