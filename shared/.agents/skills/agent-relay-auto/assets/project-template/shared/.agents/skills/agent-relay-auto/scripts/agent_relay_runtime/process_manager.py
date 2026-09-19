"""Safe subprocess lifecycle with PID/start-time/run identity tracking."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path


class _TailBuffer:
    def __init__(self, limit: int):
        self.limit = limit
        self._value = ""
        self._lock = threading.Lock()

    def append(self, value: str) -> None:
        with self._lock:
            self._value = (self._value + value)[-self.limit :]

    def value(self) -> str:
        with self._lock:
            return self._value


@dataclass
class ManagedProcess:
    process: subprocess.Popen[str]
    run_id: str
    pid: int
    process_started_at: float
    stdout_buffer: _TailBuffer
    stderr_buffer: _TailBuffer
    drain_threads: tuple[threading.Thread, ...]


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str


class ProcessManager:
    def __init__(self, output_limit_chars: int = 256 * 1024):
        if output_limit_chars < 1:
            raise ValueError("output_limit_chars must be positive")
        self.output_limit_chars = output_limit_chars

    @staticmethod
    def _drain(stream, buffer: _TailBuffer) -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                buffer.append(chunk)
        finally:
            stream.close()

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
        stdout_buffer = _TailBuffer(self.output_limit_chars)
        stderr_buffer = _TailBuffer(self.output_limit_chars)
        threads = (
            threading.Thread(target=self._drain, args=(process.stdout, stdout_buffer), daemon=True),
            threading.Thread(target=self._drain, args=(process.stderr, stderr_buffer), daemon=True),
        )
        for thread in threads:
            thread.start()
        return ManagedProcess(process, run_id, process.pid, time.time(), stdout_buffer, stderr_buffer, threads)

    @staticmethod
    def _result(managed: ManagedProcess) -> ProcessResult:
        for thread in managed.drain_threads:
            thread.join(timeout=2)
        return ProcessResult(
            int(managed.process.returncode),
            managed.stdout_buffer.value(),
            managed.stderr_buffer.value(),
        )

    def poll(self, managed: ManagedProcess) -> ProcessResult | None:
        code = managed.process.poll()
        if code is None:
            return None
        return self._result(managed)

    def interrupt(self, managed: ManagedProcess, grace_seconds: float = 30.0) -> ProcessResult:
        os.killpg(managed.process.pid, signal.SIGINT)
        try:
            managed.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            managed.process.terminate()
            managed.process.wait()
        return self._result(managed)
