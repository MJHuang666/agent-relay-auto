"""Validation models for automated Agent Relay Auto project and task state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


class SchemaError(ValueError):
    """Raised when a project or task state violates the Relay schema."""


@dataclass(frozen=True)
class ProjectQueue:
    active: tuple[str, ...]
    queued: tuple[str, ...]
    blocked: tuple[str, ...]
    completed: tuple[str, ...]


_QUEUE_KEYS = ("active", "queued", "blocked", "completed")
_TASK_STATUSES = {
    "QUEUED",
    "INTAKE",
    "PLANNING",
    "IMPLEMENTING",
    "REVIEWING",
    "REPORTING",
    "WAITING_USER",
    "BLOCKED",
    "DONE",
    "CANCELLED",
}
_RUN_STATUSES = {"idle", "starting", "running", "paused", "finished", "unknown"}


def _task_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise SchemaError(f"{field} must be an array")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise SchemaError(f"{field} must contain non-empty task IDs")
    if len(set(result)) != len(result):
        raise SchemaError(f"{field} contains duplicate task IDs")
    return result


def validate_project_state(data: Mapping[str, object]) -> ProjectQueue:
    tasks = data.get("tasks")
    if not isinstance(tasks, Mapping):
        raise SchemaError("tasks must be a mapping")
    values = {key: _task_list(tasks.get(key, []), f"tasks.{key}") for key in _QUEUE_KEYS}
    memberships: dict[str, str] = {}
    for key, task_ids in values.items():
        for task_id in task_ids:
            previous = memberships.setdefault(task_id, key)
            if previous != key:
                raise SchemaError(f"task {task_id} appears in both tasks.{previous} and tasks.{key}")
    if len(values["active"]) > 1:
        raise SchemaError("tasks.active may contain at most one task in serial mode")
    return ProjectQueue(
        active=values["active"],
        queued=values["queued"],
        blocked=values["blocked"],
        completed=values["completed"],
    )


def validate_active_task_mirror(data: Mapping[str, object]) -> None:
    queue = validate_project_state(data)
    mirror = data.get("active_task")
    expected = queue.active[0] if queue.active else None
    if mirror != expected:
        raise SchemaError(f"active_task must mirror tasks.active[0]: expected {expected!r}, found {mirror!r}")


def _require_int(data: Mapping[str, object], field: str, minimum: int = 0) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise SchemaError(f"{field} must be an integer >= {minimum}")
    return value


def validate_task_state(data: Mapping[str, object]) -> None:
    task = data.get("task")
    if not isinstance(task, str) or not task:
        raise SchemaError("task must be a non-empty string")
    status = data.get("status")
    if status not in _TASK_STATUSES:
        raise SchemaError(f"status is not a supported task state: {status!r}")
    _require_int(data, "revision")
    _require_int(data, "stage_round")
    _require_int(data, "run_attempt")
    _require_int(data, "rework_round")
    _require_int(data, "auto_replan_count")
    _require_int(data, "agent_failure_count")
    run_status = data.get("run_status", "idle")
    if run_status not in _RUN_STATUSES:
        raise SchemaError(f"run_status is not supported: {run_status!r}")
    for field in ("run_id", "runtime_snapshot_ref"):
        value = data.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            raise SchemaError(f"{field} must be null or a non-empty string")
    reporting = data.get("reporting")
    if reporting is not None:
        if not isinstance(reporting, Mapping):
            raise SchemaError("reporting must be a mapping")
        phase = reporting.get("phase")
        if phase not in {"pending", "submitted", "active", "completed", "failed", "presentation_failed"}:
            raise SchemaError(f"unsupported reporting phase: {phase!r}")
        wake_key = reporting.get("wake_key")
        if not isinstance(wake_key, str) or not wake_key:
            raise SchemaError("reporting.wake_key must be a non-empty string")
