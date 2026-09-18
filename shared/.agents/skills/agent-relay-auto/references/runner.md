# Runner Reference

The first Runner release is a macOS launchd service installed only after explicit confirmation during repository initialization.

Runtime source is copied to `~/.local/share/agent-relay-auto/versions/<version>/`; launchd points at the stable `current` link. User configuration is under `~/.config/agent-relay-auto/`, while project-local `.agent-relay-auto/` contains ignored process logs, run metadata, heartbeats, and native session references.

One project executes one active task and one role process at a time. Different registered projects have independent Supervisors and may run concurrently. `WAITING_USER` and `BLOCKED` retain the active slot until the user answers, resumes, shelves, or cancels the task.

The Runner checks `task_id + expected_revision + participant_id + stage_round`, creates a `run_id`, and records PID, process start time, and writer session. On restart, a matching PID/start-time/run tuple is monitored; a possible PID reuse or unknown remote task is blocked.

The normal automatic path is:

```text
PLANNING → IMPLEMENTING → REVIEWING → REPORTING → DONE
```

Reviewer `PASS` requires a non-empty evidence file. Planner reporting requires the final report sections: goal, delivery, tests, Reviewer evidence, limitations, usage, and explicitly unexecuted merge/push/release/deploy actions.

## Configuration Gate

The Runner is the consumer of role configuration, not the place where users repair it. Before installation or startup, the Skill must complete the conversational configuration and write `docs/agent/automation-policy.yaml` with an explicit `participant_id`, Agent, model, and provider-specific reasoning value for Planner, Implementer, and Reviewer.

`configure_runtime.py inspect` must report `complete: true`. `runnerctl.py start` performs the same validation before it registers the project or invokes launchctl. Missing policies, placeholder models, unsupported automatic tools, and participant mismatches stop with a role-specific message.

The service entry uses the project Adapter factory in both `--once` and persistent modes. The factory creates a role router for Codex, OpenCode, and Claude Code, and the router applies the model and reasoning setting selected during initialization. Users never configure an “Adapter factory” directly.
