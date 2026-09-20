# Agent Relay Auto Original Planner Auto Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect `REPORTING` locally every 45 seconds, resume the exact registered Planner conversation, request one evidence-based final report, and present that report in the original Codex, OpenCode, Claude Code, or DeepSeek Harness conversation without requiring the user to type “continue”.

**Architecture:** Keep the existing foreground Planner and background Implementer/Reviewer split. Add a project-local Planner Channel store, an append-only wake journal, a non-blocking `ReportingCoordinator`, and tool-specific `PlannerWakeAdapter` implementations; the coordinator records submission receipts before observing or presenting, so UI retries never duplicate model turns. The existing `report-done` transition remains the only path from `REPORTING` to `DONE`.

**Tech Stack:** Python 3 standard library, Markdown fenced YAML state, JSON/JSONL journals, existing Runner/launchd service, `unittest`, CLI fixtures, Codex App Server JSON-RPC, OpenCode CLI, Claude Code CLI, DeepSeek Harness ACP/TUI.

**Spec:** `docs/superpowers/specs/2026-09-20-agent-relay-auto-original-planner-auto-reporting-design.md`

## Global Constraints

- Target version is `v1.8.0`.
- Default project polling interval is exactly `45` seconds.
- Idle polling performs zero model calls.
- A reporting wake always targets an exact registered `thread_id` or `session_id`; it never creates or forks a replacement conversation.
- Runner never writes `DONE`; only the registered Planner may call the guarded `report-done` transition after Reviewer `PASS` evidence exists.
- UI presentation retries never resubmit the reporting prompt.
- `DONE` does not authorize merge, push, release, deploy, deletion, reset, or overwrite operations.
- Cursor is out of scope for this release.
- Codex, OpenCode, Claude Code, and DeepSeek Harness capability labels must reflect real probe/E2E evidence; source compatibility alone is not `verified`.
- Conversation IDs, absolute local paths, PIDs, receipts, and wake journals stay under ignored `.agent-relay-auto/`; portable evidence stays under `docs/agent/`.
- Canonical files live under `shared/.agents/skills/agent-relay-auto/`; the project-template mirror must be regenerated or synchronized before release.

## Review Focus

- Crash after remote submission but before local receipt persistence must reconcile against conversation/task evidence before retrying; Task 4 adds the ambiguity test.
- A moved repository with a stale channel path must refuse the wake and guide re-registration instead of targeting another checkout; Task 1 adds the ownership test.
- A Planner switch during an active reporting turn must be rejected without changing either binding; Task 7 adds the switch-conflict test.
- A completed model turn followed by UI-open failure must keep `DONE` and retry presentation only; Task 8 adds the no-resubmit E2E test.
- Two Runner processes for one project and two projects reaching `REPORTING` concurrently must deduplicate per project without machine-wide serialization; Task 8 adds both concurrency tests.

---

### Task 1: Reporting configuration, Planner Channel, and wake journal

**Files:**
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_channel.py`
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/wake_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/config.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/schema.py`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/.gitignore`
- Test: `tests/test_planner_channel.py`
- Test: `tests/test_wake_store.py`
- Test: `tests/test_runtime_config.py`

**Interfaces:**
- Produces: `ReportingPolicy`, `PlannerChannel`, `PlannerChannelStore.load/save`, `WakeKey`, `WakeEventStore.append/latest/find_submission`.
- Consumes: existing `RuntimeConfig`, Markdown task state fields, and `.agent-relay-auto/` local layout.

- [ ] **Step 1: Write failing configuration and channel tests**

```python
def test_reporting_defaults_are_bounded():
    config = RuntimeConfig.defaults()
    assert config.reporting.poll_interval_seconds == 45
    assert config.reporting.model_retry_limit == 1
    assert config.reporting.presentation_retry_limit == 3
    assert config.reporting.require_same_conversation is True

