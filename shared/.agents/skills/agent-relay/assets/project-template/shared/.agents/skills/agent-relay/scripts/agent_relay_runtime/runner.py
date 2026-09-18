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
    from .supervisor import ProjectSupervisor
    from .notifications import MacOSNotifier
except ImportError:
    ProjectRegistry = _sibling("registry").ProjectRegistry
    ProjectSupervisor = _sibling("supervisor").ProjectSupervisor
    MacOSNotifier = _sibling("notifications").MacOSNotifier


class RelayRunner:
    def __init__(self, registry: ProjectRegistry, adapter_factory, notifier=None):
        self.registry = registry
        self.adapter_factory = adapter_factory
        self.notifier = notifier or MacOSNotifier()
        self.supervisors: dict[Path, ProjectSupervisor] = {}
        self._stopping = False

    def _supervisor(self, repo: Path) -> ProjectSupervisor:
        if repo not in self.supervisors:
            self.supervisors[repo] = ProjectSupervisor(repo, self.adapter_factory(repo))
        return self.supervisors[repo]

    def run_once(self):
        decisions = []
        for repo in self.registry.enabled_projects():
            decision = self._supervisor(repo).tick()
            decisions.append(decision)
            if decision.task_id and decision.action in {"blocked", "waiting"}:
                self.notifier.notify(repo.name, decision.task_id, decision.action.upper(), decision.action)
        return tuple(decisions)

    def serve(self, poll_interval_seconds: float = 2.0) -> None:
        while not self._stopping:
            self.run_once()
            time.sleep(poll_interval_seconds)

    def stop(self) -> None:
        self._stopping = True
