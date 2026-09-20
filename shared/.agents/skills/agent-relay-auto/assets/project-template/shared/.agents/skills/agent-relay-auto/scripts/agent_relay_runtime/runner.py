"""Project-independent Runner loop."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


def _sibling(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"agent_relay_runtime_{name}_runner", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runtime module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from .registry import ProjectRegistry
    from .supervisor import ProjectSupervisor, SupervisorDecision
    from .notifications import MacOSNotifier, NotificationJournal, NotificationKey
    from .config import load_runtime_config
except ImportError:
    ProjectRegistry = _sibling("registry").ProjectRegistry
    _supervisor_module = _sibling("supervisor")
    ProjectSupervisor = _supervisor_module.ProjectSupervisor
    SupervisorDecision = _supervisor_module.SupervisorDecision
    MacOSNotifier = _sibling("notifications").MacOSNotifier
    NotificationJournal = _sibling("notifications").NotificationJournal
    NotificationKey = _sibling("notifications").NotificationKey
    load_runtime_config = _sibling("config").load_runtime_config


_reporting_module = _sibling("reporting")


class RelayRunner:
    def __init__(self, registry: ProjectRegistry, adapter_factory, notifier=None, planner_wake_factory=None):
        self.registry = registry
        self.adapter_factory = adapter_factory
        self.notifier = notifier or MacOSNotifier()
        if planner_wake_factory is None:
            factory_path = Path(__file__).with_name("planner_wake") / "factory.py"
            spec = importlib.util.spec_from_file_location("agent_relay_planner_wake_factory_runner", factory_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            planner_wake_factory = module.create_planner_wake_factory()
        self.planner_wake_factory = planner_wake_factory
        self.supervisors: dict[Path, ProjectSupervisor] = {}
        self._project_errors: dict[Path, str] = {}
        self._stopping = False

    def _supervisor(self, repo: Path) -> ProjectSupervisor:
        if repo not in self.supervisors:
            runtime = load_runtime_config(repo)
            self.supervisors[repo] = ProjectSupervisor(
                repo,
                self.adapter_factory(repo),
                runtime=runtime,
                reporting=_reporting_module.ReportingCoordinator(
                    repo, self.planner_wake_factory, runtime.reporting
                ),
            )
        return self.supervisors[repo]

    def run_once(self):
        decisions = []
        for repo in self.registry.enabled_projects():
            try:
                decision = self._supervisor(repo).tick()
                self._project_errors.pop(repo, None)
            except Exception as error:
                self.supervisors.pop(repo, None)
                detail = f"{repo}: {type(error).__name__}: {error}"
                report = self._project_errors.get(repo) != detail
                self._project_errors[repo] = detail
                decision = SupervisorDecision("project_error", detail=detail, report=report)
            decisions.append(decision)
            attention = {
                "waiting_foreground_planner", "waiting_user", "blocked", "done", "project_error"
            }
            if decision.action in attention and decision.report:
                task_id = decision.task_id or "Runner"
                revision = 0
                state_path = ""
                if decision.task_id:
                    path = repo / "docs/agent/tasks" / decision.task_id / "STATE.md"
                    state_path = str(path)
                    if path.is_file():
                        state = _sibling("markdown_state").parse_fenced_yaml(path.read_text(encoding="utf-8"))
                        revision = int(state.get("revision", 0))
                key = NotificationKey(repo.name, task_id, decision.action.upper(), revision)
                if NotificationJournal(repo).emit_once(key, state_path):
                    self.notifier.notify(
                        repo.name, task_id, key.state, decision.detail or decision.action,
                        revision, state_path,
                    )
        return tuple(decisions)

    def serve(self, poll_interval_seconds: float = 45.0) -> None:
        while not self._stopping:
            for decision in self.run_once():
                if decision.action == "project_error" and decision.report:
                    print(f"Agent Relay Auto project error: {decision.detail}", file=sys.stderr, flush=True)
            time.sleep(poll_interval_seconds)

    def stop(self) -> None:
        self._stopping = True