def test_channel_rejects_repository_move(self):
    channel = PlannerChannel("p", "codex", "thr_1", "/old/repo", "2026-09-20T00:00:00Z")
    with self.assertRaisesRegex(PlannerChannelError, "project_path"):
        channel.validate_for(Path("/new/repo"))
```

- [ ] **Step 2: Run the focused tests and confirm missing-type failures**

Run: `python3 -m unittest tests.test_planner_channel tests.test_wake_store tests.test_runtime_config -v`

Expected: FAIL because `planner_channel`, `wake_store`, and `RuntimeConfig.reporting` do not exist.

- [ ] **Step 3: Implement immutable local records and strict parsing**

```python
@dataclass(frozen=True)
class ReportingPolicy:
    enabled: bool = True
    poll_interval_seconds: float = 45
    reopen_original_conversation: bool = True
    launch_application_if_closed: bool = True
    require_same_conversation: bool = True
    model_retry_limit: int = 1
    presentation_retry_limit: int = 3
    presentation_retry_interval_seconds: float = 10

@dataclass(frozen=True)
class PlannerChannel:
    participant_id: str
    tool: str
    conversation_id: str
    project_path: str
    registered_at: str

@dataclass(frozen=True)
class WakeKey:
    task_id: str
    revision: int
    participant_id: str
    conversation_id: str

    def value(self) -> str:
        return f"{self.task_id}:{self.revision}:{self.participant_id}:{self.conversation_id}"
```

`PlannerChannelStore` must atomically replace `.agent-relay-auto/planner-channel.json`; `WakeEventStore` must append one JSON object per line to `.agent-relay-auto/wake-events.jsonl`, `fsync` before returning, tolerate a missing file, and reject malformed existing lines rather than silently losing idempotency history.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_planner_channel tests.test_wake_store tests.test_runtime_config -v`

Expected: PASS, including malformed journal, duplicate wake key, unsupported tool, empty conversation ID, and moved-project cases.

- [ ] **Step 5: Commit Task 1**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/{planner_channel.py,wake_store.py,config.py,schema.py} shared/.agents/skills/agent-relay-auto/assets/project-template/.gitignore tests/test_planner_channel.py tests/test_wake_store.py tests/test_runtime_config.py
git commit -m "feat: persist planner reporting channels"
```

### Task 2: Planner wake contract and capability factory

**Files:**
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/__init__.py`
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/base.py`
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/factory.py`
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/fake.py`
- Test: `tests/test_planner_wake_contract.py`

**Interfaces:**
- Consumes: `PlannerChannel`, `WakeKey`, project path, task ID, and expected revision from Task 1.
- Produces: `WakeCapabilities`, `WakeRequest`, `SubmissionReceipt`, `ObservationResult`, `PresentationResult`, `PlannerWakeAdapter`, and `create_planner_wake_factory()`.

- [ ] **Step 1: Write the failing adapter-contract tests**

```python
def test_receipt_preserves_remote_identity():
    receipt = SubmissionReceipt("wk", "codex", "thr_1", "turn_9", "submitted")
    assert receipt.conversation_id == "thr_1"
    assert receipt.remote_id == "turn_9"

def test_factory_does_not_fallback_to_another_tool(self):
    factory = create_planner_wake_factory({"codex": lambda: object()})
    with self.assertRaisesRegex(WakeAdapterUnavailable, "opencode"):
        factory("opencode")
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `python3 -m unittest tests.test_planner_wake_contract -v`

Expected: FAIL because the `planner_wake` package does not exist.

- [ ] **Step 3: Implement the exact protocol and fixed reporting prompt**

