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


@dataclass(frozen=True)
class StageEvidence:
    progress_ref: str
    delivery_ref: str | None = None
    review_ref: str | None = None
    report_ref: str | None = None


@dataclass(frozen=True)
class RunFinalization:
    action: str
    task_id: str
    run_id: str
    input_revision: int
    output_revision: int
    idempotent_replay: bool = False


def classify_run_result(
    start_status: str, current_status: str, exit_code: int, termination_reason: str
) -> str:
    if current_status != start_status:
        return "completed"
    if termination_reason == "timeout":
        return "timeout"
    if termination_reason == "interrupted":
        return "interrupted"
    if exit_code == 0:
        return "protocol_failure"
    return "agent_failure"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _lock_path(repo: Path) -> Path:
    git_path = repo / ".git"
    if git_path.is_dir():
        return git_path / "agent-relay-auto.lock"
    return repo / ".agent-relay-auto.lock"


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

_ROLE_EVENTS = {
    ("planner", "plan_completed"): ("PLANNING", "IMPLEMENTING", "implementer"),
    ("implementer", "implementation_completed"): ("IMPLEMENTING", "REVIEWING", "reviewer"),
    ("reviewer", "review_passed"): ("REVIEWING", "REPORTING", "planner"),
    ("reviewer", "changes_requested"): ("REVIEWING", "IMPLEMENTING", "implementer"),
    ("reviewer", "replan_required"): ("REVIEWING", "PLANNING", "planner"),
    ("planner", "report_completed"): ("REPORTING", "DONE", "planner"),
}


