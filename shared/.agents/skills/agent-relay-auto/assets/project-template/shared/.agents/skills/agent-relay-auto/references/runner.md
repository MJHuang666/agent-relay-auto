# Runner Reference

The first Runner release is a macOS launchd service installed only after explicit confirmation during repository initialization.

Runtime source is copied to `~/.local/share/agent-relay-auto/versions/<version>/`; launchd points at the stable `current` link. User configuration is under `~/.config/agent-relay-auto/`, while project-local `.agent-relay-auto/` contains ignored process logs, run metadata, heartbeats, and native session references.

One project executes one active task and one background role process at a time. Different registered projects have independent Supervisors and may run concurrently. Planner is foreground-only. `PLANNING`, `REPORTING`, `WAITING_USER`, and `BLOCKED` wait for foreground action; minimizing the Planner UI does not stop a running Implementer or Reviewer.

The Runner checks `task_id + expected_revision + participant_id + stage_round`, creates a `run_id`, and records PID, process start time, and writer session. On restart, a matching PID/start-time/run tuple is monitored; a possible PID reuse or unknown remote task is blocked.

The normal automatic path is:

```text
Planner foreground → Implementer background → Reviewer background → Planner foreground → DONE
```

Runner reports `waiting_foreground_planner` in `PLANNING` and `REPORTING` and does not create a Planner run. Background stages complete only through `implementation-done` and `verdict`. Exit 0 without a legal handoff is `protocol_failure: no_handoff`; it retries only within `max_agent_retries` and otherwise becomes `BLOCKED`.

Each run directory contains launch context, process identity, heartbeat, stdout/stderr, exit and protocol records. Defaults are `agent_timeout_minutes: 30`, `heartbeat_interval_seconds: 10`, `heartbeat_stale_seconds: 45`, and `interrupt_grace_seconds: 30`. `--ephemeral` controls Codex session persistence only, not process completion, state transition, timeout, or writer-lease release.

Reviewer `PASS` requires a non-empty evidence file. Planner reporting requires the final report sections: goal, delivery, tests, Reviewer evidence, limitations, usage, and explicitly unexecuted merge/push/release/deploy actions.

## Configuration Gate

The Runner is the consumer of role configuration, not the place where users repair it. Before installation or startup, the Skill must complete the conversational configuration and write `docs/agent/automation-policy.yaml` with an explicit `participant_id`, Agent, model, and provider-specific reasoning value for Planner, Implementer, and Reviewer.

`configure_runtime.py inspect` must report `complete: true`. `runnerctl.py start` performs the same validation before it registers the project or invokes launchctl. Missing policies, placeholder models, unsupported automatic tools, and participant mismatches stop with a role-specific message.

The service entry uses the project Adapter factory in both `--once` and persistent modes. The factory creates a role router for Codex, OpenCode, and Claude Code, and the router applies the model and reasoning setting selected during initialization. Users never configure an “Adapter factory” directly.

## Health and Isolation

`runnerctl.py status` reports project configuration and launchd health separately. A registered service in `spawn scheduled` with `active count = 0` or a non-zero last exit code is `failed`, not `running`; an incomplete project is `blocked` even when the shared service is healthy. Inspect the returned stderr log path for permission and executable failures.

Each repository has an independent Supervisor. A missing policy, unreadable external volume, or damaged state produces a project-scoped error and must not stop later registered repositories. Automatic handoff messages say that Runner is starting the next role; they do not ask the user to open another window or type `continue`.

The launchd installer records `HOME`, `CODEX_HOME`, and a PATH containing the discovered Codex executable. macOS Full Disk Access cannot be granted programmatically. If launchd cannot read a project on an external volume, startup health remains failed/blocked and the user must grant access to the Python executable shown in the plist before restarting.

Agent stdout and stderr are drained concurrently into a bounded in-memory tail, redacted, and persisted under `.agent-relay-auto/runs/<task>/<run>/`. This prevents continuous JSONL output from filling an unread pipe while retaining enough diagnostics for recovery.
