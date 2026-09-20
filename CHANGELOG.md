# Changelog

All notable changes to Agent Relay Auto are documented here. Project Role Workflow and Agent Relay are legacy names retained only for migration history.

## [1.8.0] - 2026-09-20

- Added project-local Planner conversation bindings and exact-conversation wake adapters for Codex, OpenCode, Claude Code, and DeepSeek Harness.
- Made `REPORTING` automatically resume the original Planner conversation, while keeping `PLANNING`, `WAITING_USER`, and `BLOCKED` foreground-controlled.
- Added revision-checked wake keys, append-only wake journals, submission receipts, and separate model/presentation retry handling.
- Kept idle polling local and model-free at a 45-second default interval, with per-project concurrency and duplicate-submission protection.
- Guarded `REPORTING → DONE` behind Planner identity, Reviewer evidence, delivery ID, and wake-key validation; Runner still cannot write `DONE` directly.
- Marked DeepSeek Harness support truthfully as static-only unless a real authenticated session probe succeeds.
- Made remote-turn completion insufficient without `STATE.md == DONE`, and added bounded model retries plus independent persisted UI-presentation retries.
- Added a durable report-completion transaction with crash recovery for task/project-index split-brain.
- Prevented full conversation IDs from leaking through fallback receipt identifiers and added Codex exact-thread reconciliation for ambiguous submissions.

## [1.7.0] - 2026-09-20

- Made Planner foreground-only while Runner launches only Implementer and Reviewer in the background.
- Added atomic `plan-done`, `implementation-done`, `verdict`, answer, and final-report transitions with revision, participant, run-ID, writer and evidence checks.
- Added durable Worker process identity, launch context, heartbeat, stdout/stderr, exit and protocol records with restart reconciliation.
- Classified exit 0 without a legal handoff as `protocol_failure: no_handoff`, with bounded retries and audited blocking.
- Added revision-keyed attention notifications, workflow-aware health output and non-destructive v1.7 upgrade preflight.
- Kept `DONE` separate from merge, push, release and deploy authorization.

## [1.6.3] - 2026-09-19

- Made automatic handoffs wait for Runner results instead of instructing users to open the next role manually.
- Added per-project Runner fault isolation so one invalid or unreadable repository cannot stop other registered projects.
- Added bounded concurrent stdout/stderr draining and project-local redacted run logs to prevent Codex JSONL pipe deadlocks.
- Added durable run finalization for adapters without a lifecycle callback and `CHANGES_REQUESTED` dispatch back to Implementer.
- Added Codex non-Git and approved non-interactive execution flags.
- Added launchd `HOME`, `CODEX_HOME`, and executable `PATH` configuration.
- Made Runner status distinguish healthy execution, project configuration blocks, unloaded services, and launchd crash loops.

## [1.6.2] - 2026-09-19

- Added a mandatory conversational configuration gate before Runner installation or startup.
- Added complete participant, model, and provider-specific reasoning settings for Planner, Implementer, and Reviewer.
- Connected the service entry to a real per-project Adapter factory and role router for Codex, OpenCode, and Claude Code.
- Corrected Codex app-server model discovery initialization and OpenCode model-list parsing against the locally installed CLIs.
- Added configuration-aware Runner start/status controls and absolute launchd log paths.
- Prevented missing policies, placeholder models, unsupported automatic tools, and participant mismatches from reaching launchctl or an Agent process.

## [1.6.1] - 2026-09-19

- Renamed the automatic edition's public Skill, commands, project-local paths, documentation, and release package from `agent-relay` to `agent-relay-auto`.
- Kept `project-role-workflow` as a thin compatibility redirect; it does not contain a second workflow implementation.

## [1.6.0] - 2026-09-19

- Added the project-scoped Relay Runner with serial task queues, CAS claims, run logs, notifications, pause/interruption recovery, and automatic Reviewer-to-Planner reporting.
- Added Codex, OpenCode, and Claude Code non-interactive adapters with model/session contracts; unsupported tools remain manual participants.
- Added explicit initialization policy/model review, optional macOS launchd installation, versioned runtime upgrades, and bilingual Runner commands.
- Automatic `DONE` remains acceptance only and does not authorize merge, push, release, or deploy.

## [1.5.0] - 2026-09-17

### Added

- `knowledge-index.md` for durable, evidence-linked architecture, constraints, decisions, and verified lessons.
- An end-to-end fresh-clone recovery test that proves committed Relay state can be recovered without bringing uncommitted files along.
- A documented, explicit handoff package for dirty working trees during machine or Agent migration.

### Changed

- Renamed the public Skill, commands, project directory, documentation, and release package from `project-role-workflow` to `agent-relay-auto`.
- Retained a thin legacy redirect until v2.0 and made the state helper recognize old lock names without permitting ambiguous automatic release.

## [1.4.0] - 2026-09-17

### Added

- First-class DeepSeek Harness (`deepseek-harness`) and OpenCode (`opencode`) tool identities in initialization, Profiles, documentation, and release validation.
- Shared-entry installation and troubleshooting guidance for both tools without duplicate Skill trees.

### Changed

- The initializer now presents nine stable tool choices, with `Other` reserved for an explicit custom ID.

## [1.3.0] - 2026-09-17

### Added

- Repeated, scoped Agent replacement commands in Chinese and English for current tasks, future defaults, or both.
- A Python-standard-library state helper with a short-lived local lock, expected-revision validation, atomic file replacement, and authorized stale-lock recovery.
- Per-role assignment change references and append-only MANAGEMENT records for participant changes.

### Changed

- Participant lifecycle now distinguishes `active`, reusable `standby`, and explicitly retired identities.
- Implementer replacement resets the subagent decision so the new participant must choose again.

## [1.2.0] - 2026-09-16

### Added

- Chinese and English commands for repository initialization and continuation.
- Project-language selection before role-tool assignment, with localized templates for Chinese and English projects.
- Implementer subagent decision gate, recorded in task state before product-code changes.
- A compact `docs/agent/protocol.md` fallback when a host prevents project-level `.agents/` installation.

### Changed

- Automatic initialization now excludes the example task from active project state.
- Project-level Skill installation degrades gracefully when the host sandbox denies `.agents/` writes.

## [1.1.0] - 2026-09-16

### Added

- Initial Planner, Implementer, and Reviewer file-based collaboration workflow.
