"""Durable coordinator for waking the registered foreground Planner."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


def _load(name: str, relative: str | None = None):
    path = Path(__file__).parent / (relative or f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"agent_relay_reporting_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_markdown = _load("markdown_state")
_channel = _load("planner_channel")
_wake = _load("wake_store")
_base = _load("wake_base", "planner_wake/base.py")
_state_store = _load("state_store")


@dataclass(frozen=True)
class ReportingDecision:
    action: str
    task_id: str
    wake_key: str | None = None
    detail: str = ""


class ReportingCoordinator:
    def __init__(self, repo: Path, adapter_factory, policy):
        self.repo = Path(repo).resolve()
        self.adapter_factory = adapter_factory
        self.policy = policy
        self.channels = _channel.PlannerChannelStore(self.repo)
        self.events = _wake.WakeEventStore(self.repo)
        self.store = _state_store.StateStore(self.repo)

    def _state(self, task_id: str):
        path = self.repo / "docs/agent/tasks" / task_id / "STATE.md"
        if not path.is_file():
            raise ValueError(f"missing task state: {path}")
        return _markdown.parse_fenced_yaml(path.read_text(encoding="utf-8"))

    @staticmethod
    def _receipt(event):
        return _base.SubmissionReceipt(
            str(event["wake_key"]), str(event["tool"]), str(event["conversation_id"]),
            str(event["receipt_id"]), "submitted",
        )

    def tick(self, task_id: str) -> ReportingDecision:
        try:
            state = self._state(task_id)
            if state.get("status") == "DONE":
                return ReportingDecision("report_completed", task_id)
            if state.get("status") != "REPORTING":
                return ReportingDecision("blocked", task_id, detail="task is not REPORTING")
            if state.get("current_role") != "planner" or not state.get("review_ref") or not state.get("delivery_id"):
                return ReportingDecision("blocked", task_id, detail="Planner or Reviewer evidence is incomplete")
            channel = self.channels.load()
            if channel is None:
                return ReportingDecision("blocked", task_id, detail="Planner channel is not registered")
            if channel.participant_id != state.get("current_participant"):
                return ReportingDecision("blocked", task_id, detail="Planner participant does not match channel")
            wake_revision, key = self.store.prepare_reporting_wake(
                task_id, int(state["revision"]), channel.participant_id, channel.conversation_id
            )
            latest = self.events.latest(key)
            adapter = self.adapter_factory(channel.tool)
            if latest is None:
                self.events.append({"wake_key": key, "status": "submitting", "attempt": 1})
                receipt = adapter.submit_report(
                    channel,
                    _base.WakeRequest(self.repo, task_id, wake_revision, channel.participant_id, key),
                )
                self.events.append({
                    "wake_key": key, "status": "submitted", "attempt": 1,
                    "tool": receipt.tool, "conversation_id": receipt.conversation_id,
                    "receipt_id": receipt.remote_id,
                })
                self.store.set_reporting_phase(task_id, wake_revision, key, "submitted")
                return ReportingDecision("report_submitted", task_id, key)
            if latest["status"] == "submitting":
                reconcile = getattr(adapter, "reconcile", None)
                receipt = reconcile(key) if reconcile is not None else None
                if receipt is None:
                    return ReportingDecision("blocked", task_id, key, "ambiguous remote submission")
                self.events.append({
                    "wake_key": key, "status": "submitted", "attempt": latest.get("attempt", 1),
                    "tool": receipt.tool, "conversation_id": receipt.conversation_id,
                    "receipt_id": receipt.remote_id,
                })
                self.store.set_reporting_phase(task_id, wake_revision, key, "submitted")
            submitted = self.events.find_submission(key)
            if submitted is None:
                return ReportingDecision("blocked", task_id, key, "submission receipt is unavailable")
            observed = adapter.observe(self._receipt(submitted))
            if observed.status == "completed":
                adapter.present(channel)
                self.events.append({"wake_key": key, "status": "completed", "attempt": submitted.get("attempt", 1)})
                return ReportingDecision("report_completed", task_id, key)
            if observed.status == "active":
                self.store.set_reporting_phase(task_id, wake_revision, key, "active")
            return ReportingDecision("report_active", task_id, key, observed.detail)
        except Exception as error:
            return ReportingDecision("blocked", task_id, detail=f"{type(error).__name__}: {error}")