```python
@dataclass(frozen=True)
class WakeCapabilities:
    resume_original_conversation: str
    submit_turn: str
    reopen_original_ui: str
    end_to_end_reporting: str

@dataclass(frozen=True)
class WakeRequest:
    repo: Path
    task_id: str
    expected_revision: int
    participant_id: str
    wake_key: str

class PlannerWakeAdapter(Protocol):
    def probe(self, channel: PlannerChannel) -> WakeCapabilities: ...
    def resume(self, channel: PlannerChannel) -> None: ...
    def submit_report(self, channel: PlannerChannel, request: WakeRequest) -> SubmissionReceipt: ...
    def observe(self, receipt: SubmissionReceipt) -> ObservationResult: ...
    def present(self, channel: PlannerChannel) -> PresentationResult: ...
```

Add `build_reporting_prompt(request)` with the five approved duties, exact task/revision/wake fields, and explicit prohibitions on product edits, merge, push, release, and deploy. Do not embed conclusions or Reviewer text in this prompt.

- [ ] **Step 4: Run contract tests**

Run: `python3 -m unittest tests.test_planner_wake_contract -v`

Expected: PASS, including capability-label validation and exact-conversation checks.

- [ ] **Step 5: Commit Task 2**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake tests/test_planner_wake_contract.py
git commit -m "feat: define planner wake adapter contract"
```

### Task 3: Codex, OpenCode, and Claude Code Planner bridges

**Files:**
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/codex.py`
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/opencode.py`
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/claude_code.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/factory.py`
- Modify: `tests/fixtures/codex_app_server_fixture.py`
- Modify: `tests/fixtures/opencode_fixture.py`
- Modify: `tests/fixtures/claude_fixture.py`
- Test: `tests/test_planner_wake_cli_bridges.py`

**Interfaces:**
- Consumes: Task 2 `PlannerWakeAdapter` types and fixed prompt.
- Produces: `CodexPlannerWakeAdapter`, `OpenCodePlannerWakeAdapter`, and `ClaudeCodePlannerWakeAdapter` with exact-session submission receipts.

- [ ] **Step 1: Extend fixtures and write failing exact-session tests**

```python
def test_opencode_uses_exact_session_without_fork(adapter, channel, request):
    receipt = adapter.submit_report(channel, request)
    assert receipt.conversation_id == channel.conversation_id
    assert "--session" in receipt.debug_command
    assert "--fork" not in receipt.debug_command

def test_claude_never_uses_continue(adapter, channel, request):
    receipt = adapter.submit_report(channel, request)
    assert "--resume" in receipt.debug_command
    assert "--continue" not in receipt.debug_command
```

The Codex fixture must accept `initialize`, `thread/read`, `thread/resume`, and `turn/start`, emit a stable turn ID, then emit `turn/completed` for that same thread.

- [ ] **Step 2: Run bridge tests and verify failures**

Run: `python3 -m unittest tests.test_planner_wake_cli_bridges -v`

Expected: FAIL because the three Planner bridge modules are absent.

- [ ] **Step 3: Implement Codex JSON-RPC resume and turn submission**

Use the existing newline-delimited JSON-RPC transport pattern in `adapters/codex.py`, but keep a Planner-specific process lifetime long enough to receive `turn/completed`. Verify `thread/read` returns the registered ID before `thread/resume`; return a `SubmissionReceipt` containing the exact thread and turn IDs. `present()` may report `experimental` when exact Codex Desktop navigation cannot be proved; it must not claim success after only `open -a Codex`.

- [ ] **Step 4: Implement exact OpenCode and Claude Code session commands**

OpenCode submission must execute:

```text
opencode run --session SESSION_ID --format json REPORTING_PROMPT
```

OpenCode presentation must execute `opencode PROJECT_PATH --session SESSION_ID`. Claude submission must execute:

```text
claude -p --resume SESSION_ID --output-format json REPORTING_PROMPT
```

Claude presentation must execute `claude --resume SESSION_ID`. Both adapters must parse the returned session identifier and reject a mismatch.

- [ ] **Step 5: Run bridge and pre-existing CLI adapter tests**

Run: `python3 -m unittest tests.test_planner_wake_cli_bridges tests.test_cli_adapters tests.test_adapter_contract -v`

