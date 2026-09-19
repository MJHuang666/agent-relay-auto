# Agent Relay Auto Foreground Planner Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Planner a foreground-only role while giving background Implementer and Reviewer runs an atomic, durable, restart-safe execution and handoff protocol.

**Architecture:** `ProjectSupervisor` becomes a hybrid scheduler: `PLANNING` and `REPORTING` produce a foreground wait decision, while `IMPLEMENTING` and `REVIEWING` launch durable Run Workers. Role agents receive an explicit launch context and complete stages only through revision-checked `relay_state.py` commands; the supervisor treats process exit and business-stage transition as separate facts and reconciles both after restarts.

**Tech Stack:** Python 3 standard library, Markdown fenced-YAML state files, `unittest`, macOS launchd, Codex/OpenCode/Claude Code CLIs, shell release validation.

**Spec:** `docs/superpowers/specs/2026-09-20-agent-relay-auto-foreground-planner-reliability-design.md`

## Global Constraints

- Work only in `/Volumes/HP P900/mjwork/多agent项目状态共享自动版`; do not modify the original repository.
- Target release is `v1.7.0`.
- Planner is always `execution_mode: foreground`; Runner never launches Planner for `PLANNING`, `REPORTING`, or replanning.
- Implementer and Reviewer default to `execution_mode: background`.
- `STATE.md` and referenced evidence remain the business source of truth; stdout text never decides a verdict or completion.
- Every coordination write uses the repository lock, expected revision, immutable participant identity, and run identity where applicable.
- A background process exit is not a successful role completion unless the business stage made a legal transition with valid evidence.
- `DONE` never authorizes merge, push, release, deploy, deletion, production writes, or risk acceptance.
- One project failure must not stop another registered project.
- Use only Python standard-library runtime dependencies.
- Keep canonical Skill scripts and the bootstrap project-template mirror byte-identical.
- Do not mutate `test-auto-relay2` while implementing the product fix; use temporary test repositories for automated and real acceptance.
- Use `python3 -m unittest discover -s tests -p 'test_*.py' -v`, not pytest.
- Before release validation, remove generated `._*`, `.DS_Store`, and `__pycache__` artifacts without deleting user-owned files.

## Review Focus

- A policy with a foreground Planner whose CLI is missing must still configure and start background Implementer/Reviewer; Task 1 adds this test.
- An Agent that exits 0 without a legal handoff must consume exactly one configured retry and then become `BLOCKED`, never spin; Task 5 adds this test.
- A Runner restart between process launch and exit must recover from durable `process.json`/`exit.json` without a duplicate claim; Task 4 adds this test.
- A user answer with a stale revision or unsupported decision value must produce no decision file and no partial state update; Task 3 adds this test.
- A legitimate stage transition followed by process exit must close the same run idempotently without overwriting a newer role's state; Tasks 3 and 5 add this test.

---

### Task 1: Foreground Planner Policy and Hybrid Dispatch

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/factory.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/configure_runtime.py`
- Modify: `tests/test_runner_service.py`
- Modify: `tests/test_supervisor.py`
- Modify: `tests/test_configure_runtime.py`

**Interfaces:**
- Produces: `RoleAdapterConfiguration.execution_mode: str` with values `foreground|background`.
- Produces: `RoleRoutingAdapter.is_background_role(role: str) -> bool`.
- Produces: `SupervisorDecision(action="waiting_foreground_planner", detail="PLANNING"|"REPORTING", report=True|False)`.
- Consumes later: Task 2 uses resolved background role configuration; Task 5 uses the foreground wait action for notification deduplication.

- [ ] **Step 1: Add failing policy tests for execution modes**

Add tests equivalent to:

```python
def test_missing_execution_mode_uses_hybrid_defaults(self):
    roles = factory.load_agent_policy(self.repo)
    self.assertEqual(roles["planner"].execution_mode, "foreground")
    self.assertEqual(roles["implementer"].execution_mode, "background")
    self.assertEqual(roles["reviewer"].execution_mode, "background")

def test_foreground_planner_does_not_require_an_adapter_builder(self):
    build = factory.create_adapter_factory({"codex": FakeBuilder})
    router = build(self.repo_with_planner_agent("unavailable-gui-tool"))
    self.assertFalse(router.is_background_role("planner"))
```

Add a configuration test asserting generated policy includes exactly one foreground and two background modes.

- [ ] **Step 2: Add failing supervisor tests for foreground waits**

```python
def test_planning_waits_for_foreground_planner_without_starting_process(self):
    decision = supervisor.tick()
    self.assertEqual(decision.action, "waiting_foreground_planner")
    self.assertEqual(decision.detail, "PLANNING")
    self.assertEqual(process_manager.start_calls, [])

def test_reporting_waits_for_foreground_planner_without_starting_process(self):
    write_state(status="REPORTING", current_role="planner")
    decision = supervisor.tick()
    self.assertEqual(decision.action, "waiting_foreground_planner")
    self.assertEqual(process_manager.start_calls, [])
