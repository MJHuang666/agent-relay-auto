# Agent Relay Auto v1.8.0 Verification

Date: 2026-09-20

## Scope

This release adds project-local, exact-conversation Planner wake-up for automatic final reporting. Planner remains foreground for planning and decisions; Runner launches Implementer and Reviewer in the background and resumes the registered original Planner conversation only at `REPORTING`.

`DONE` means acceptance is complete. This verification did not merge, push, create a GitHub Release, publish, or deploy anything.

## Automated evidence

- `python3 -m unittest discover -s tests -v`: **148 tests passed**.
- `python3 -m unittest tests.test_agent_relay_contract tests.shared_dot_agents_skill_loader -v`: **9 contract tests passed**.
- `git diff --check`: passed before the documentation commit and is rerun at release completion.
- Hybrid and reporting E2E coverage proves:
  - Reviewer `PASS` reaches `REPORTING`, then the original Planner completes `DONE` without user `continue`.
  - two Runner instances submit one wake for one project;
  - two different projects can report independently;
  - failed UI presentation does not roll back a valid `DONE`;
  - idle and `PLANNING` polling submit zero model turns.

## Planner wake capability status

| Tool | Release status | Evidence |
|---|---|---|
| Codex | `verified` | Exact thread resume, turn receipt, deduplicated reporting, and E2E completion tests. |
| OpenCode | `verified` | Exact session command and no-fork contract tests. |
| Claude Code | `verified` | Exact `--resume` session contract and rejection of mismatched sessions. |
| DeepSeek Harness | `static_only` | ACP bridge and exact-session state machine tests pass; no `dsh` executable, `DSH_TEST_SESSION_ID`, or authenticated API credential was available for a real-session probe. |

No capability is upgraded from `static_only` without real authenticated session evidence.

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
- SHA-256: `763867d706d754985469624d19f81d0e54f6b80faef7a0b915c959a3a0c1087f`
- Excludes `.git`, `.agent-relay-auto`, credentials, logs, `.DS_Store`, AppleDouble files, Python caches, and example active tasks.

Final archive hash and installation manifest counts are verified during the release build and checksum checks.
