"""Serial project task queue operations."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sibling(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"agent_relay_runtime_{name}_queue", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runtime module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from .markdown_state import atomic_write_text, parse_fenced_yaml, set_yaml_value
    from .state_store import _state_lock
except ImportError:
    _markdown_state = _sibling("markdown_state")
    atomic_write_text = _markdown_state.atomic_write_text
    parse_fenced_yaml = _markdown_state.parse_fenced_yaml
    set_yaml_value = _markdown_state.set_yaml_value
    _state_store = _sibling("state_store")
    _state_lock = _state_store._state_lock


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def activate_next_queued_task(repo: Path, expected_project_revision: int) -> str | None:
    repo = Path(repo)
    with _state_lock(repo, "activate-next-task"):
        path = repo / "docs/agent/PROJECT_STATUS.md"
        text = path.read_text(encoding="utf-8")
        project = parse_fenced_yaml(text)
        actual_revision = project.get("project_revision")
        if actual_revision is not None and actual_revision != expected_project_revision:
            raise ValueError(
                f"project revision mismatch: expected {expected_project_revision}, actual {actual_revision}"
            )
        tasks = project.get("tasks") or {}
        active = list(tasks.get("active") or [])
        queued = list(tasks.get("queued") or [])
        if active or not queued:
            return None
        task_id = queued.pop(0)
        updated = set_yaml_value(text, ("tasks", "active"), [task_id])
        updated = set_yaml_value(updated, ("tasks", "queued"), queued)
        updated = set_yaml_value(updated, ("active_task",), task_id)
        if actual_revision is not None:
            updated = set_yaml_value(updated, ("project_revision",), expected_project_revision + 1)
        updated = set_yaml_value(updated, ("updated_at",), _now())
        atomic_write_text(path, updated)
        return task_id
