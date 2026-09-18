"""Common adapter data types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
class ModelOption:
    model_id: str
    display_name: str


class FailureKind(Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH = "auth"
    MODEL_UNAVAILABLE = "model_unavailable"
    PERMISSION = "permission"
    UNSUPPORTED = "unsupported"
    UNKNOWN_REMOTE_RUN = "unknown_remote_run"


@dataclass(frozen=True)
class ExitClassification:
    success: bool
    failure: FailureKind | None = None
    detail: str = ""


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
