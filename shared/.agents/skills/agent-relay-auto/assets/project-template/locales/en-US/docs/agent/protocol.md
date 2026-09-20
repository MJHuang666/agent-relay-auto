# Agent Relay Auto Protocol

Use repository files, not chat history, as authority for task, identity, revision, writer, reviewed delivery, and evidence.

In automatic mode, `PLANNING` stays in the user-facing Planner conversation. At `REPORTING`, Runner polls every 45 seconds by default and resumes the exact conversation stored in ignored `.agent-relay-auto/planner-channel.json`; normal completion never asks the user to type `continue`.

Planner wake tools are `codex`, `opencode`, `claude-code`, and `deepseek-harness`. Capability labels are `verified`, `experimental`, `static_only`, and `unavailable`. Never claim a static probe is verified.

Only the registered Planner may call `report-done`, and only with matching task, revision, participant, persisted `wake_key`, Reviewer reference, and `review_delivery_id`. Runner never writes `DONE`. `DONE` does not authorize merge, push, release, or deploy.