Expected: PASS with no change to background-role command construction.

- [ ] **Step 6: Commit Task 3**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake tests/fixtures/{codex_app_server_fixture.py,opencode_fixture.py,claude_fixture.py} tests/test_planner_wake_cli_bridges.py
git commit -m "feat: wake original planner cli sessions"
```

### Task 4: Durable, non-blocking ReportingCoordinator

**Files:**
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/reporting.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/schema.py`
- Test: `tests/test_reporting_coordinator.py`

**Interfaces:**
- Consumes: `PlannerChannelStore`, `WakeEventStore`, `PlannerWakeAdapter`, task state and `ReportingPolicy`.
- Produces: `ReportingCoordinator.tick(task_id) -> ReportingDecision`, where actions are `report_wake_pending`, `report_submitted`, `report_active`, `report_completed`, `report_presentation_retry`, or `blocked`.

- [ ] **Step 1: Write failing coordinator-state tests**

```python
def test_second_tick_does_not_resubmit_after_receipt(coordinator, adapter):
    assert coordinator.tick("TASK-001").action == "report_submitted"
    assert coordinator.tick("TASK-001").action in {"report_active", "report_completed"}
    assert adapter.submit_count == 1

def test_ambiguous_crash_reconciles_before_retry(coordinator, adapter, wake_store):
    wake_store.append({"wake_key": "wk", "status": "submitting"})
    adapter.remote_has_wake_key = True
    coordinator.tick("TASK-001")
    assert adapter.submit_count == 0
```

- [ ] **Step 2: Run coordinator tests and verify failures**

Run: `python3 -m unittest tests.test_reporting_coordinator -v`

Expected: FAIL because `ReportingCoordinator` is undefined.

- [ ] **Step 3: Implement the non-blocking reporting state machine**

On each tick: validate `REPORTING`, Planner identity, Reviewer `PASS`, current revision, and channel ownership; compute the `WakeKey`; append `submitting` before remote work; persist the receipt as `submitted`; call `observe()` only for an existing receipt; and call `present()` only after the report turn completes or `STATE.md` is `DONE`. A malformed or ambiguous journal must fail closed. No coordinator method may invoke `StateStore.transition(..., "report_completed")`.

- [ ] **Step 4: Add retry and revision-conflict tests**

Cover model failure count `0..model_retry_limit`, presentation attempts `0..presentation_retry_limit`, stale revision, missing channel, wrong project path, mismatched participant, missing Reviewer evidence, and `STATE.md == DONE` before observation.

- [ ] **Step 5: Run coordinator and state tests**

Run: `python3 -m unittest tests.test_reporting_coordinator tests.test_automation_transitions tests.test_stage_completion -v`

Expected: PASS; existing Reviewer transitions still stop at `REPORTING` until Planner calls `report-done`.

- [ ] **Step 6: Commit Task 4**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/{reporting.py,state_store.py,schema.py} tests/test_reporting_coordinator.py
git commit -m "feat: coordinate durable planner reporting wakes"
```

### Task 5: Guard `report-done` with wake identity and Reviewer evidence

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/relay_state.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/tasks/_template/STATE.md`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/tasks/_template/STATE.md`
- Test: `tests/test_relay_state_cli.py`
- Test: `tests/test_stage_completion.py`

**Interfaces:**
- Consumes: persisted `reporting.wake_key`, expected revision, current Planner participant, review reference, and delivery ID.
- Produces: `report-done --wake-key --review-delivery-id` as the only legal automated reporting completion command.

- [ ] **Step 1: Write failing command-guard tests**

```python
def test_report_done_rejects_wrong_wake_key(self):
    result = self.run_cli_expect_failure(
        "report-done", "--task", "TASK-001", "--expected-revision", "9",
        "--participant-id", "planner-a", "--wake-key", "wrong",
        "--review-delivery-id", "delivery-1", "--report", self.report,
        "--review-ref", self.review,
    )
    self.assertIn("wake_key", result.stderr)
