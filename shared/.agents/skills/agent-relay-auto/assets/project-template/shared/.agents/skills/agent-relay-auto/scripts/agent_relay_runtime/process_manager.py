"""Safe subprocess lifecycle with PID/start-time/run identity tracking."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ManagedProcess:
    process: subprocess.Popen[str]
    run_id: str
    pid: int
    process_started_at: float


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str


class ProcessManager:
    def start(self, command: tuple[str, ...], cwd: Path, run_id: str) -> ManagedProcess:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        return ManagedProcess(process, run_id, process.pid, time.time())

    def poll(self, managed: ManagedProcess) -> ProcessResult | None:
        code = managed.process.poll()
        if code is None:
            return None
        stdout, stderr = managed.process.communicate()
        return ProcessResult(code, stdout, stderr)

    def interrupt(self, managed: ManagedProcess, grace_seconds: float = 30.0) -> ProcessResult:
        os.killpg(managed.process.pid, signal.SIGINT)
        try:
            stdout, stderr = managed.process.communicate(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            managed.process.terminate()
            stdout, stderr = managed.process.communicate()
        return ProcessResult(managed.process.returncode, stdout, stderr)
