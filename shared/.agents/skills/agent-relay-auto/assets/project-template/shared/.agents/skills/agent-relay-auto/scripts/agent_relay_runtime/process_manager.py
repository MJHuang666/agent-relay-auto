"""Safe subprocess lifecycle with PID/start-time/run identity tracking."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
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
    run_dir: Path | None = None


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

    def start_worker(
        self,
        command: tuple[str, ...],
        cwd: Path,
        run_dir: Path,
        runtime: object | None = None,
    ) -> ManagedProcess:
        worker = Path(__file__).with_name("run_worker.py")
        interval = float(getattr(runtime, "heartbeat_interval_seconds", 10.0))
        run_id = run_dir.name
        process = subprocess.Popen(
            [
                sys.executable,
                str(worker),
                "--run-id",
                run_id,
                "--run-dir",
                str(run_dir),
                "--cwd",
                str(cwd),
                "--heartbeat-interval",
                str(interval),
                "--",
                *command,
            ],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        managed = ManagedProcess(
            process,
            run_id,
            process.pid,
            time.time(),
            _TailBuffer(self.output_limit_chars),
            _TailBuffer(self.output_limit_chars),
            (),
            run_dir,
        )
        process_record = run_dir / "process.json"
        deadline = time.monotonic() + 2
        while not process_record.is_file() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.005)
        if not process_record.is_file():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=2)
            raise RuntimeError(f"run worker did not publish process identity: {run_id}")
        return managed

    @staticmethod
    def _result(managed: ManagedProcess) -> ProcessResult:
        for thread in managed.drain_threads:
            thread.join(timeout=2)
        if managed.run_dir is not None:
            stdout_path = managed.run_dir / "stdout.log"
            stderr_path = managed.run_dir / "stderr.log"
            stdout = stdout_path.read_text(encoding="utf-8")[-managed.stdout_buffer.limit :] if stdout_path.is_file() else ""
            stderr = stderr_path.read_text(encoding="utf-8")[-managed.stderr_buffer.limit :] if stderr_path.is_file() else ""
            exit_path = managed.run_dir / "exit.json"
            exit_code = int(json.loads(exit_path.read_text(encoding="utf-8"))["exit_code"]) if exit_path.is_file() else int(managed.process.returncode)
            return ProcessResult(exit_code, stdout, stderr)
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
        process_group = managed.process.pid
        if managed.run_dir is not None:
            process_path = managed.run_dir / "process.json"
            if process_path.is_file():
                record = json.loads(process_path.read_text(encoding="utf-8"))
                if record.get("run_id") != managed.run_id:
                    raise RuntimeError("run identity mismatch before interrupt")
                process_group = int(record["process_group_id"])
        os.killpg(process_group, signal.SIGINT)
        try:
            managed.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process_group, signal.SIGTERM)
            try:
                managed.process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(process_group, signal.SIGKILL)
                managed.process.wait(timeout=grace_seconds)
        return self._result(managed)
