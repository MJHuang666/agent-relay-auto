"""Locked, revision-checked state mutations for the automated Relay."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _sibling(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"agent_relay_runtime_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runtime module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from .markdown_state import atomic_write_text, parse_fenced_yaml, set_yaml_value
except ImportError:
    _markdown_state = _sibling("markdown_state")
    atomic_write_text = _markdown_state.atomic_write_text
    parse_fenced_yaml = _markdown_state.parse_fenced_yaml
    set_yaml_value = _markdown_state.set_yaml_value


class StateStoreError(RuntimeError):
    pass


class RevisionConflict(StateStoreError):
    pass


class TransitionError(StateStoreError):
    pass


class StateLockError(StateStoreError):
    pass


@dataclass(frozen=True)
class ClaimKey:
    task_id: str
    expected_revision: int
    participant_id: str
    stage_round: int

    def as_text(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class TransitionResult:
    task_id: str
    old_status: str
    new_status: str
    input_revision: int
    output_revision: int
    idempotent_replay: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _lock_path(repo: Path) -> Path:
    git_path = repo / ".git"
    if git_path.is_dir():
        return git_path / "agent-relay.lock"
    return repo / ".agent-relay.lock"


@contextmanager
def _state_lock(repo: Path, operation: str):
    path = _lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "transaction_id": str(uuid.uuid4()),
        "operation": operation,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "created_at": now_iso(),
    }
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise StateLockError(f"lock already exists: {path}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield metadata
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


_TRANSITIONS = {
    ("PLANNING", "plan_completed"): "IMPLEMENTING",
    ("IMPLEMENTING", "implementation_completed"): "REVIEWING",
    ("REVIEWING", "review_passed"): "REPORTING",
    ("REVIEWING", "changes_requested"): "IMPLEMENTING",
    ("REVIEWING", "replan_required"): "PLANNING",
    ("REPORTING", "report_completed"): "DONE",
}


class StateStore:
    def __init__(self, repo: Path):
        self.repo = Path(repo).resolve()

    def _project_path(self) -> Path:
        return self.repo / "docs/agent/PROJECT_STATUS.md"

    def _task_path(self, task_id: str) -> Path:
        return self.repo / "docs/agent/tasks" / task_id / "STATE.md"

    def _read_task(self, task_id: str) -> tuple[Path, str, dict[str, Any]]:
        path = self._task_path(task_id)
        if not path.is_file():
            raise StateStoreError(f"task state is missing: {path}")
        text = path.read_text(encoding="utf-8")
        return path, text, parse_fenced_yaml(text)

    def _write_state(self, path: Path, text: str, values: Mapping[tuple[str, ...], object]) -> None:
        updated = text
        for key_path, value in values.items():
            updated = set_yaml_value(updated, key_path, value)
        atomic_write_text(path, updated)

    def transition(
        self,
        task_id: str,
        expected_revision: int,
        event: str,
        payload: Mapping[str, object],
    ) -> TransitionResult:
        with _state_lock(self.repo, f"transition:{event}"):
            path, text, state = self._read_task(task_id)
            actual = state.get("revision")
            if actual != expected_revision:
                raise RevisionConflict(f"revision mismatch: expected {expected_revision}, actual {actual}")
            old_status = str(state.get("status"))
            new_status = _TRANSITIONS.get((old_status, event))
            if new_status is None:
                raise TransitionError(f"illegal transition: {old_status} + {event}")
            values: dict[tuple[str, ...], object] = {
                ("status",): new_status,
                ("revision",): expected_revision + 1,
                ("updated_at",): now_iso(),
            }
            if event == "changes_requested":
                values[("rework_round",)] = int(state.get("rework_round", 0)) + 1
            if event == "replan_required":
                values[("auto_replan_count",)] = int(state.get("auto_replan_count", 0)) + 1
            if "current_role" in payload:
                values[("current_role",)] = payload["current_role"]
            self._write_state(path, text, values)
            return TransitionResult(task_id, old_status, new_status, expected_revision, expected_revision + 1)

    def claim(self, key: ClaimKey, run_id: str) -> TransitionResult:
        with _state_lock(self.repo, "claim"):
            path, text, state = self._read_task(key.task_id)
            actual = state.get("revision")
            claim_key = key.as_text()
            if state.get("last_claim_key") == claim_key and state.get("run_id") == run_id:
                status = str(state.get("status"))
                return TransitionResult(
                    key.task_id,
                    status,
                    status,
                    key.expected_revision,
                    key.expected_revision + 1,
                    True,
                )
            if actual != key.expected_revision:
                raise RevisionConflict(f"revision mismatch: expected {key.expected_revision}, actual {actual}")
            if state.get("run_id") and state.get("run_status") in {"starting", "running"}:
                raise StateStoreError(f"task already has an active run: {state.get('run_id')}")
            new_revision = key.expected_revision + 1
            self._write_state(
                path,
                text,
                {
                    ("run_id",): run_id,
                    ("run_status",): "running",
                    ("run_attempt",): int(state.get("run_attempt", 0)) + 1,
                    ("last_claim_key",): claim_key,
                    ("writer_session",): run_id,
                    ("revision",): new_revision,
                    ("updated_at",): now_iso(),
                },
            )
            status = str(state.get("status"))
            return TransitionResult(key.task_id, status, status, key.expected_revision, new_revision)