```

- [ ] **Step 3: Run the focused tests and confirm the red state**

Run:

```bash
python3 -m unittest tests.test_runner_service tests.test_supervisor tests.test_configure_runtime -v
```

Expected: failures for missing `execution_mode`, missing `is_background_role`, and Planner still being dispatched.

- [ ] **Step 4: Implement policy parsing and foreground dispatch**

Extend the role dataclass and default resolver:

```python
@dataclass(frozen=True)
class RoleAdapterConfiguration:
    role: str
    participant_id: str
    agent: str
    model: str
    reasoning: str
    validation_status: str
    execution_mode: str

def _execution_mode(role: str, raw: str) -> str:
    value = raw or ("foreground" if role == "planner" else "background")
    if value not in {"foreground", "background"}:
        raise AdapterConfigurationError(f"role {role} has invalid execution_mode {value}")
    if role == "planner" and value != "foreground":
        raise AdapterConfigurationError("planner execution_mode must be foreground")
    return value
```

Only construct/check adapters for roles whose execution mode is `background`. In `ProjectSupervisor.tick()`, return `waiting_foreground_planner` before run claim logic for `PLANNING` and `REPORTING`. Remove those statuses from the background role map.

- [ ] **Step 5: Run focused tests and the existing schema suite**

```bash
python3 -m unittest tests.test_runner_service tests.test_supervisor tests.test_configure_runtime tests.test_automation_schema -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the hybrid scheduling boundary**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/factory.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py \
  shared/.agents/skills/agent-relay-auto/scripts/configure_runtime.py \
  tests/test_runner_service.py tests/test_supervisor.py tests/test_configure_runtime.py
git commit -m "feat: keep planner in foreground"
```

### Task 2: Explicit Launch Context and Role-Specific Prompts

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/base.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/factory.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/codex.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/opencode.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/claude_code.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/run_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py`
- Modify: `tests/test_cli_adapters.py`
- Modify: `tests/test_run_store.py`
- Create: `tests/test_launch_context.py`

**Interfaces:**
- Produces: immutable `LaunchContext` dataclass and `LaunchContext.as_dict()`.
- Produces: `RunStore.write_launch_context(run_id: str, context: Mapping[str, object]) -> Path`.
- Produces: `build_role_prompt(request: LaunchRequest, context: LaunchContext) -> str`.
- Consumes: role configuration and foreground policy from Task 1.
- Consumed later: Run Worker and reconciliation use `launch-context.json` as durable input evidence.

- [ ] **Step 1: Write failing launch-context tests**

```python
def test_context_identifies_current_run_as_writer(self):
    context = LaunchContext.from_state(request, state)
    self.assertEqual(context.run_id, "run-1")
    self.assertEqual(context.writer_session, "run-1")
    self.assertEqual(context.start_revision, 8)
    self.assertEqual(context.subagent_policy, "DO_NOT_USE")

def test_prompt_contains_identity_evidence_and_completion_command(self):
    prompt = build_role_prompt(request, context)
    for value in ("implementer-codex", "run-1", "writer_session", "implementation-done"):
        self.assertIn(value, prompt)
    self.assertIn("not a foreign writer", prompt)
```

Add one test per CLI adapter asserting it embeds the same role prompt, while preserving model/reasoning flags. Assert Codex retains `--ephemeral` but the test name describes it as session-persistence control, not lifecycle control.

- [ ] **Step 2: Run tests and confirm the generic prompt fails them**

```bash
python3 -m unittest tests.test_launch_context tests.test_cli_adapters tests.test_run_store -v
```

Expected: failures because the current prompt contains only task and role, and no launch context file exists.

- [ ] **Step 3: Implement the context model and prompt builder**

Add these concrete types:

```python
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

def build_role_prompt(request: LaunchRequest, context: LaunchContext) -> str:
    return (
        f"You are {context.participant_id}, serving role {context.role} for {context.task_id}.\n"
        f"This Runner turn is {context.run_id}. STATE.md writer_session must equal that value.\n"
        "When it matches, it is your lease and not a foreign writer.\n"
        f"Re-read revision {context.start_revision} or newer before writing.\n"
        f"Complete the stage with: {context.completion_command}\n"
        "A final chat response alone does not complete the stage."
    )
```

The prompt must instruct the Agent to re-read state before the completion CAS, treat only an unequal non-null writer as foreign, and never infer completion from its final chat response.

- [ ] **Step 4: Persist context before starting the process**

In the supervisor sequence use:

```python
claim = self.store.claim(key, run_id)
context = LaunchContext.from_state(request, self.store.read_task(task_id))
self.run_store.create(metadata)
self.run_store.write_launch_context(run_id, context.as_dict())
command = self.adapter.build_command(request, context)
```

If context writing or command construction fails after claim, call the Task 5 rollback/failure path rather than leaving a running lease. Until Task 5 exists, add a private `_abort_unstarted_claim()` that clears only the matching run ID.

- [ ] **Step 5: Run focused tests**

```bash
python3 -m unittest tests.test_launch_context tests.test_cli_adapters tests.test_run_store tests.test_supervisor -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the explicit run identity contract**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/run_store.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py \
  tests/test_cli_adapters.py tests/test_run_store.py tests/test_launch_context.py
git commit -m "feat: pass durable launch context to role agents"
```

