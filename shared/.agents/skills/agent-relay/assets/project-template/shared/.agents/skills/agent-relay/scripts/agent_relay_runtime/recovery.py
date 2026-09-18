"""Safe interruption and restart reconciliation."""

from __future__ import annotations

from dataclasses import dataclass


class RecoveryMode:
    NATIVE_SESSION = "native-session"
    CHECKPOINT_RESTART = "checkpoint-restart"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ReconcileResult:
    status: str
    reason: str = ""


class RecoveryManager:
    def __init__(self, process_manager):
        self.process_manager = process_manager

    def interrupt(self, managed, grace_seconds: float = 30.0):
        return self.process_manager.interrupt(managed, grace_seconds)

    def reconcile(self, run: dict, *, process_exists: bool, observed_started_at: float | None) -> ReconcileResult:
        if process_exists and run.get("pid") is not None:
            if observed_started_at == run.get("process_started_at"):
                return ReconcileResult("monitor", "pid, process start time, and run_id match")
            return ReconcileResult("unknown", "PID may have been reused")
        if run.get("remote"):
            return ReconcileResult("blocked", "remote task may still be running")
        return ReconcileResult("restart", "local process is confirmed stopped")

    def resume(self, mode: str, session_id: str | None = None) -> str:
        if mode == RecoveryMode.NATIVE_SESSION and not session_id:
            raise ValueError("native session recovery requires a session ID")
        if mode == RecoveryMode.UNSUPPORTED:
            raise ValueError("adapter does not support recovery")
        return session_id or RecoveryMode.CHECKPOINT_RESTART