class StateStore:
    def __init__(self, repo: Path, max_agent_retries: int = 1):
        self.repo = Path(repo).resolve()
        self.max_agent_retries = max_agent_retries

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

    def complete_stage(
        self,
        task_id: str,
        expected_revision: int,
        role: str,
        participant_id: str,
        run_id: str | None,
        event: str,
        evidence: StageEvidence,
    ) -> TransitionResult:
        rule = _ROLE_EVENTS.get((role, event))
        if rule is None:
            raise TransitionError(f"role {role} cannot submit event {event}")
        expected_status, new_status, next_role = rule
        with _state_lock(self.repo, f"complete-stage:{event}"):
            path, text, state = self._read_task(task_id)
            if state.get("revision") != expected_revision:
                raise RevisionConflict(
                    f"revision mismatch: expected {expected_revision}, actual {state.get('revision')}"
                )
            if state.get("status") != expected_status:
                raise TransitionError(f"illegal transition: {state.get('status')} + {event}")
            if state.get("current_role") != role or state.get("current_participant") != participant_id:
                raise TransitionError(
                    f"role identity mismatch: expected {role}/{participant_id}, "
                    f"actual {state.get('current_role')}/{state.get('current_participant')}"
                )
            if role in {"implementer", "reviewer"}:
                if not run_id or state.get("run_id") != run_id or state.get("writer_session") != run_id:
                    raise TransitionError(
                        f"run identity mismatch: expected {run_id}, actual {state.get('run_id')}"
                    )
            elif run_id is not None:
                raise TransitionError("foreground planner completion cannot carry a background run ID")
            assignments = state.get("assignments") if isinstance(state.get("assignments"), Mapping) else {}
            next_participant = assignments.get(next_role) or (
                participant_id if next_role == role else f"{next_role}-main"
            )
            values: dict[tuple[str, ...], object] = {
                ("status",): new_status,
                ("previous_role",): role,
                ("previous_participant",): participant_id,
                ("previous_progress",): evidence.progress_ref,
                ("current_role",): next_role,
                ("current_participant",): next_participant,
                ("stage_round",): int(state.get("stage_round", 1)) + 1,
                ("revision",): expected_revision + 1,
                ("updated_at",): now_iso(),
            }
            if evidence.delivery_ref is not None:
                values[("code_delivery_ref",)] = evidence.delivery_ref
            if evidence.review_ref is not None:
                values[("review_ref",)] = evidence.review_ref
            if evidence.report_ref is not None:
                values[("report_ref",)] = evidence.report_ref
            if event == "changes_requested":
                values[("rework_round",)] = int(state.get("rework_round", 0)) + 1
            if event == "replan_required":
                values[("auto_replan_count",)] = int(state.get("auto_replan_count", 0)) + 1
            if role == "planner":
                values[("writer_session",)] = None
                values[("execution",)] = "idle"
            self._write_state(path, text, values)
            return TransitionResult(task_id, expected_status, new_status, expected_revision, expected_revision + 1)

    def complete_report(
        self,
        task_id: str,
        expected_revision: int,
        participant_id: str,
        wake_key: str,
        review_delivery_id: str,
        review_ref: str,
        report_ref: str,
    ) -> TransitionResult:
        """Finish REPORTING only for the registered foreground Planner wake."""
        with _state_lock(self.repo, "complete-report"):
            path, text, state = self._read_task(task_id)
            if state.get("task") != task_id:
                raise TransitionError(
                    f"task identity mismatch: expected {task_id}, actual {state.get('task')}"
                )
            if state.get("revision") != expected_revision:
                raise RevisionConflict(
                    f"revision mismatch: expected {expected_revision}, actual {state.get('revision')}"
                )
            if state.get("status") != "REPORTING":
                raise TransitionError(f"illegal transition: {state.get('status')} + report_completed")
            if "runner" in participant_id.lower():
                raise TransitionError("Runner identity cannot complete Planner reporting")
            assignments = state.get("assignments") if isinstance(state.get("assignments"), Mapping) else {}
            assigned_planner = assignments.get("planner")
            if (
                state.get("current_role") != "planner"
                or state.get("current_participant") != participant_id
                or assigned_planner != participant_id
            ):
                raise TransitionError(
                    "Planner identity mismatch: "
                    f"expected planner/{assigned_planner}, actual "
                    f"{state.get('current_role')}/{state.get('current_participant')}"
                )
            reporting = state.get("reporting") if isinstance(state.get("reporting"), Mapping) else {}
            if reporting.get("wake_key") != wake_key:
                raise TransitionError(
                    f"wake_key mismatch: expected {reporting.get('wake_key')}, actual {wake_key}"
                )
            if state.get("delivery_id") != review_delivery_id:
                raise TransitionError(
                    "review delivery_id mismatch: "
                    f"expected {state.get('delivery_id')}, actual {review_delivery_id}"
                )
            if not state.get("review_ref") or state.get("review_ref") != review_ref:
                raise TransitionError(
                    f"review_ref mismatch: expected {state.get('review_ref')}, actual {review_ref}"
                )

            project_path = self._project_path()
            project_text = project_path.read_text(encoding="utf-8")
            project = parse_fenced_yaml(project_text)
            tasks = project.get("tasks") if isinstance(project.get("tasks"), Mapping) else {}
            active = [item for item in tasks.get("active", []) if item != task_id]
            completed = list(tasks.get("completed", []))
            if task_id not in completed:
                completed.append(task_id)
            completed_reporting = dict(reporting)
            completed_reporting["phase"] = "completed"
            self._write_state(
                path,
                text,
                {
                    ("status",): "DONE",
                    ("previous_role",): "planner",
                    ("previous_participant",): participant_id,
                    ("previous_progress",): report_ref,
                    ("report_ref",): report_ref,
                    ("reporting",): completed_reporting,
                    ("current_role",): "planner",
                    ("current_participant",): participant_id,
                    ("run_id",): None,
                    ("run_status",): "idle",
                    ("writer_session",): None,
                    ("execution",): "idle",
                    ("stage_round",): int(state.get("stage_round", 1)) + 1,
                    ("revision",): expected_revision + 1,
                    ("updated_at",): now_iso(),
                },
            )

            self._write_state(
                project_path,
                project_text,
                {
                    ("active_task",): None if project.get("active_task") == task_id else project.get("active_task"),
                    ("tasks", "active"): active,
                    ("tasks", "completed"): completed,
                },
            )
            return TransitionResult(task_id, "REPORTING", "DONE", expected_revision, expected_revision + 1)

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

    def finish_run(
        self,
        task_id: str,
        run_id: str,
        exit_code: int,
        start_status: str | None = None,
        termination_reason: str = "exit",
    ) -> RunFinalization:
        with _state_lock(self.repo, "finish-run"):
            path, text, state = self._read_task(task_id)
            input_revision = int(state.get("revision"))
            if state.get("last_finished_run_id") == run_id:
                return RunFinalization(
                    str(state.get("last_run_action") or "already_finalized"),
                    task_id,
                    run_id,
                    input_revision,
                    input_revision,
                    True,
                )
            if state.get("run_id") != run_id:
                raise StateStoreError(
                    f"run identity mismatch: expected {run_id}, actual {state.get('run_id')}"
                )
            current_status = str(state.get("status"))
            # The legacy three-argument call means the caller already handled
            # the role protocol and only needs the lease released.
            result = (
                "completed"
                if start_status is None
                else classify_run_result(start_status, current_status, exit_code, termination_reason)
            )
            failures = int(state.get("agent_failure_count", 0))
            action = "completed"
            values: dict[tuple[str, ...], object] = {
                ("run_status",): "finished",
                ("run_exit_code",): exit_code,
                ("last_finished_run_id",): run_id,
                ("last_run_result",): result,
                ("run_id",): None,
                ("writer_session",): None,
            }
            if result != "completed":
                failures += 1
                values[("agent_failure_count",)] = failures
                if failures <= self.max_agent_retries:
                    action = "retry"
                    values[("run_status",)] = "idle"
                else:
                    action = "blocked"
                    values[("status",)] = "BLOCKED"
                    detail = "no_handoff" if result == "protocol_failure" else result
                    values[("blocked_reason",)] = f"{result}: {detail}"
                    values[("unblock_condition",)] = "inspect run logs and resume or replace the assigned Agent"
            values[("last_run_action",)] = action
            output_revision = input_revision + 1
            values[("revision",)] = output_revision
            values[("updated_at",)] = now_iso()
            self._write_state(path, text, values)
            return RunFinalization(action, task_id, run_id, input_revision, output_revision)