### Task 3: Atomic Decisions and Stage Completion Commands

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/relay_state.py`
- Modify: `tests/test_automation_transitions.py`
- Modify: `tests/test_relay_state_cli.py`
- Create: `tests/test_stage_completion.py`

**Interfaces:**
- Produces: `StateStore.complete_stage(task_id, expected_revision, role, participant_id, run_id, event, evidence) -> TransitionResult`.
- Produces CLI commands: `plan-done`, `implementation-done`, enhanced `answer`, enhanced `verdict`, existing `report-done`.
- Produces: automatic-mode handoff semantics where stage transition retains the matching background run lease until process exit.
- Consumed later: Task 5 compares start status with the transition written by these commands.

- [ ] **Step 1: Add failing atomic-answer tests**

```python
def test_subagent_answer_updates_decision_and_policy_atomically(self):
    result = run_answer(
        expected_revision=5,
        decision_key="subagent_policy",
        decision_value="DO_NOT_USE",
    )
    state = read_state()
    self.assertEqual(state["subagent_policy"], "DO_NOT_USE")
    self.assertEqual(state["subagent_decision_ref"], result["answer_ref"])

def test_invalid_or_stale_answer_leaves_no_partial_artifacts(self):
    run_answer(expected_revision=4, decision_value="MAYBE", expected_exit=2)
    self.assertEqual(list(decisions_dir.glob("*")), [])
    self.assertEqual(read_state()["revision"], 5)
```

- [ ] **Step 2: Add failing stage-completion tests**

Cover these exact cases; each helper creates all required evidence unless the test intentionally removes one item:

```python
def test_implementation_done_requires_same_participant_run_and_evidence():
    result = implementation_done(participant="other", run_id="run-1")
    self.assertEqual(result.returncode, 3)
    self.assertEqual(read_state()["status"], "IMPLEMENTING")

def test_implementation_done_moves_to_reviewer_but_keeps_run_lease():
    implementation_done(participant="impl-a", run_id="run-1", expected=5)
    self.assertEqual(read_state()["status"], "REVIEWING")
    self.assertEqual(read_state()["run_id"], "run-1")

def test_review_pass_moves_to_foreground_reporting_and_keeps_reviewer_lease():
    reviewer_pass(participant="reviewer-a", run_id="run-2", expected=9)
    self.assertEqual(read_state()["status"], "REPORTING")
    self.assertEqual(read_state()["run_id"], "run-2")

def test_plan_done_rejects_wrong_planner_or_missing_plan():
    plan_path.unlink()
    self.assertEqual(plan_done(participant="planner-a").returncode, 2)

def test_report_done_rejects_missing_review_pass_reference():
    self.assertEqual(report_done(review_ref="missing.md").returncode, 2)

def test_completion_is_all_or_nothing_on_stale_revision():
    before = state_path.read_bytes()
    self.assertEqual(implementation_done(expected=4).returncode, 3)
    self.assertEqual(state_path.read_bytes(), before)
```

The successful Implementer assertion must include:

```python
self.assertEqual(state["status"], "REVIEWING")
self.assertEqual(state["current_role"], "reviewer")
self.assertEqual(state["run_id"], "run-impl-1")
self.assertEqual(state["writer_session"], "run-impl-1")
self.assertEqual(state["code_delivery_ref"], "execution.md#delivery-1")
```

- [ ] **Step 3: Run transition tests and confirm failures**

```bash
python3 -m unittest tests.test_relay_state_cli tests.test_automation_transitions tests.test_stage_completion -v
```

Expected: missing commands, missing policy synchronization, and incomplete handoff updates fail.

- [ ] **Step 4: Implement the stage-completion transaction**

Add a typed evidence object and allowlisted transitions:

```python
@dataclass(frozen=True)
class StageEvidence:
    progress_ref: str
    delivery_ref: str | None = None
    review_ref: str | None = None
    report_ref: str | None = None

_ROLE_EVENTS = {
    ("planner", "plan_completed"): ("PLANNING", "IMPLEMENTING", "implementer"),
    ("implementer", "implementation_completed"): ("IMPLEMENTING", "REVIEWING", "reviewer"),
    ("reviewer", "review_passed"): ("REVIEWING", "REPORTING", "planner"),
    ("reviewer", "changes_requested"): ("REVIEWING", "IMPLEMENTING", "implementer"),
    ("reviewer", "replan_required"): ("REVIEWING", "PLANNING", "planner"),
    ("planner", "report_completed"): ("REPORTING", "DONE", "planner"),
}
```

Inside one `_state_lock`, validate state and referenced files, create the progress/decision artifact using atomic replacement, update Task State, then update `PROJECT_STATUS.md`. If any validation fails, write nothing.

- [ ] **Step 5: Expose concrete CLI arguments**

The parsers must require these inputs:

```text
plan-done --task ID --expected-revision N --participant-id ID --plan FILE --approval-ref REF --progress FILE
implementation-done --task ID --expected-revision N --participant-id ID --run-id ID --execution FILE --delivery-ref REF --progress FILE
answer --task ID --expected-revision N --question-id ID --answer-file FILE --decision-key subagent_policy --decision-value USE|DO_NOT_USE
verdict --task ID --expected-revision N --participant-id ID --run-id ID --verdict PASS|CHANGES_REQUESTED|REPLAN_REQUIRED|BLOCKED --evidence FILE --delivery-ref REF
report-done --task ID --expected-revision N --participant-id ID --report FILE --review-ref REF
```

- [ ] **Step 6: Run focused and workflow tests**

```bash
python3 -m unittest tests.test_relay_state_cli tests.test_automation_transitions tests.test_stage_completion tests.test_workflow_state -v
```

Expected: all selected tests pass, including all-or-nothing stale revision cases.

- [ ] **Step 7: Commit atomic workflow transitions**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py \
  shared/.agents/skills/agent-relay-auto/scripts/relay_state.py \
  tests/test_automation_transitions.py tests/test_relay_state_cli.py tests/test_stage_completion.py
git commit -m "feat: add atomic role completion commands"
```

