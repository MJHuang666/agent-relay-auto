"""Tool-independent Planner wake contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class WakeContractError(ValueError):
    pass


_CAPABILITY_LABELS = {"verified", "experimental", "static_only", "unavailable"}


@dataclass(frozen=True)
class WakeCapabilities:
    resume_original_conversation: str
    submit_turn: str
    reopen_original_ui: str
    end_to_end_reporting: str

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            value = getattr(self, field)
            if value not in _CAPABILITY_LABELS:
                raise WakeContractError(f"invalid capability label for {field}: {value!r}")


@dataclass(frozen=True)
class WakeRequest:
    repo: Path
    task_id: str
    expected_revision: int
    participant_id: str
    wake_key: str


@dataclass(frozen=True)
class SubmissionReceipt:
    wake_key: str
    tool: str
    conversation_id: str
    remote_id: str
    status: str
    debug_command: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObservationResult:
    status: str
    detail: str = ""


@dataclass(frozen=True)
class PresentationResult:
    status: str
    detail: str = ""


class PlannerWakeAdapter(Protocol):
    def probe(self, channel) -> WakeCapabilities: ...
    def resume(self, channel) -> None: ...
    def submit_report(self, channel, request: WakeRequest) -> SubmissionReceipt: ...
    def observe(self, receipt: SubmissionReceipt) -> ObservationResult: ...
    def present(self, channel) -> PresentationResult: ...


def build_reporting_prompt(request: WakeRequest) -> str:
    return (
        "Task reached REPORTING. Resume the registered Planner identity and rebuild context from project files.\n"
        f"expected_task_id: {request.task_id}\n"
        f"expected_revision: {request.expected_revision}\n"
        f"planner_participant_id: {request.participant_id}\n"
        f"wake_key: {request.wake_key}\n"
        "1. Validate task_id, revision, participant_id, and Reviewer PASS.\n"
        "2. Read plan, implementation, tests, review, and delivery evidence.\n"
        "3. If complete, write the final delivery report and run report-done with this wake_key.\n"
        "4. If evidence or authority conflicts, record the reason and move to BLOCKED; never guess completion.\n"
        "5. Do not edit product code or perform merge, push, release, or deploy.\n"
    )
