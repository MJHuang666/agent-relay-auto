"""Project-local run logs and durable Runner event files."""

from __future__ import annotations

import json
import os
import tempfile
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

try:
    from .redaction import redact_text
except ImportError:
    _redaction_path = Path(__file__).with_name("redaction.py")
    _redaction_spec = importlib.util.spec_from_file_location("agent_relay_runtime_redaction", _redaction_path)
    if _redaction_spec is None or _redaction_spec.loader is None:
        raise ImportError(f"cannot load {_redaction_path}")
    _redaction = importlib.util.module_from_spec(_redaction_spec)
    _redaction_spec.loader.exec_module(_redaction)
    redact_text = _redaction.redact_text


class RunStore:
    def __init__(self, repo: Path, max_log_bytes: int = 10 * 1024 * 1024, keep_rotations: int = 5):
        self.repo = Path(repo)
        self.root = self.repo / ".agent-relay-auto" / "runs"
        self.max_log_bytes = max_log_bytes
        self.keep_rotations = keep_rotations

    def _run_path(self, run_id: str) -> Path:
        for candidate in self.root.glob(f"*/{run_id}"):
            return candidate
        raise FileNotFoundError(f"unknown run: {run_id}")

    def create(self, metadata: Mapping[str, object]) -> Path:
        run_id = str(metadata["run_id"])
        task_id = str(metadata["task_id"])
        path = self.root / task_id / run_id
        path.mkdir(parents=True, exist_ok=False)
        payload = dict(metadata)
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        (path / "metadata.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (path / "events.jsonl").touch()
        (path / "heartbeat.json").touch()
        return path

    def write_launch_context(self, run_id: str, context: Mapping[str, object]) -> Path:
        path = self._run_path(run_id) / "launch-context.json"
        payload = json.dumps(dict(context), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return path

    def _rotate(self, path: Path, incoming_size: int) -> None:
        if not path.exists() or path.stat().st_size + incoming_size <= self.max_log_bytes:
            return
        for index in range(self.keep_rotations - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}") if index > 0 else path
            target = path.with_name(f"{path.name}.{index + 1}")
            if source.exists():
                if index == self.keep_rotations - 1:
                    source.unlink()
                else:
                    os.replace(source, target)
        os.replace(path, path.with_name(f"{path.name}.1"))

    def append(self, run_id: str, stream: str, text: str) -> None:
        if stream not in {"stdout", "stderr"}:
            raise ValueError(f"unsupported log stream: {stream}")
        path = self._run_path(run_id) / f"{stream}.log"
        safe = redact_text(text, set(), os.environ)
        encoded = safe.encode("utf-8")
        self._rotate(path, len(encoded))
        with path.open("ab") as handle:
            handle.write(encoded)

    def append_event(self, run_id: str, event: Mapping[str, object]) -> None:
        path = self._run_path(run_id) / "events.jsonl"
        line = json.dumps(dict(event), ensure_ascii=False, sort_keys=True) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(redact_text(line, set(), os.environ))

    def write_heartbeat(self, run_id: str, heartbeat: Mapping[str, object]) -> None:
        path = self._run_path(run_id) / "heartbeat.json"
        path.write_text(json.dumps(dict(heartbeat), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def finish(self, run_id: str, exit_code: int, usage: Mapping[str, object] | None) -> None:
        path = self._run_path(run_id)
        metadata_path = path / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(
            {
                "status": "finished",
                "exit_code": exit_code,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        usage_payload = dict(usage) if usage is not None else {"status": "unavailable"}
        (path / "usage.json").write_text(json.dumps(usage_payload, indent=2) + "\n", encoding="utf-8")

    def cleanup(self, now: datetime) -> tuple[Path, ...]:
        deleted: list[Path] = []
        for path in self.root.glob("*/*"):
            metadata_path = path / "metadata.json"
            if not metadata_path.is_file():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("status") in {"active", "BLOCKED"}:
                continue
            finished = metadata.get("finished_at")
            if finished and datetime.fromisoformat(finished) < now - timedelta(days=30):
                deleted.append(path)
        return tuple(deleted)