### Task 4: Durable Run Worker and Restart Evidence

**Files:**
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/run_worker.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/process_manager.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/run_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/recovery.py`
- Modify: `tests/test_process_manager.py`
- Modify: `tests/test_run_store.py`
- Modify: `tests/test_runner_reconciliation.py`
- Create: `tests/fixtures/sleeping_agent_cli.py`
- Create: `tests/test_run_worker.py`

**Interfaces:**
- Produces: `RunWorkerSpec` and a `python3 run_worker.py --run-dir PATH -- COMMAND ARGUMENTS` entry point.
- Produces: `RunStore.read_process(run_id)`, `read_exit(run_id)`, and `mark_protocol_result(run_id, result)`.
- Produces: `ProcessManager.start_worker(command, cwd, run_dir, runtime) -> ManagedProcess`.
- Produces: `RecoveryManager.reconcile(run, process_observation, exit_record) -> ReconcileResult`.
- Consumed later: Task 5 uses Worker evidence for timeouts, retries and restart reconciliation.

- [ ] **Step 1: Add failing worker persistence tests**

```python
def test_worker_writes_process_heartbeat_logs_and_exit_atomically(self):
    result = run_worker((sys.executable, fixture, "--exit", "7"))
    self.assertEqual(json_load("exit.json")["exit_code"], 7)
    self.assertIn("fixture stdout", read("stdout.log"))
    self.assertIn("fixture stderr", read("stderr.log"))
    self.assertGreater(json_load("heartbeat.json")["sequence"], 0)
    self.assertIn("command_sha256", json_load("process.json"))
```

Add a test that terminates the parent supervisor fixture while leaving the Worker alive, then verifies the Worker still writes `exit.json`.

- [ ] **Step 2: Add failing reconciliation tests**

Cover exact outcomes:

```python
def test_exit_record_wins_after_runner_restart():
    self.assertEqual(reconcile(exit_record={"run_id": "run-1", "exit_code": 0}).status, "finish")

def test_matching_live_worker_is_monitored_without_new_claim():
    self.assertEqual(reconcile(process_exists=True, observed_started_at=10.0).status, "monitor")

def test_missing_worker_without_exit_becomes_interrupted_unknown_exit():
    self.assertEqual(reconcile(process_exists=False, exit_record=None).status, "interrupted")

def test_pid_start_mismatch_is_blocked_as_possible_pid_reuse():
    self.assertEqual(reconcile(process_exists=True, observed_started_at=11.0).status, "blocked")
```

- [ ] **Step 3: Run worker and reconciliation tests to confirm failures**

```bash
python3 -m unittest tests.test_run_worker tests.test_process_manager tests.test_run_store tests.test_runner_reconciliation -v
```

Expected: failures for missing Worker files and restart outcomes.

- [ ] **Step 4: Implement the Worker with atomic JSON writes**

Use this public shape:

```python
@dataclass(frozen=True)
class RunWorkerSpec:
    run_id: str
    run_dir: Path
    cwd: Path
    command: Sequence[str]
    heartbeat_interval_seconds: int

def execute(spec: RunWorkerSpec) -> int:
    with (spec.run_dir / "stdout.log").open("a", encoding="utf-8") as stdout_handle, \
         (spec.run_dir / "stderr.log").open("a", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            list(spec.command), cwd=spec.cwd, stdin=subprocess.DEVNULL,
            stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True,
        )
        atomic_write_process_record(spec, process)
        sequence = 0
        while process.poll() is None:
            atomic_write_heartbeat(spec, process, sequence)
            sequence += 1
            time.sleep(spec.heartbeat_interval_seconds)
        atomic_write_exit_record(spec, process.returncode, "exit")
        return int(process.returncode)
```

Write JSON through a temporary file in the same directory, `fsync`, and `os.replace`. `process.json` records Worker PID, Agent PID, process-group ID, ISO start time, monotonic start value and SHA-256 of the argument vector. Never write raw secrets or environment contents.

- [ ] **Step 5: Make ProcessManager start and identify Workers**

`ManagedProcess` must track the Worker, not depend on pipe drains. `poll()` reads `exit.json`; `interrupt()` verifies run ID, PID start identity and process group before signaling. Keep log redaction at Agent output boundaries and retain bounded log rotation.

- [ ] **Step 6: Implement restart reconciliation**

Use the order:

```python
if exit_record_matches_run:
    return ReconcileResult("finish", exit_record["termination_reason"])