```

- [ ] **Step 2: Run focused tests and verify the guard is absent**

Run: `python3 -m unittest tests.test_relay_state_cli tests.test_stage_completion -v`

Expected: FAIL because the CLI does not accept or validate wake identity.

- [ ] **Step 3: Implement atomic report completion validation**

Require matching task, revision, participant, `reporting.wake_key`, Reviewer `PASS`, review reference, delivery ID, and non-empty report. In the same locked CAS write, move the task to `DONE`, clear the active writer/run fields, update project queues, and append the final progress reference. Do not allow Runner identity as Planner participant.

- [ ] **Step 4: Run transition tests**

Run: `python3 -m unittest tests.test_relay_state_cli tests.test_stage_completion tests.test_automation_transitions -v`

Expected: PASS for matching evidence and FAIL without mutation for every mismatched field.

- [ ] **Step 5: Commit Task 5**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/relay_state.py shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py shared/.agents/skills/agent-relay-auto/assets/project-template/locales/{zh-CN,en-US}/docs/agent/tasks/_template/STATE.md tests/test_relay_state_cli.py tests/test_stage_completion.py
git commit -m "feat: bind final reporting to planner wake evidence"
```

### Task 6: DeepSeek Harness bridge with truthful capability gating

**Files:**
- Create: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/deepseek_harness.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/factory.py`
- Create: `tests/fixtures/deepseek_harness_fixture.py`
- Create: `tests/test_deepseek_harness_planner_wake.py`

**Interfaces:**
- Consumes: Task 2 bridge contract and a configured `dsh` executable/profile.
- Produces: `DeepSeekHarnessPlannerWakeAdapter` using ACP/API resume/followup and `dsh --profile tui --resume SESSION_ID` presentation.

- [ ] **Step 1: Write failing ACP/session tests**

```python
def test_dsh_resumes_and_follows_up_exact_session(adapter, channel, request):
    receipt = adapter.submit_report(channel, request)
    assert receipt.conversation_id == channel.conversation_id
    assert receipt.remote_id

def test_static_probe_is_not_verified(adapter, channel):
    adapter.real_session_verified = False
    assert adapter.probe(channel).end_to_end_reporting in {"static_only", "experimental"}
```

- [ ] **Step 2: Run the new tests and verify failure**

Run: `python3 -m unittest tests.test_deepseek_harness_planner_wake -v`

Expected: FAIL because the DeepSeek Harness bridge and fixture do not exist.

- [ ] **Step 3: Implement ACP resume/followup and TUI presentation**

Use a fixture-compatible ACP client command that resumes the supplied session ID, submits exactly one prompt, waits for agent idle, and returns a durable receipt. Presentation must invoke `dsh --profile tui --resume SESSION_ID`; Web presentation remains disabled unless an explicit stable session route probe passes.

- [ ] **Step 4: Run static and optional real-session verification**

Run: `python3 -m unittest tests.test_deepseek_harness_planner_wake -v`

Expected: PASS for the fixture. If `DSH_TEST_SESSION_ID` and real credentials are present, run the key-gated smoke test and record its result; otherwise preserve `static_only`/`experimental` without failing packaging.

- [ ] **Step 5: Commit Task 6**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/{deepseek_harness.py,factory.py} tests/fixtures/deepseek_harness_fixture.py tests/test_deepseek_harness_planner_wake.py
git commit -m "feat: add gated deepseek planner wake bridge"
```

