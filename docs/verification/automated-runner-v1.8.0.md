# Agent Relay Auto v1.8.0 Verification

Date: 2026-09-20

## Scope

This release adds project-local, exact-conversation Planner wake-up for automatic final reporting. Planner remains foreground for planning and decisions; Runner launches Implementer and Reviewer in the background and resumes the registered original Planner conversation only at `REPORTING`.

`DONE` means acceptance is complete. This verification did not merge, push, create a GitHub Release, publish, or deploy anything.

## Automated evidence

- `python3 -m unittest discover -s tests -v`: **156 tests passed** after independent whole-branch review fixes.
- `python3 -m unittest tests.test_agent_relay_contract tests.shared_dot_agents_skill_loader -v`: **9 contract tests passed**.
- `git diff --check`: passed before the documentation commit and is rerun at release completion.
- Hybrid and reporting E2E coverage proves:
  - Reviewer `PASS` reaches `REPORTING`, then the original Planner completes `DONE` without user `continue`.
  - two Runner instances submit one wake for one project;
  - two different projects can report independently;
  - failed UI presentation does not roll back a valid `DONE`;
  - idle and `PLANNING` polling submit zero model turns.
  - a remote turn cannot report completion without guarded `report-done` and `STATE.md == DONE`;
  - model retries are bounded independently from persisted UI-presentation retries;
  - report completion recovers a simulated crash between task-state and project-index writes;
  - fallback receipts do not persist full conversation IDs.

## Planner wake capability status

The tests below use controlled transports or fake Planner implementations. They verify contracts and state-machine behavior, not a real authenticated CLI/UI session. Therefore no tool is labelled end-to-end `verified` by this release report.

| Tool | Exact-session contract | Original UI reopen | End-to-end status | Evidence |
|---|---|---|---|---|
| Codex | `experimental` | `experimental` | `experimental` | Controlled App Server transport tests exact thread IDs, receipts, observation, reconciliation, and deduplication; no real Desktop UI wake was run. |
| OpenCode | `experimental` | `experimental` | `experimental` | Command contract tests exact `--session` and no fork; the reporting E2E uses a fake Planner. |
| Claude Code | `experimental` | `experimental` | `experimental` | Command contract tests exact `--resume` and rejects mismatched sessions; the reporting E2E uses a fake Planner. |
| DeepSeek Harness | `static_only` | `experimental` | `static_only` | ACP bridge/state-machine tests pass; no `dsh` executable, `DSH_TEST_SESSION_ID`, or authenticated credential was available. |

Only a tool whose four capability fields are all `verified` may be displayed as fully verified. No capability is upgraded on the strength of fake or static tests alone.

## Local installation and service isolation

Release installation verification uses an isolated local data/config/LaunchAgents tree and an empty project registry. This proves installed-file manifest parity, the generated `--poll-interval 45` service command, and a model-free idle `--once` pass without waking any registered user project.

- Installed version: `1.8.0`
- Installed manifest: **171 entries verified by SHA-256**
- Isolated Runner `--once`: exit 0, zero registered projects, zero model submissions
- Generated service polling interval: **45 seconds**

The already-running user launchd service and its two registered projects are deliberately not restarted for release testing. Therefore this report does not claim that the user's persistent service was upgraded or restarted as part of validation.

## Package

- Artifact: `dist/agent-relay-auto-skill-pack-v1.8.0.zip`
- Checksum: `dist/agent-relay-auto-skill-pack-v1.8.0.zip.sha256`
- ZIP root: `agent-relay-auto-skill-pack/`
- Entries: **303**
- SHA-256: `17656aab9a3d04f1bed529aa0b796fde2baf3ed5928d87adbb30a9415f57ccea`
- Excludes `.git`, `.agent-relay-auto`, credentials, logs, `.DS_Store`, AppleDouble files, Python caches, and example active tasks.

Final archive hash and installation manifest counts are verified during the release build and checksum checks.