if process_identity.matches:
    return ReconcileResult("monitor", "durable worker is alive")
if process_identity.possible_pid_reuse:
    return ReconcileResult("blocked", "PID identity mismatch")
if run.get("remote"):
    return ReconcileResult("blocked", "remote task may still be running")
return ReconcileResult("interrupted", "worker stopped without exit record")
```

- [ ] **Step 7: Run the focused lifecycle tests**

```bash
python3 -m unittest tests.test_run_worker tests.test_process_manager tests.test_run_store tests.test_runner_reconciliation -v
```

Expected: all selected tests pass without orphan processes.

- [ ] **Step 8: Commit durable process evidence**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/run_worker.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/process_manager.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/run_store.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/recovery.py \
  tests/test_run_worker.py tests/test_process_manager.py tests/test_run_store.py \
  tests/test_runner_reconciliation.py tests/fixtures/sleeping_agent_cli.py
git commit -m "feat: persist background run lifecycle"
```

### Task 5: Protocol Failure, Retry, Timeout and Idempotent Finalization

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/config.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/runner.py`
- Modify: `tests/test_runtime_config.py`
- Modify: `tests/test_supervisor.py`
- Modify: `tests/test_interrupt_recovery.py`
- Modify: `tests/test_cross_project_concurrency.py`
- Create: `tests/test_protocol_failure.py`

**Interfaces:**
- Produces: `RuntimeLimits(agent_timeout_minutes=30, heartbeat_interval_seconds=10, heartbeat_stale_seconds=45, interrupt_grace_seconds=30)`.
- Produces: `StateStore.finish_run(task_id: str, run_id: str, exit_code: int, start_status: str, termination_reason: str) -> RunFinalization` with idempotent outcomes `completed|retry|blocked|already_finalized`.
- Produces: `SupervisorDecision` actions `protocol_failure`, `retry_scheduled`, `blocked`, `finished`.
- Consumes: atomic stage transitions from Task 3 and durable Worker evidence from Task 4.

- [ ] **Step 1: Add failing runtime-limit tests**

```python
def test_runtime_limit_defaults_are_bounded(self):
    limits = RuntimeLimits()
    self.assertEqual(limits.agent_timeout_minutes, 30)
    self.assertEqual(limits.heartbeat_interval_seconds, 10)
    self.assertEqual(limits.heartbeat_stale_seconds, 45)
    self.assertEqual(limits.interrupt_grace_seconds, 30)

def test_invalid_runtime_limits_are_rejected(self):
    with self.assertRaises(ConfigError):
        RuntimeLimits(agent_timeout_minutes=0)
```

- [ ] **Step 2: Add failing no-handoff and retry tests**

```python
def test_exit_zero_without_transition_retries_once_then_blocks(self):
    first = run_role_that_exits_zero_without_state_change()
    self.assertEqual(first.action, "retry_scheduled")
    second = run_role_that_exits_zero_without_state_change()
    self.assertEqual(second.action, "blocked")
    self.assertIn("protocol_failure: no_handoff", read_state()["blocked_reason"])
    self.assertEqual(count_runs(), 2)

def test_legal_transition_then_exit_finalizes_idempotently(self):
    complete_implementation(run_id="run-1")
    first = supervisor.tick_after_exit("run-1", 0)
    second = store.finish_run(task_id, "run-1", 0, "IMPLEMENTING", "exit")
    self.assertEqual(first.action, "finished")
    self.assertTrue(second.idempotent_replay)
```

- [ ] **Step 3: Add failing timeout and cross-project tests**

Assert a timed-out Worker receives interrupt then termination, its matching writer clears, and it retries/blocks according to policy. Register a second healthy repository and assert its decision is still returned in the same `RelayRunner.run_once()` call.

- [ ] **Step 4: Run focused tests and confirm failures**

```bash
python3 -m unittest tests.test_runtime_config tests.test_protocol_failure \
  tests.test_interrupt_recovery tests.test_cross_project_concurrency tests.test_supervisor -v
```

Expected: failures for missing limits, no-handoff classification, and durable retry logic.

- [ ] **Step 5: Implement business/process result comparison**

Add:

```python
@dataclass(frozen=True)
class RunFinalization:
    action: str
    task_id: str
    run_id: str
    input_revision: int
    output_revision: int
    idempotent_replay: bool = False

def classify_run_result(start_status: str, current_status: str, exit_code: int, termination_reason: str) -> str:
    if current_status != start_status:
        return "completed"
    if termination_reason == "timeout":
        return "timeout"
    if exit_code == 0:
        return "protocol_failure"
    return "agent_failure"