### Task 7: Wire reporting into Runner, configuration, and Planner replacement

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/supervisor.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/runner.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runner.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/configure_runtime.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py`
- Modify: `shared/.agents/skills/agent-relay-auto/scripts/runnerctl.py`
- Test: `tests/test_supervisor.py`
- Test: `tests/test_configure_runtime.py`
- Test: `tests/test_workflow_state.py`
- Test: `tests/test_runnerctl.py`

**Interfaces:**
- Consumes: `ReportingCoordinator`, Planner wake factory, reporting config, and channel store.
- Produces: 45-second default Runner loop, registration/migration summaries, and atomic Planner replacement that updates the local channel only when no reporting turn is active.

- [ ] **Step 1: Replace the old REPORTING expectation with failing wake tests**

```python
def test_reporting_delegates_to_reporting_coordinator(self):
    coordinator = FakeReportingCoordinator(action="report_submitted")
    decision = ProjectSupervisor(repo, background_adapter, reporting=coordinator).tick()
    self.assertEqual(decision.action, "report_submitted")
    self.assertEqual(coordinator.calls, ["TASK-001"])

def test_planning_still_waits_for_foreground_planner(self):
    self.assertEqual(supervisor.tick().action, "waiting_foreground_planner")
```

- [ ] **Step 2: Run Runner/configuration tests and verify failures**

Run: `python3 -m unittest tests.test_supervisor tests.test_configure_runtime tests.test_workflow_state tests.test_runnerctl -v`

Expected: FAIL because `REPORTING` still returns `waiting_foreground_planner` and no channel migration exists.

- [ ] **Step 3: Route only REPORTING through the coordinator**

Keep `PLANNING` unchanged. Construct one `ReportingCoordinator` per project in `RelayRunner._supervisor()`, map reporting actions into notifications, and set both `agent_relay_runner.py` and installed service defaults to 45 seconds while retaining an explicit CLI override for tests and operators.

- [ ] **Step 4: Add conversational configuration and migration outputs**

`configure_runtime.py inspect/apply` must expose Planner tool, masked conversation ID, project path, capability labels, 45-second interval, retry values, and `ready_to_start`. It must never print credentials. When the channel is missing, return a structured action telling the Skill to re-run `$agent-relay-auto continue` in the intended Planner conversation.

- [ ] **Step 5: Guard Planner replacement during active reporting**

Add a test where `reporting.phase: active` and verify `workflow_state.py replace-agent` rejects the operation without changing role bindings or local channel. Add A → B → A coverage after reporting is idle and verify old wake events remain immutable.

- [ ] **Step 6: Run focused integration tests**

Run: `python3 -m unittest tests.test_supervisor tests.test_configure_runtime tests.test_workflow_state tests.test_runnerctl tests.test_runner_integration -v`

Expected: PASS; `PLANNING` remains foreground waiting, while `REPORTING` is automatically coordinated.

- [ ] **Step 7: Commit Task 7**

```bash
git add shared/.agents/skills/agent-relay-auto/scripts tests/test_supervisor.py tests/test_configure_runtime.py tests/test_workflow_state.py tests/test_runnerctl.py tests/test_runner_integration.py
git commit -m "feat: automate foreground planner reporting"
```

### Task 8: End-to-end idempotency, recovery, Token, and concurrency acceptance

**Files:**
- Modify: `tests/test_hybrid_relay_e2e.py`
- Create: `tests/test_planner_reporting_e2e.py`
- Modify: `tests/test_cross_project_concurrency.py`
- Modify: `tests/test_runner_reconciliation.py`
- Modify: `tests/test_redaction.py`

**Interfaces:**
- Consumes: all runtime interfaces from Tasks 1–7.
- Produces: executable acceptance evidence for automatic `REPORTING → DONE` and failure recovery.

- [ ] **Step 1: Write the normal-flow E2E before changing expectations**

```python
def test_reviewer_pass_wakes_original_planner_without_continue(self):
    run_background_roles_until("REPORTING")
    runner.run_once()
    wait_until(lambda: read_state()["status"] == "DONE")
    assert fake_planner.submission_count == 1
    assert fake_planner.created_conversation_count == 0
    assert fake_planner.presented_conversation_id == registered_conversation_id
