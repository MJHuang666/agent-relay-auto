"""Common adapter data types."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence


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
class LaunchContext:
    task_id: str
    role: str
    participant_id: str
    run_id: str
    writer_session: str
    start_status: str
    start_revision: int
    stage_round: int
    plan_version: int | None
    subagent_policy: str | None
    required_inputs: Sequence[str]
    required_outputs: Sequence[str]
    completion_command: str

    @classmethod
    def from_state(cls, request: LaunchRequest, state: Mapping[str, object]) -> "LaunchContext":
        writer_session = str(state.get("writer_session") or "")
        if writer_session != request.run_id:
            raise ValueError(
                f"writer_session mismatch for launch context: expected {request.run_id}, found {writer_session or 'null'}"
            )
        if request.role == "implementer":
            inputs = ("requirement.md", "plan.md", "previous_progress")
            outputs = ("execution.md", "delivery evidence")
            command = (
                "python3 .agents/skills/agent-relay-auto/scripts/relay_state.py --repo . "
                f"implementation-done --task {request.task_id} --expected-revision {state['revision']} "
                f"--participant-id {request.participant_id} --run-id {request.run_id}"
            )
        elif request.role == "reviewer":
            inputs = ("requirement.md", "plan.md", "execution.md", "delivery evidence")
            outputs = ("review.md", "verdict evidence")
            command = (
                "python3 .agents/skills/agent-relay-auto/scripts/relay_state.py --repo . "
                f"verdict --task {request.task_id} --expected-revision {state['revision']} "
                f"--participant-id {request.participant_id} --run-id {request.run_id}"
            )
        else:
            raise ValueError(f"background launch context is unsupported for role {request.role}")
        return cls(
            task_id=request.task_id,
            role=request.role,
            participant_id=request.participant_id,
            run_id=request.run_id,
            writer_session=writer_session,
            start_status=str(state.get("status")),
            start_revision=int(state["revision"]),
            stage_round=int(state.get("stage_round", 1)),
            plan_version=int(state["plan_version"]) if state.get("plan_version") is not None else None,
            subagent_policy=str(state["subagent_policy"]) if state.get("subagent_policy") is not None else None,
            required_inputs=inputs,
            required_outputs=outputs,
            completion_command=command,
        )

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["required_inputs"] = list(self.required_inputs)
        payload["required_outputs"] = list(self.required_outputs)
        return payload


def build_role_prompt(request: LaunchRequest, context: LaunchContext) -> str:
    return (
        f"You are {context.participant_id}, serving role {context.role} for {context.task_id}.\n"
        f"This Runner turn is {context.run_id}. STATE.md writer_session must equal that value.\n"
        "When it matches, it is your lease and not a foreign writer. "
        "Only a different non-null writer_session is a foreign writer conflict.\n"
        f"Read launch context and task evidence, then re-read STATE.md revision {context.start_revision} or newer before writing.\n"
        f"Complete the stage with: {context.completion_command}\n"
        "A final chat response alone does not complete the stage. Do not start the next role."
    )


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str


class AgentAdapter(Protocol):
    def capabilities(self) -> AdapterCapabilities: ...
    def build_command(self, request: LaunchRequest, context: LaunchContext) -> tuple[str, ...]: ...