```

Only clear `run_id`/`writer_session` when they equal the finalized run. Store `last_finished_run_id` and `last_run_result` so replay is idempotent. If a newer run owns the state, return/raise a conflict and transition to audited `BLOCKED` without clearing it.

- [ ] **Step 6: Apply bounded failure policy**

For protocol, process, timeout and interrupted failures:

1. increment `agent_failure_count` once per unique run;
2. if count is within `max_agent_retries`, finish the lease and permit one new claim;
3. otherwise set `status: BLOCKED`, write reason, unblock condition and run-log reference;
4. never count `CHANGES_REQUESTED` as Agent failure;
5. never generate more than one replacement run for the same failed run result.

- [ ] **Step 7: Run focused tests**

```bash
python3 -m unittest tests.test_runtime_config tests.test_protocol_failure \
  tests.test_interrupt_recovery tests.test_cross_project_concurrency tests.test_supervisor -v
```

Expected: all selected tests pass and process-fixture cleanup leaves no running fixture PIDs.

- [ ] **Step 8: Commit bounded failure handling**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/config.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/runner.py \
  tests/test_runtime_config.py tests/test_protocol_failure.py tests/test_interrupt_recovery.py \
  tests/test_cross_project_concurrency.py tests/test_supervisor.py
git commit -m "fix: bound failed background role runs"
```

### Task 6: Notification Deduplication, Migration and Health Reporting

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/notifications.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/runner.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/configure_runtime.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/runnerctl.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/setup_runner.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_configure_runtime.py`
- Modify: `tests/test_runnerctl.py`
- Modify: `tests/test_runner_installer.py`
- Create: `tests/test_v17_migration.py`

**Interfaces:**
- Produces: `NotificationKey(project, task_id, state, revision)` and project-local notification event records.
- Produces: `runnerctl status` fields `workflow_status`, `runner_action`, `active_run`, `last_run_result`, `attention_required`.
- Produces: v1.7 preflight result `safe_to_upgrade|wait_for_active_run|repair_required`.

- [ ] **Step 1: Add failing notification-dedup tests**

```python
def test_foreground_wait_notifies_once_per_revision(self):
    runner.run_once()
    runner.run_once()
    self.assertEqual(len(notifier.events), 1)
    bump_revision()
    runner.run_once()
    self.assertEqual(len(notifier.events), 2)
```

Assert event records contain project, task, state, revision and state path, but no model output or environment values.

- [ ] **Step 2: Add failing migration and health tests**

Cover:

```python
def test_old_policy_migrates_to_foreground_planner_defaults():
    self.assertEqual(load_agent_policy(old_repo)["planner"].execution_mode, "foreground")

def test_live_legacy_background_planner_blocks_upgrade_without_killing_it():
    result = installer.preflight(project_with_live_planner)
    self.assertEqual(result.status, "wait_for_active_run")
    self.assertTrue(fake_process.is_running)

def test_stopped_legacy_planner_lease_requires_explicit_repair():
    self.assertEqual(installer.preflight(project_with_stale_planner).status, "repair_required")

def test_status_reports_waiting_foreground_planner_as_healthy_attention():
    result = controller.status(reporting_repo)
    self.assertEqual(result["runner_action"], "waiting_foreground_planner")
    self.assertTrue(result["attention_required"])

def test_status_exposes_protocol_failure_log_path():
    result = controller.status(blocked_repo)
    self.assertEqual(result["last_run_result"], "protocol_failure")
    self.assertTrue(Path(result["run_log"]).is_absolute())
```

- [ ] **Step 3: Run focused tests and confirm failures**

```bash
python3 -m unittest tests.test_notifications tests.test_configure_runtime \
  tests.test_runnerctl tests.test_runner_installer tests.test_v17_migration -v
```

Expected: missing deduplication, migration preflight and health fields fail.

- [ ] **Step 4: Implement revision-keyed notifications**

Persist the last emitted keys under `.agent-relay-auto/notifications.jsonl`. Runner reports these actions:

```python
ATTENTION_ACTIONS = {
    "waiting_foreground_planner",
    "waiting_user",
    "blocked",
    "done",
    "project_error",
}
```

Do not notify repeatedly until state or revision changes.

- [ ] **Step 5: Implement v1.7 upgrade preflight**

Before replacing the installed runtime:

1. inspect registered projects;
2. detect active Planner/Implementer/Reviewer runs;
3. refuse automatic upgrade when a live background Planner exists;
4. refuse stale-writer cleanup without an explicit repair operation;
5. permit upgrade when no run is active;
6. never mutate task state during package installation.

- [ ] **Step 6: Improve `runnerctl status`**

Return stable JSON such as:

```json
{
  "status": "running",
  "workflow_status": "REPORTING",
  "runner_action": "waiting_foreground_planner",
  "active_run": null,
  "last_run_result": "completed",
  "attention_required": true
}
```

`waiting_foreground_planner` is a healthy workflow wait, not a service failure.

- [ ] **Step 7: Run focused tests**

```bash
python3 -m unittest tests.test_notifications tests.test_configure_runtime \
  tests.test_runnerctl tests.test_runner_installer tests.test_v17_migration -v
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit notification and migration behavior**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/notifications.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/runner.py \
  shared/.agents/skills/agent-relay-auto/scripts/configure_runtime.py \
  shared/.agents/skills/agent-relay-auto/scripts/runnerctl.py \
  shared/.agents/skills/agent-relay-auto/scripts/setup_runner.py \
  tests/test_notifications.py tests/test_configure_runtime.py tests/test_runnerctl.py \
  tests/test_runner_installer.py tests/test_v17_migration.py
