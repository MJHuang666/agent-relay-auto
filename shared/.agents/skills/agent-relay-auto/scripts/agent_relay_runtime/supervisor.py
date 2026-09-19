"""One-project supervisor; it never invents a state transition."""

from __future__ import annotations

import importlib.util
import sys
import time
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
    from .config import RuntimeConfig
    from .run_store import RunStore
    from .state_store import ClaimKey, StateStore
    from .adapters.base import LaunchContext, LaunchRequest
except ImportError:
    _process = _sibling("process_manager")
    _runs = _sibling("run_store")
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
    RuntimeConfig = _sibling("config").RuntimeConfig
    RunStore = _runs.RunStore
    ClaimKey = _state.ClaimKey
    StateStore = _state.StateStore
    LaunchRequest = _base.LaunchRequest
    LaunchContext = _base.LaunchContext


@dataclass(frozen=True)
class SupervisorDecision:
    action: str
    task_id: str | None = None
    run_id: str | None = None
    detail: str = ""
    report: bool = False


class ProjectSupervisor:
    def __init__(
        self,
        repo: Path,
        adapter,
        process_manager: ProcessManager | None = None,
        run_store: RunStore | None = None,
        runtime: RuntimeConfig | None = None,
    ):
        self.repo = Path(repo).resolve()
        self.adapter = adapter
        self.process_manager = process_manager or ProcessManager()
        self.runtime = runtime or RuntimeConfig.defaults()
        self.store = StateStore(self.repo, self.runtime.policy.max_agent_retries)
        self.run_store = run_store or RunStore(self.repo)
        self._active: dict[str, ManagedProcess] = {}
        self._start_status: dict[str, str] = {}

    def _finalize(
        self,
        task_id: str,
        managed: ManagedProcess,
        exit_code: int,
        termination_reason: str,
    ) -> SupervisorDecision:
        self._active.pop(task_id, None)
        start_status = self._start_status.pop(task_id, "")
        self.run_store.finish(managed.run_id, exit_code, None)
        on_result = getattr(self.adapter, "on_result", None)
        if on_result is not None:
            on_result(self, task_id, managed.run_id, exit_code)
            self.run_store.mark_protocol_result(managed.run_id, "completed")
            return SupervisorDecision("finished", task_id, managed.run_id)
        final = self.store.finish_run(
            task_id,
            managed.run_id,
            exit_code,
            start_status,
            termination_reason,
        )
        self.run_store.mark_protocol_result(managed.run_id, str(final.action))
        action = {
            "completed": "finished",
            "retry": "retry_scheduled",
            "blocked": "blocked",
        }.get(final.action, "protocol_failure")
        return SupervisorDecision(action, task_id, managed.run_id, detail=termination_reason, report=action == "blocked")

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
                elapsed = time.time() - managed.process_started_at
                if elapsed >= self.runtime.limits.agent_timeout_minutes * 60:
                    result = self.process_manager.interrupt(
                        managed, self.runtime.limits.interrupt_grace_seconds
                    )
                    return self._finalize(str(task_id), managed, result.exit_code, "timeout")
                return SupervisorDecision("already_running", task_id, managed.run_id)
            if managed.run_dir is None:
                if result.stdout:
                    self.run_store.append(managed.run_id, "stdout", result.stdout)
                if result.stderr:
                    self.run_store.append(managed.run_id, "stderr", result.stderr)
            exit_record = self.run_store.read_exit(managed.run_id) or {}
            reason = str(exit_record.get("termination_reason", "exit"))
            return self._finalize(str(task_id), managed, result.exit_code, reason)
        _, _, state = self.store._read_task(str(task_id))
        if state.get("run_status") in {"starting", "running"}:
            return SupervisorDecision("already_running", str(task_id), str(state.get("run_id")))
        status = state.get("status")
        if status in {"PLANNING", "REPORTING"}:
            return SupervisorDecision("waiting_foreground_planner", str(task_id), detail=str(status), report=True)
        role = {
            "IMPLEMENTING": "implementer",
            "CHANGES_REQUESTED": "implementer",
            "REVIEWING": "reviewer",
        }.get(status)
        if role is None:
            return SupervisorDecision("waiting", str(task_id))
        participant = state.get("current_participant") or f"{role}-main"
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        request = LaunchRequest(
            self.repo,
            str(task_id),
            role,
            str(participant),
            str(state.get("model", "default")),
            state.get("reasoning"),
            run_id,
            int(state["revision"]),
        )
        capabilities_for = getattr(self.adapter, "capabilities_for", None)
        capabilities = capabilities_for(request) if capabilities_for is not None else self.adapter.capabilities()
        if not capabilities.noninteractive:
            return SupervisorDecision("blocked", str(task_id), run_id)
        claim = ClaimKey(str(task_id), int(state["revision"]), str(participant), int(state.get("stage_round", 1)))
        result = self.store.claim(claim, run_id)
        run_created = False
        try:
            _, _, claimed_state = self.store._read_task(str(task_id))
            context = LaunchContext.from_state(request, claimed_state)
            run_dir = self.run_store.create(
                {
                    "task_id": str(task_id),
                    "role": role,
                    "participant_id": str(participant),
                    "agent": type(self.adapter).__name__,
                    "model": request.model,
                    "run_id": run_id,
                    "start_revision": result.output_revision,
                    "start_status": str(state.get("status")),
                    "status": "active",
                }
            )
            run_created = True
            self.run_store.write_launch_context(run_id, context.as_dict())
            command = self.adapter.build_command(request, context)
            managed = self.process_manager.start_worker(
                command,
                self.repo,
                run_dir,
                self.runtime.limits,
            )
        except Exception:
            if run_created:
                self.run_store.finish(run_id, 1, None)
            self.store.finish_run(str(task_id), run_id, 1)
            raise
        self._active[str(task_id)] = managed
        self._start_status[str(task_id)] = str(state.get("status"))
        return SupervisorDecision("started", str(task_id), run_id)
