#!/usr/bin/env python3
"""Command-line state transitions used by Agent Relay Auto Runner and agents."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent / "agent_relay_runtime"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_relay_runtime.markdown_state import atomic_write_text, parse_fenced_yaml, set_yaml_value  # noqa: E402
from agent_relay_runtime.state_store import (  # noqa: E402
    RevisionConflict,
    StateStore,
    StateStoreError,
    StageEvidence,
    TransitionError,
    _state_lock,
)


def _context(repo: Path, task_id: str):
    store = StateStore(repo)
    path, text, state = store._read_task(task_id)
    return store, path, text, state


def _write_values(path: Path, text: str, values: dict[tuple[str, ...], object]) -> None:
    updated = text
    for key_path, value in values.items():
        updated = set_yaml_value(updated, key_path, value)
    atomic_write_text(path, updated)


def _require_revision(state: dict, expected: int) -> None:
    actual = state.get("revision")
    if actual != expected:
        raise RevisionConflict(f"revision mismatch: expected {expected}, actual {actual}")


def _wait_user(args: argparse.Namespace) -> dict:
    question_source = Path(args.question_file)
    if not question_source.is_file():
        raise ValueError(f"question file is missing: {question_source}")
    repo = Path(args.repo).resolve()
    with _state_lock(repo, "wait-user"):
        _, state_path, text, state = _context(repo, args.task)
        _require_revision(state, args.expected_revision)
        if state.get("status") in {"DONE", "CANCELLED"}:
            raise TransitionError("terminal task cannot wait for user")
        question_id = f"Q-{uuid.uuid4().hex[:8].upper()}"
        question_ref = f"questions/{question_id}.md"
        question_path = state_path.parent / question_ref
        question_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(question_source, question_path)
        _write_values(
            state_path,
            text,
            {
                ("status",): "WAITING_USER",
                ("suspended_status",): state.get("status"),
                ("resume_role",): args.resume_role,
                ("question_id",): question_id,
                ("question_ref",): question_ref,
                ("revision",): args.expected_revision + 1,
            },
        )
    return {"task": args.task, "question_id": question_id, "output_revision": args.expected_revision + 1}


def _answer(args: argparse.Namespace) -> dict:
    answer_path = Path(args.answer_file)
    if not answer_path.is_file():
        raise ValueError(f"answer file is missing: {answer_path}")
    decision_values: dict[str, set[str]] = {"subagent_policy": {"USE", "DO_NOT_USE"}}
    if bool(args.decision_key) != bool(args.decision_value):
        raise ValueError("decision-key and decision-value must be supplied together")
    if args.decision_key:
        allowed = decision_values.get(args.decision_key)
        if allowed is None or args.decision_value not in allowed:
            raise ValueError(f"unsupported decision: {args.decision_key}={args.decision_value}")
    repo = Path(args.repo).resolve()
    with _state_lock(repo, "answer"):
        _, state_path, text, state = _context(repo, args.task)
        _require_revision(state, args.expected_revision)
        if state.get("status") != "WAITING_USER" or state.get("question_id") != args.question_id:
            raise TransitionError("question ID or waiting state does not match")
        answer_ref = f"decisions/{args.question_id}.md"
        answer_target = state_path.parent / answer_ref
        answer_target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            answer_target,
            f"# Decision {args.question_id}\n\nQuestion: {state.get('question_ref')}\n\n"
            + answer_path.read_text(encoding="utf-8")
            + "\n",
        )
        values = {
            ("status",): state.get("suspended_status") or "PLANNING",
            ("suspended_status",): None,
            ("resume_role",): None,
            ("question_id",): None,
            ("question_ref",): None,
            ("revision",): args.expected_revision + 1,
        }
        if args.decision_key == "subagent_policy":
            values[("subagent_policy",)] = args.decision_value
            values[("subagent_decision_ref",)] = answer_ref
        _write_values(
            state_path,
            text,
            values,
        )
    return {"task": args.task, "output_revision": args.expected_revision + 1, "answer_ref": answer_ref}


def _verdict(args: argparse.Namespace) -> dict:
    evidence = Path(args.evidence)
    if not evidence.is_file() or not evidence.read_text(encoding="utf-8").strip():
        raise ValueError("review verdict requires a non-empty evidence file")
    event = {
        "PASS": "review_passed",
        "CHANGES_REQUESTED": "changes_requested",
        "REPLAN_REQUIRED": "replan_required",
    }.get(args.verdict)
    if event is None:
        raise ValueError(f"unsupported verdict: {args.verdict}")
    delivery = _require_task_reference(Path(args.repo).resolve(), args.task, args.delivery_ref, "delivery")
    result = StateStore(Path(args.repo).resolve()).complete_stage(
        args.task,
        args.expected_revision,
        "reviewer",
        args.participant_id,
        args.run_id,
        event,
        StageEvidence(
            progress_ref=str(evidence),
            delivery_ref=args.delivery_ref,
            review_ref=str(evidence),
        ),
    )
    return result.__dict__


def _report_done(args: argparse.Namespace) -> dict:
    report = Path(args.report)
    if not report.is_file():
        raise ValueError(f"final report is missing: {report}")
    content = report.read_text(encoding="utf-8").lower()
    required = ("goal", "delivery", "tests", "reviewer", "limitations", "usage", "not executed")
    missing = [term for term in required if term not in content]
    if missing:
        raise ValueError("final report is missing sections: " + ", ".join(missing))
    _require_task_reference(Path(args.repo).resolve(), args.task, args.review_ref, "review")
    result = StateStore(Path(args.repo).resolve()).complete_stage(
        args.task,
        args.expected_revision,
        "planner",
        args.participant_id,
        None,
        "report_completed",
        StageEvidence(progress_ref=str(report), review_ref=args.review_ref, report_ref=str(report)),
    )
    return result.__dict__


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        raise ValueError(f"{label} file is missing or empty: {path}")
    return path


def _require_task_reference(repo: Path, task_id: str, reference: str, label: str) -> Path:
    raw_path = reference.split("#", 1)[0]
    path = Path(raw_path)
    if not path.is_absolute():
        path = repo / "docs/agent/tasks" / task_id / path
    return _require_file(path.resolve(), label)


def _plan_done(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    plan = _require_file(Path(args.plan), "plan")
    progress = _require_file(Path(args.progress), "progress")
    _require_task_reference(repo, args.task, args.approval_ref, "approval")
    result = StateStore(repo).complete_stage(
        args.task,
        args.expected_revision,
        "planner",
        args.participant_id,
        None,
        "plan_completed",
        StageEvidence(progress_ref=str(progress)),
    )
    return {**result.__dict__, "plan": str(plan), "approval_ref": args.approval_ref}


def _implementation_done(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    execution = _require_file(Path(args.execution), "execution")
    progress = _require_file(Path(args.progress), "progress")
    _require_task_reference(repo, args.task, args.delivery_ref, "delivery")
    result = StateStore(repo).complete_stage(
        args.task,
        args.expected_revision,
        "implementer",
        args.participant_id,
        args.run_id,
        "implementation_completed",
        StageEvidence(progress_ref=str(progress), delivery_ref=args.delivery_ref),
    )
    return {**result.__dict__, "execution": str(execution), "delivery_ref": args.delivery_ref}


def _status(args: argparse.Namespace) -> dict:
    store = StateStore(Path(args.repo).resolve())
    _, _, state = store._read_task(args.task)
    return {"task": args.task, "status": state.get("status"), "revision": state.get("revision"), "run_id": state.get("run_id")}


def _cancel(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    with _state_lock(repo, "cancel"):
        _, state_path, text, state = _context(repo, args.task)
        _require_revision(state, args.expected_revision)
        if state.get("status") in {"DONE", "CANCELLED"}:
            raise TransitionError("task is already terminal")
        _write_values(
            state_path,
            text,
            {
                ("status",): "CANCELLED",
                ("blocked_reason",): args.authorization,
                ("revision",): args.expected_revision + 1,
            },
        )
    return {"task": args.task, "status": "CANCELLED", "output_revision": args.expected_revision + 1}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--repo", required=True)
    commands = root.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--task", required=True)
    wait = commands.add_parser("wait-user")
    wait.add_argument("--task", required=True)
    wait.add_argument("--expected-revision", type=int, required=True)
    wait.add_argument("--question-file", required=True)
    wait.add_argument("--resume-role", required=True)
    answer = commands.add_parser("answer")
    answer.add_argument("--task", required=True)
    answer.add_argument("--expected-revision", type=int, required=True)
    answer.add_argument("--question-id", required=True)
    answer.add_argument("--answer-file", required=True)
    answer.add_argument("--decision-key")
    answer.add_argument("--decision-value")
    plan = commands.add_parser("plan-done")
    plan.add_argument("--task", required=True)
    plan.add_argument("--expected-revision", type=int, required=True)
    plan.add_argument("--participant-id", required=True)
    plan.add_argument("--plan", required=True)
    plan.add_argument("--approval-ref", required=True)
    plan.add_argument("--progress", required=True)
    implementation = commands.add_parser("implementation-done")
    implementation.add_argument("--task", required=True)
    implementation.add_argument("--expected-revision", type=int, required=True)
    implementation.add_argument("--participant-id", required=True)
    implementation.add_argument("--run-id", required=True)
    implementation.add_argument("--execution", required=True)
    implementation.add_argument("--delivery-ref", required=True)
    implementation.add_argument("--progress", required=True)
    verdict = commands.add_parser("verdict")
    verdict.add_argument("--task", required=True)
    verdict.add_argument("--expected-revision", type=int, required=True)
    verdict.add_argument("--verdict", required=True)
    verdict.add_argument("--evidence", required=True)
    verdict.add_argument("--participant-id", required=True)
    verdict.add_argument("--run-id", required=True)
    verdict.add_argument("--delivery-ref", required=True)
    report = commands.add_parser("report-done")
    report.add_argument("--task", required=True)
    report.add_argument("--expected-revision", type=int, required=True)
    report.add_argument("--report", required=True)
    report.add_argument("--participant-id", required=True)
    report.add_argument("--review-ref", required=True)
    cancel = commands.add_parser("cancel")
    cancel.add_argument("--task", required=True)
    cancel.add_argument("--expected-revision", type=int, required=True)
    cancel.add_argument("--authorization", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    handlers = {
        "status": _status,
        "wait-user": _wait_user,
        "answer": _answer,
        "plan-done": _plan_done,
        "implementation-done": _implementation_done,
        "verdict": _verdict,
        "report-done": _report_done,
        "cancel": _cancel,
    }
    try:
        payload = handlers[args.command](args)
    except (RevisionConflict, TransitionError, StateStoreError) as error:
        print(str(error), file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