git commit -m "feat: report foreground waits and safe upgrades"
```

### Task 7: Hybrid End-to-End Workflow

**Files:**
- Modify: `tests/fixtures/fake_agent_cli.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/fake.py`
- Rewrite: `tests/test_automated_relay_e2e.py`
- Modify: `tests/test_runner_integration.py`
- Create: `tests/test_hybrid_relay_e2e.py`

**Interfaces:**
- Consumes all Task 1–6 public interfaces.
- Produces no new runtime API; it proves the integrated state machine and safety boundary.

- [ ] **Step 1: Replace the old all-background E2E expectation with a failing hybrid test**

The test must explicitly simulate foreground actions:

```python
def test_foreground_planner_background_roles_foreground_report_reaches_done(self):
    self.assertEqual(runner.run_once()[0].action, "waiting_foreground_planner")
    planner_cli("plan-done", revision=1)
    drain_until_status("REVIEWING")
    drain_until_status("REPORTING")
    self.assertEqual(runner.run_once()[0].action, "waiting_foreground_planner")
    self.assertEqual(background_runs_by_role(), ["implementer", "reviewer"])
    planner_cli("report-done", current_revision())
    self.assertEqual(read_state()["status"], "DONE")
```

- [ ] **Step 2: Add end-to-end failure branches**

Create deterministic fixture modes covering:

- Reviewer `CHANGES_REQUESTED`, one Implementer repair, then PASS;
- Reviewer `REPLAN_REQUIRED`, followed by foreground Planner replan;
- Implementer waits for subagent choice and resumes after atomic `DO_NOT_USE` answer;
- Runner object is destroyed/recreated while Worker continues;
- exit 0 without handoff retries once and then `BLOCKED`;
- second repository continues while the first is blocked.

- [ ] **Step 3: Run E2E tests and confirm initial failures**

```bash
python3 -m unittest tests.test_automated_relay_e2e tests.test_hybrid_relay_e2e tests.test_runner_integration -v
```

Expected: old Fake Adapter assumptions or remaining integration gaps fail before fixture/runtime adjustments.

- [ ] **Step 4: Update Fake Adapter to use the same completion surface**

Fake background roles must execute `relay_state.py implementation-done` or `verdict` with fixture evidence. Remove Fake Adapter logic that auto-transitions `PLANNING` or `REPORTING`; foreground test helpers own those transitions.

- [ ] **Step 5: Run E2E and all unit tests**

```bash
python3 -m unittest tests.test_automated_relay_e2e tests.test_hybrid_relay_e2e tests.test_runner_integration -v
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass, no fixture process remains running, and no E2E run contains role `planner`.

- [ ] **Step 6: Commit the integrated hybrid loop**

```bash
git add tests/fixtures/fake_agent_cli.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/fake.py \
  tests/test_automated_relay_e2e.py tests/test_hybrid_relay_e2e.py tests/test_runner_integration.py
git commit -m "test: verify hybrid automatic relay loop"
```

### Task 8: Skill, Templates, Documentation, Packaging and Installed Verification

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/SKILL.md`
- Modify: `shared/.agents/skills/agent-relay-auto/references/protocol.md`
- Modify: `shared/.agents/skills/agent-relay-auto/references/runner.md`
- Modify: `shared/docs/agent/protocol.md`
- Modify: `shared/docs/agent/workflow.md`
- Modify: `shared/docs/agent/automation-design.md`
- Modify: `shared/docs/agent/automation-policy.md`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/automation-policy.yaml`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/automation-policy.yaml`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/AGENT_RELAY_AUTO_USAGE.md`
- Modify: `docs/AGENT_RELAY_AUTO_USAGE.en-US.md`
- Modify: `CHANGELOG.md`
- Modify: `distribution/VERSION`
- Modify: `.github/scripts/validate-release.sh`
- Modify: `.github/workflows/ci.yml`
- Mirror: `shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/`
- Create: `docs/verification/automated-runner-v1.7.0.md`
- Generate: `dist/agent-relay-auto-skill-pack-v1.7.0.zip`
- Generate: `dist/agent-relay-auto-skill-pack-v1.7.0.zip.sha256`

**Interfaces:**
- Consumes all runtime behavior and verified command syntax from Tasks 1–7.
- Produces v1.7.0 Skill source, bootstrap mirror, bilingual user guidance, release artifacts and installed local runtime.

- [ ] **Step 1: Add failing contract checks to release validation**

Extend validation so it fails unless canonical and mirrored content contains:

```text
execution_mode: foreground
waiting_foreground_planner
implementation-done
protocol_failure: no_handoff
heartbeat_stale_seconds
```

Also fail if user-facing documentation says Runner automatically starts Planner or implies `--ephemeral` provides lifecycle completion.

- [ ] **Step 2: Run release validation and confirm the red state**

```bash
bash .github/scripts/validate-release.sh
```

