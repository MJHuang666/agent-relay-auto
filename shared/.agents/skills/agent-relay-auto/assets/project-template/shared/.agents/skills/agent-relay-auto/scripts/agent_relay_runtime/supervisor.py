"""One-project supervisor; it never invents a state transition."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


def _sibling(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"agent_relay_runtime_{name}_supervisor", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runtime module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from .process_manager import ManagedProcess, ProcessManager
    from .state_store import ClaimKey, StateStore
    from .adapters.base import LaunchRequest
except ImportError:
    _process = _sibling("process_manager")
    _state = _sibling("state_store")
    _base_path = Path(__file__).with_name("adapters") / "base.py"
    _base_spec = importlib.util.spec_from_file_location("agent_relay_runtime_base_supervisor", _base_path)
    if _base_spec is None or _base_spec.loader is None:
        raise ImportError(f"cannot load runtime module {_base_path}")
    _base = importlib.util.module_from_spec(_base_spec)
    sys.modules[_base_spec.name] = _base
    _base_spec.loader.exec_module(_base)
    ManagedProcess = _process.ManagedProcess
    ProcessManager = _process.ProcessManager
    ClaimKey = _state.ClaimKey
    StateStore = _state.StateStore
    LaunchRequest = _base.LaunchRequest


@dataclass(frozen=True)
class SupervisorDecision:
    action: str
    task_id: str | None = None
    run_id: str | None = None


class ProjectSupervisor:
    def __init__(self, repo: Path, adapter, process_manager: ProcessManager | None = None):
        self.repo = Path(repo).resolve()
        self.adapter = adapter
        self.process_manager = process_manager or ProcessManager()
        self.store = StateStore(self.repo)
        self._active: dict[str, ManagedProcess] = {}

    def tick(self) -> SupervisorDecision:
        project_path = self.repo / "docs/agent/PROJECT_STATUS.md"
        if not project_path.is_file():
            return SupervisorDecision("uninitialized")
        project = _sibling("markdown_state").parse_fenced_yaml(project_path.read_text(encoding="utf-8"))
        task_ids = (project.get("tasks") or {}).get("active") or []
        task_id = project.get("active_task") or (task_ids[0] if task_ids else None)
        if not task_id:
            return SupervisorDecision("idle")
        managed = self._active.get(task_id)
        if managed is not None:
            result = self.process_manager.poll(managed)
            if result is None:
                return SupervisorDecision("already_running", task_id, managed.run_id)
            self._active.pop(task_id, None)
            on_result = getattr(self.adapter, "on_result", None)
            if on_result is not None:
                on_result(self, task_id, managed.run_id, result.exit_code)
            return SupervisorDecision("finished", task_id, managed.run_id)
        _, _, state = self.store._read_task(str(task_id))
        if state.get("run_status") in {"starting", "running"}:
            return SupervisorDecision("already_running", str(task_id), str(state.get("run_id")))
        status = state.get("status")
        role = {"PLANNING": "planner", "IMPLEMENTING": "implementer", "REVIEWING": "reviewer", "REPORTING": "planner"}.get(status)
        if role is None:
            return SupervisorDecision("waiting", str(task_id))
        participant = state.get("current_participant") or f"{role}-main"
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        claim = ClaimKey(str(task_id), int(state["revision"]), str(participant), int(state.get("stage_round", 1)))
        result = self.store.claim(claim, run_id)
        request = LaunchRequest(self.repo, str(task_id), role, str(participant), str(state.get("model", "default")), state.get("reasoning"), run_id, result.input_revision)
        if not self.adapter.capabilities().noninteractive:
            return SupervisorDecision("blocked", str(task_id), run_id)
        managed = self.process_manager.start(self.adapter.build_command(request), self.repo, run_id)
        self._active[str(task_id)] = managed
        return SupervisorDecision("started", str(task_id), run_id)