```

- [ ] **Step 2: Add recovery and no-resubmission E2E cases**

Cover Runner exit before submission, ambiguous exit after remote submission, Planner interruption, application closed, stale revision, quota exhaustion, moved project, and completed report plus failed presentation. Assert the last case is `DONE`, has one model submission, and has bounded presentation retries.

- [ ] **Step 3: Add project-granularity concurrency tests**

Start two Runner objects against one project and assert one `wake_key` submission. Start two projects at `REPORTING` and assert both submit independently without a machine-global lock.

- [ ] **Step 4: Add idle Token accounting and redaction tests**

Run several empty/PLANNING polling cycles and assert zero adapter submissions. Assert logs carry task ID, revision, participant, masked conversation ID, wake key, receipt ID, attempts, and errors, but not credentials, full prompts, or full conversation transcripts.

- [ ] **Step 5: Run the complete runtime suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass; no existing v1.7 foreground Planner, worker recovery, state lock, or background adapter test regresses.

- [ ] **Step 6: Commit Task 8**

```bash
git add tests/test_hybrid_relay_e2e.py tests/test_planner_reporting_e2e.py tests/test_cross_project_concurrency.py tests/test_runner_reconciliation.py tests/test_redaction.py
git commit -m "test: prove original planner auto reporting"
```

### Task 9: Skill instructions, bilingual templates, and synchronized install tree

**Files:**
- Modify: `shared/.agents/skills/agent-relay-auto/SKILL.md`
- Modify: `shared/.agents/skills/agent-relay-auto/references/initialization.md`
- Modify: `shared/.agents/skills/agent-relay-auto/references/runner.md`
- Modify: `shared/.agents/skills/agent-relay-auto/references/protocol.md`
- Modify: `shared/.agents/skills/agent-relay-auto/references/state-helper.md`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/{README.md,protocol.md,workflow.md,integrations.md,automation-policy.yaml}`
- Modify: `shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/{README.md,protocol.md,workflow.md,integrations.md,automation-policy.yaml}`
- Modify: `shared/docs/agent/{README.md,protocol.md,workflow.md,integrations.md}`
- Modify: `docs/AGENT_RELAY_AUTO_USAGE.md`
- Modify: `docs/AGENT_RELAY_AUTO_USAGE.en-US.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `tests/test_agent_relay_contract.py`
- Modify: `tests/shared_dot_agents_skill_loader.py`

**Interfaces:**
- Consumes: final CLI/config names and capability labels from Tasks 1–8.
- Produces: a user-facing initialization/resume/replacement protocol that automatically registers the Planner conversation and explains verified versus experimental support.

- [ ] **Step 1: Add failing template-drift assertions**

Assert both languages contain the four Planner tools, `45`-second default, same-conversation requirement, no-continue normal flow, local ignored channel path, retries, `DONE` boundary, and capability labels. Assert canonical Skill and embedded project-template Skill agree on command names and version.

- [ ] **Step 2: Run contract tests and verify documentation failures**

Run: `python3 -m unittest tests.test_agent_relay_contract tests.shared_dot_agents_skill_loader -v`

Expected: FAIL until every canonical/template/bilingual surface is synchronized.

- [ ] **Step 3: Update the Skill and bilingual instructions**

Initialization must first collect language and roles as before, then detect/register the current Planner conversation, show its masked identity and capability results, and ask for one confirmation before install/start. Continue must migrate missing channels conversationally. Replacement must refuse an active report and rebind the new exact conversation after an idle handoff.

- [ ] **Step 4: Synchronize the embedded Skill/runtime tree**

Copy the finalized canonical `shared/.agents/skills/agent-relay-auto/` content into `assets/project-template/shared/.agents/skills/agent-relay-auto/` using the repository's existing synchronization method, then assert file-by-file parity excluding generated caches.

- [ ] **Step 5: Run documentation and mirror tests**

Run: `python3 -m unittest tests.test_agent_relay_contract tests.shared_dot_agents_skill_loader -v`

Expected: PASS with no canonical/template drift.

- [ ] **Step 6: Commit Task 9**

```bash
git add README.md README.zh-CN.md docs shared tests/test_agent_relay_contract.py tests/shared_dot_agents_skill_loader.py
git commit -m "docs: explain automatic original planner reporting"
```

### Task 10: v1.8.0 release validation, package, and local installation verification

**Files:**
- Modify: `distribution/VERSION`
- Modify: `CHANGELOG.md`
- Modify: `.github/scripts/validate-release.sh`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/verification/automated-runner-v1.8.0.md`
- Generate: `dist/agent-relay-auto-skill-pack-v1.8.0.zip`
- Generate: `dist/agent-relay-auto-skill-pack-v1.8.0.zip.sha256`

