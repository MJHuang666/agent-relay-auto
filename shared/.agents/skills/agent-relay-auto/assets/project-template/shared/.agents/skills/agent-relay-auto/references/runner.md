# Runner Reference

The first Runner release is a macOS launchd service installed only after explicit confirmation during repository initialization.

Runtime source is copied to `~/.local/share/agent-relay-auto/versions/<version>/`; launchd points at the stable `current` link. User configuration is under `~/.config/agent-relay-auto/`, while project-local `.agent-relay-auto/` contains ignored process logs, run metadata, heartbeats, and native session references.

One project executes one active task and one role turn at a time. Different registered projects have independent Supervisors and may run concurrently. Planner stays user-facing: `PLANNING` waits for conversation, while `REPORTING` automatically resumes the exact Planner conversation registered in `.agent-relay-auto/planner-channel.json`. `WAITING_USER` and `BLOCKED` still wait for foreground action. The default poll interval is 45 seconds.

The Runner checks `task_id + expected_revision + participant_id + stage_round`, creates a `run_id`, and records PID, process start time, and writer session. On restart, a matching PID/start-time/run tuple is monitored; a possible PID reuse or unknown remote task is blocked.

The normal automatic path is:

```text
Planner foreground → Implementer background → Reviewer background
                  → same Planner conversation auto-resumed → DONE
```

Runner reports `waiting_foreground_planner` only in `PLANNING`. At `REPORTING`, it persists an idempotent wake key, submits one turn to the same conversation, and tracks the receipt. The user does not type `continue`. Background stages complete only through `implementation-done` and `verdict`. Exit 0 without a legal handoff is `protocol_failure: no_handoff`; it retries only within `max_agent_retries` and otherwise becomes `BLOCKED`.

Each run directory contains launch context, process identity, heartbeat, stdout/stderr, exit and protocol records. Defaults are `agent_timeout_minutes: 30`, `heartbeat_interval_seconds: 10`, `heartbeat_stale_seconds: 45`, and `interrupt_grace_seconds: 30`. `--ephemeral` controls Codex session persistence only, not process completion, state transition, timeout, or writer-lease release.

Reviewer `PASS` requires a non-empty evidence file. Planner reporting requires the final report sections: goal, delivery, tests, Reviewer evidence, limitations, usage, and explicitly unexecuted merge/push/release/deploy actions.

`report-done` requires the current revision, Planner participant, persisted `wake_key`, matching Reviewer reference, and matching `review_delivery_id`. Only Planner can advance `REPORTING` to `DONE`; Runner never guesses or writes that transition. Presentation retries are independent from the single model submission, so a UI reopen failure cannot roll back a valid `DONE`.

A remote turn is not business completion by itself: Runner reports completion only after re-reading `STATE.md == DONE`. A completed turn without guarded `report-done` consumes the bounded model retry policy and then blocks. UI presentation has separate persisted attempt and next-retry records and never resubmits the model after `DONE`. A durable local report transaction repairs `STATE.md == DONE` / `PROJECT_STATUS.md` split-brain after a crash. Ambiguous submissions are reconciled against the exact conversation when the tool exposes history (currently Codex); otherwise Runner fails closed instead of blindly resubmitting.

## Configuration Gate

The Runner is the consumer of role configuration, not the place where users repair it. Before installation or startup, the Skill must complete the conversational configuration and write `docs/agent/automation-policy.yaml` with an explicit `participant_id`, Agent, model, and provider-specific reasoning value for Planner, Implementer, and Reviewer.

`configure_runtime.py inspect` must report `complete: true` and `ready_to_start: true`. It returns a masked Planner conversation ID, capability labels, 45-second interval, and retry limits. `runnerctl.py start` performs the same validation before it registers the project or invokes launchctl. Missing channels instruct the user to run `$agent-relay-auto continue` in the intended Planner conversation. Missing policies, placeholder models, unsupported automatic tools, and participant mismatches stop with a role-specific message.

Planner wake support: Codex, OpenCode, and Claude Code have verified exact-session submission bridges; DeepSeek Harness ACP/TUI support is `static_only`/`experimental` until a real credentialed session passes. Cursor is not supported for original-window auto-reporting in this release.

The service entry uses the project Adapter factory in both `--once` and persistent modes. The factory creates a role router for Codex, OpenCode, and Claude Code, and the router applies the model and reasoning setting selected during initialization. Users never configure an “Adapter factory” directly.

## Health and Isolation

`runnerctl.py status` reports project configuration and launchd health separately. A registered service in `spawn scheduled` with `active count = 0` or a non-zero last exit code is `failed`, not `running`; an incomplete project is `blocked` even when the shared service is healthy. Inspect the returned stderr log path for permission and executable failures.

Each repository has an independent Supervisor. A missing policy, unreadable external volume, or damaged state produces a project-scoped error and must not stop later registered repositories. Automatic handoff messages say that Runner is starting the next role; they do not ask the user to open another window or type `continue`.

The launchd installer records `HOME`, `CODEX_HOME`, and a PATH containing the discovered Codex executable. macOS Full Disk Access cannot be granted programmatically. If launchd cannot read a project on an external volume, startup health remains failed/blocked and the user must grant access to the Python executable shown in the plist before restarting.

Agent stdout and stderr are drained concurrently into a bounded in-memory tail, redacted, and persisted under `.agent-relay-auto/runs/<task>/<run>/`. This prevents continuous JSONL output from filling an unread pipe while retaining enough diagnostics for recovery.
