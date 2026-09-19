#!/usr/bin/env python3
"""Durable wrapper for one background Agent command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class RunWorkerSpec:
    run_id: str
    run_dir: Path
    cwd: Path
    command: Sequence[str]
    heartbeat_interval_seconds: float = 10.0


def _command_sha256(command: Sequence[str]) -> str:
    encoded = json.dumps(list(command), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def execute(spec: RunWorkerSpec) -> int:
    spec.run_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    with (spec.run_dir / "stdout.log").open("a", encoding="utf-8") as stdout_handle, (
        spec.run_dir / "stderr.log"
    ).open("a", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            list(spec.command),
            cwd=str(spec.cwd),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            start_new_session=True,
        )
        _atomic_json(
            spec.run_dir / "process.json",
            {
                "run_id": spec.run_id,
                "worker_pid": os.getpid(),
                "agent_pid": process.pid,
                "process_group_id": process.pid,
                "process_started_at": started_at,
                "started_at": _now(),
                "command_sha256": _command_sha256(spec.command),
            },
        )
        sequence = 1
        while process.poll() is None:
            _atomic_json(
                spec.run_dir / "heartbeat.json",
                {"run_id": spec.run_id, "sequence": sequence, "agent_pid": process.pid, "observed_at": _now()},
            )
            sequence += 1
            try:
                process.wait(timeout=max(0.001, spec.heartbeat_interval_seconds))
            except subprocess.TimeoutExpired:
                pass
        _atomic_json(
            spec.run_dir / "heartbeat.json",
            {"run_id": spec.run_id, "sequence": sequence, "agent_pid": process.pid, "observed_at": _now()},
        )
        exit_code = int(process.returncode)
    _atomic_json(
        spec.run_dir / "exit.json",
        {
            "run_id": spec.run_id,
            "exit_code": exit_code,
            "termination_reason": "exit",
            "finished_at": _now(),
        },
    )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--heartbeat-interval", type=float, default=10.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")
    return execute(
        RunWorkerSpec(
            args.run_id,
            Path(args.run_dir).resolve(),
            Path(args.cwd).resolve(),
            tuple(command),
            args.heartbeat_interval,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
