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
