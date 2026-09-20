"""Durable coordinator for waking the registered foreground Planner."""

from __future__ import annotations

import importlib.util
import hashlib
import sys
import time
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
    def _receipt(event, channel):
        return _base.SubmissionReceipt(
            str(event["wake_key"]), str(event["tool"]), channel.conversation_id,
            str(event["receipt_id"]), "submitted",
        )

    @staticmethod
    def _masked_conversation(conversation_id: str) -> str:
        return f"***{conversation_id[-6:]}"

    @staticmethod
    def _safe_receipt_id(receipt, channel) -> str:
        remote_id = str(receipt.remote_id)
        if channel.conversation_id in remote_id:
            digest = hashlib.sha256(remote_id.encode("utf-8")).hexdigest()[:16]
            return f"sha256:{digest}"
        return remote_id

    def _submit(self, task_id, wake_revision, key, channel, adapter, attempt):
        self.events.append({"wake_key": key, "status": "submitting", "attempt": attempt})
        receipt = adapter.submit_report(
            channel,
            _base.WakeRequest(self.repo, task_id, wake_revision, channel.participant_id, key),
        )
        self.events.append({
            "wake_key": key, "status": "submitted", "attempt": attempt,
            "tool": receipt.tool,
            "conversation_id_masked": self._masked_conversation(receipt.conversation_id),
            "receipt_id": self._safe_receipt_id(receipt, channel),
        })
        return receipt

    def _present(self, task_id, key, channel, adapter, attempt):
        try:
            adapter.present(channel)
        except Exception as error:
            next_retry_at = time.time() + self.policy.presentation_retry_interval_seconds
            self.events.append({
                "wake_key": key,
                "status": "presentation_failed",
                "attempt": attempt,
                "next_retry_at": next_retry_at,
                "detail": f"{type(error).__name__}: {error}",
            })
            if attempt >= self.policy.presentation_retry_limit:
                return ReportingDecision(
                    "report_completed", task_id, key,
                    f"DONE; presentation failed after {attempt} attempts: {type(error).__name__}: {error}",
                )
            return ReportingDecision(
                "report_presentation_retry", task_id, key,
                f"presentation attempt {attempt} failed: {type(error).__name__}: {error}",
            )
        self.events.append({"wake_key": key, "status": "presented", "attempt": attempt})
        return ReportingDecision("report_completed", task_id, key, "presented")

    def _tick_done(self, task_id, key, channel, adapter):
        latest = self.events.latest(key) if key else None
        if latest is None or latest.get("status") in {"presented", "completed"}:
            return ReportingDecision("report_completed", task_id, key)
        if latest.get("status") == "presentation_failed":
            attempt = int(latest.get("attempt", 1))
            if attempt >= self.policy.presentation_retry_limit:
                return ReportingDecision(
                    "report_completed", task_id, key,
                    f"DONE; presentation retry limit reached after {attempt} attempts",
                )
            if time.time() < float(latest.get("next_retry_at", 0)):
                return ReportingDecision("report_presentation_retry", task_id, key, "waiting for presentation retry")
            return self._present(task_id, key, channel, adapter, attempt + 1)
        submission = self.events.find_submission(key)
        if submission is None:
            return ReportingDecision("report_completed", task_id, key, "DONE without a persisted wake receipt")
        return self._present(task_id, key, channel, adapter, 1)

    def tick(self, task_id: str) -> ReportingDecision:
        try:
            self.store.recover_pending_transactions()
            state = self._state(task_id)
            if state.get("status") not in {"REPORTING", "DONE"}:
                return ReportingDecision("blocked", task_id, detail="task is not REPORTING")
            if not self.policy.enabled:
                return ReportingDecision("blocked", task_id, detail="automatic Planner reporting is disabled")
            if state.get("current_role") != "planner" or not state.get("review_ref") or not state.get("delivery_id"):
                return ReportingDecision("blocked", task_id, detail="Planner or Reviewer evidence is incomplete")
            channel = self.channels.load()
            if channel is None:
                return ReportingDecision("blocked", task_id, detail="Planner channel is not registered")
            if channel.participant_id != state.get("current_participant"):
                return ReportingDecision("blocked", task_id, detail="Planner participant does not match channel")
            if state.get("status") == "DONE":
                reporting = state.get("reporting") if isinstance(state.get("reporting"), dict) else {}
                key = str(reporting.get("wake_key") or "")
                return self._tick_done(task_id, key, channel, self.adapter_factory(channel.tool))
            wake_revision, key = self.store.prepare_reporting_wake(
                task_id, int(state["revision"]), channel.participant_id, channel.conversation_id
            )
            latest = self.events.latest(key)
            adapter = self.adapter_factory(channel.tool)
            if latest is None:
                self._submit(task_id, wake_revision, key, channel, adapter, 1)
                completed_state = self._state(task_id)
                if completed_state.get("status") == "DONE":
                    return self._present(task_id, key, channel, adapter, 1)
                self.store.set_reporting_phase(task_id, wake_revision, key, "submitted")
                return ReportingDecision("report_submitted", task_id, key)
            if latest["status"] == "submitting":
                reconcile = getattr(adapter, "reconcile", None)
                receipt = reconcile(channel, key) if reconcile is not None else None
                if receipt is None:
                    return ReportingDecision("blocked", task_id, key, "ambiguous remote submission")
                self.events.append({
                    "wake_key": key, "status": "submitted", "attempt": latest.get("attempt", 1),
                    "tool": receipt.tool,
                    "conversation_id_masked": self._masked_conversation(receipt.conversation_id),
                    "receipt_id": self._safe_receipt_id(receipt, channel),
                })
                self.store.set_reporting_phase(task_id, wake_revision, key, "submitted")
            if latest["status"] == "model_failed":
                attempt = int(latest.get("attempt", 1))
                if attempt > self.policy.model_retry_limit:
                    return ReportingDecision("blocked", task_id, key, "Planner report-done retry limit reached")
                self._submit(task_id, wake_revision, key, channel, adapter, attempt + 1)
                self.store.set_reporting_phase(task_id, wake_revision, key, "submitted")
                return ReportingDecision("report_submitted", task_id, key, f"model retry {attempt}")
            submitted = self.events.find_submission(key)
            if submitted is None:
                return ReportingDecision("blocked", task_id, key, "submission receipt is unavailable")
            observed = adapter.observe(self._receipt(submitted, channel))
            if observed.status == "completed":
                completed_state = self._state(task_id)
                if completed_state.get("status") != "DONE":
                    attempt = int(submitted.get("attempt", 1))
                    self.events.append({
                        "wake_key": key,
                        "status": "model_failed",
                        "attempt": attempt,
                        "detail": "remote turn completed without guarded report-done",
                    })
                    if attempt > self.policy.model_retry_limit:
                        return ReportingDecision(
                            "blocked", task_id, key,
                            "remote Planner turn completed without report-done; retry limit reached",
                        )
                    return ReportingDecision(
                        "report_wake_pending", task_id, key,
                        "remote Planner turn completed without report-done; retry scheduled",
                    )
                self.events.append({
                    "wake_key": key, "status": "model_completed", "attempt": submitted.get("attempt", 1)
                })
                return self._present(task_id, key, channel, adapter, 1)
            if observed.status == "active":
                self.store.set_reporting_phase(task_id, wake_revision, key, "active")
            return ReportingDecision("report_active", task_id, key, observed.detail)
        except Exception as error:
            return ReportingDecision("blocked", task_id, detail=f"{type(error).__name__}: {error}")