Expected: failure because docs, templates, version and archive still describe v1.6.3 behavior.

- [ ] **Step 3: Update canonical Skill and bilingual documentation**

Document the exact user experience:

```text
Planner 前台沟通与交付
  → Runner 后台 Implementer
  → Runner 后台 Reviewer
  → Planner 前台总结
```

State that minimizing Planner does not stop background roles, but `PLANNING`, `REPORTING`, `WAITING_USER` and `BLOCKED` wait for foreground action. Document run files, timeouts, recovery, status JSON, repair boundaries and the fact that `--ephemeral` controls session persistence only.

- [ ] **Step 4: Update project templates and mirror runtime files**

Add runtime defaults:

```yaml
runtime:
  agent_timeout_minutes: 30
  heartbeat_interval_seconds: 10
  heartbeat_stale_seconds: 45
  interrupt_grace_seconds: 30
```

Add the three role execution modes. Copy canonical Skill runtime files into the project-template shared Skill mirror, then verify byte equality using the release script rather than manual visual comparison.

- [ ] **Step 5: Update version and changelog**

Set `distribution/VERSION` to `1.7.0`. Record foreground Planner, atomic decisions/completion, durable Worker recovery, bounded no-handoff retries and migration behavior in `CHANGELOG.md`.

- [ ] **Step 6: Run complete source verification**

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash .github/scripts/validate-release.sh
git diff --check
```

Expected: zero test failures, release validation success and no whitespace errors.

- [ ] **Step 7: Build and checksum the v1.7.0 package**

Use the repository's existing packaging command from `validate-release.sh`, then verify:

```bash
shasum -a 256 -c dist/agent-relay-auto-skill-pack-v1.7.0.zip.sha256
unzip -t dist/agent-relay-auto-skill-pack-v1.7.0.zip
```

Expected: checksum `OK` and archive test with no errors.

- [ ] **Step 8: Install Skill and Runner v1.7.0 locally**

Use versioned installation, never edit `~/.local/share/agent-relay-auto/current` in place:

```bash
python3 shared/.agents/skills/agent-relay-auto/scripts/setup_runner.py upgrade \
  --source-skill shared/.agents/skills/agent-relay-auto \
  --version 1.7.0
```

Synchronize the global Skill through the repository's established install procedure, then compare source and installed manifests. Do not start or register `test-auto-relay2` during this step.

- [ ] **Step 9: Perform isolated real-session acceptance**

Create a temporary repository outside the source tree, initialize it with Planner foreground and background role CLIs, and verify:

1. Runner reports `waiting_foreground_planner` without a Planner process.
2. Foreground `plan-done` starts exactly one Implementer.
3. Implementer recognizes its own run ID and writes a valid delivery transition.
4. Reviewer runs independently and writes PASS evidence.
5. Runner returns to `waiting_foreground_planner` without a Planner process.
6. Foreground `report-done` reaches `DONE`.
7. No merge, push, release or deploy side effect exists.

If real credentials are unavailable for an adapter, record that adapter as `pending real-session verification`; do not claim it passed.

- [ ] **Step 10: Verify installed service and logs**

For the isolated project only:

```bash
python3 "$HOME/.local/share/agent-relay-auto/current/scripts/runnerctl.py" status --repo "$ISOLATED_REPO"
launchctl print "gui/$(id -u)/com.agent-relay-auto.runner"
```

Confirm active service state, correct v1.7.0 symlink/manifest, foreground wait action, no crash loop and no new unexpected stderr. Stop/unregister the temporary project after evidence capture.

- [ ] **Step 11: Write verification evidence and rerun release checks**

Record commands, exit codes, role run list, state revisions, log paths, archive hash, installed version and any unverified adapter in `docs/verification/automated-runner-v1.7.0.md`. Then rerun:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash .github/scripts/validate-release.sh
git diff --check
git status --short
```

- [ ] **Step 12: Commit release artifacts without pushing**

```bash
git add shared README.md README.zh-CN.md docs CHANGELOG.md distribution/VERSION \
  .github tests dist/agent-relay-auto-skill-pack-v1.7.0.zip \
  dist/agent-relay-auto-skill-pack-v1.7.0.zip.sha256
git commit -m "release: prepare agent-relay-auto v1.7.0"
```

Do not push GitHub and do not create a GitHub Release unless the user asks separately.

## Final Whole-Branch Review

- [ ] Compare the implementation against every section of the approved spec.
- [ ] Inspect the complete branch diff from commit `28d89a1` to `HEAD`.
- [ ] Confirm no background run has role `planner`.
- [ ] Confirm every coordination command fails closed on stale revision, wrong participant and wrong run ID.
- [ ] Confirm Worker restart recovery does not duplicate claims.
- [ ] Confirm `test-auto-relay2` was not modified.
- [ ] Confirm the original repository `/Volumes/HP P900/mjwork/多agent项目状态共享` was not modified.
- [ ] Run the full source, release, package and installed-service verification one final time.
- [ ] Report local commits, changed files, tests, archive SHA-256, installed version, real-session evidence and remaining limitations; do not report push/release/deploy.