**Interfaces:**
- Consumes: completed implementation, full test suite, capability probe records, and synchronized Skill tree.
- Produces: validated v1.8.0 artifacts and a locally installed Skill/Runner parity report; no GitHub push or Release.

- [ ] **Step 1: Extend CI/release checks before changing the version**

Require the four Planner IDs, bridge modules, reporting policy keys, 45-second default, same-conversation wording, bilingual parity, ignored local channel, Skill mirror parity, and truthful DeepSeek Harness capability label.

- [ ] **Step 2: Run release validation and confirm it fails on v1.7.0 metadata**

Run: `bash .github/scripts/validate-release.sh`

Expected: FAIL because release metadata and v1.8.0 verification artifacts are not prepared.

- [ ] **Step 3: Update version, changelog, and verification report**

Record exact test commands/results, per-tool capability status, any key-gated test skipped for missing credentials, package file list, local installation target, and explicit statement that merge/push/release/deploy were not performed.

- [ ] **Step 4: Run complete verification**

Run:

```bash
python3 -m unittest discover -s tests -v
bash .github/scripts/validate-release.sh
git diff --check
```

Expected: all tests and validation pass, with a clean whitespace check.

- [ ] **Step 5: Build deterministic package and checksum**

Use the existing release packager or deterministic ZIP procedure required by `validate-release.sh`, then run:

```bash
shasum -a 256 dist/agent-relay-auto-skill-pack-v1.8.0.zip > dist/agent-relay-auto-skill-pack-v1.8.0.zip.sha256
```

Expected: package and checksum names exactly match v1.8.0.

- [ ] **Step 6: Install locally and verify source/install parity**

Install the packaged Skill and Runner through the documented installer, then compare the installed manifest and hashes against the package. Confirm the service is genuinely healthy, the project polling interval is 45 seconds, an idle polling window makes zero model calls, and no unrelated registered project is awakened for a test.

- [ ] **Step 7: Commit Task 10**

```bash
git add distribution/VERSION CHANGELOG.md .github docs/verification/automated-runner-v1.8.0.md dist/agent-relay-auto-skill-pack-v1.8.0.zip dist/agent-relay-auto-skill-pack-v1.8.0.zip.sha256
git commit -m "release: prepare agent-relay-auto v1.8.0"
```

## Final branch review

- [ ] Compare every section of the approved spec with Tasks 1–10 and confirm no requirement lacks an implementation or test owner.
- [ ] Search the plan and implementation for accidental Cursor support, conversation fallback, `--continue`, `--fork`, direct Runner `DONE`, unmasked IDs in committed files, and model calls in idle polling.
- [ ] Run `python3 -m unittest discover -s tests -v`, `bash .github/scripts/validate-release.sh`, and `git diff --check` again from a clean process.
- [ ] Request a fresh whole-branch review focused on crash ambiguity, exact-conversation guarantees, cross-project concurrency, UI/model retry separation, and truthful capability labels.
- [ ] Apply accepted review findings with focused regression tests and a separate commit.
- [ ] Do not merge, push, create a GitHub Release, or deploy without a new explicit user request.
