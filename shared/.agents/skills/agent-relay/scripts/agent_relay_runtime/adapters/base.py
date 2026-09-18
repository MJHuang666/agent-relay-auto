"""Common adapter data types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AdapterCapabilities:
    noninteractive: bool
    model_discovery: bool
    native_resume: bool
    structured_usage: bool
    graceful_interrupt: bool


@dataclass(frozen=True)
class LaunchRequest:
    repo: Path
    task_id: str
    role: str
    participant_id: str
    model: str
    reasoning: str | None
    run_id: str
    expected_revision: int


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str


class AgentAdapter(Protocol):
    def capabilities(self) -> AdapterCapabilities: ...
    def build_command(self, request: LaunchRequest) -> tuple[str, ...]: ...

