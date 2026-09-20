"""Project-local binding for the exact foreground Planner conversation."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


class PlannerChannelError(ValueError):
    """Raised when a Planner channel is missing, malformed, or belongs elsewhere."""


_SUPPORTED_TOOLS = {"codex", "opencode", "claude-code", "deepseek-harness"}


@dataclass(frozen=True)
class PlannerChannel:
    participant_id: str
    tool: str
    conversation_id: str
    project_path: str
    registered_at: str

    def __post_init__(self) -> None:
        for field in ("participant_id", "conversation_id", "project_path", "registered_at"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise PlannerChannelError(f"{field} must be a non-empty string")
        if self.tool not in _SUPPORTED_TOOLS:
            raise PlannerChannelError(f"unsupported Planner tool: {self.tool!r}")

    def validate_for(self, repo: Path) -> None:
        if Path(self.project_path).resolve() != Path(repo).resolve():
            raise PlannerChannelError(
                f"planner channel project_path {self.project_path!r} does not match {str(Path(repo).resolve())!r}"
            )


class PlannerChannelStore:
    def __init__(self, repo: Path):
        self.repo = Path(repo).resolve()
        self.path = self.repo / ".agent-relay-auto/planner-channel.json"

    def load(self) -> PlannerChannel | None:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("channel root is not an object")
            channel = PlannerChannel(**payload)
            channel.validate_for(self.repo)
            return channel
        except (OSError, ValueError, TypeError) as error:
            if isinstance(error, PlannerChannelError):
                raise
            raise PlannerChannelError(f"cannot read {self.path}: {error}") from error

    def save(self, channel: PlannerChannel) -> None:
        channel.validate_for(self.repo)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".planner-channel-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(asdict(channel), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
