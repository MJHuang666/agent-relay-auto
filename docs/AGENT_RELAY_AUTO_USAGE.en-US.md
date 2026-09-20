# Agent Relay Auto Usage Guide

This guide covers `agent-relay-auto` Skill v1.8.0: initialization, role handoff, Agent replacement, automatic original-Planner reporting, pause and recovery, state inspection, and task acceptance.

Automatic mode is fixed to: foreground Planner → background Implementer → background Reviewer → resume the exact original Planner conversation for reporting. `PLANNING` waits for foreground interaction; `REPORTING` does not require the user to type `continue`. The default project polling interval is 45 seconds.

Initialization registers the current Planner conversation in the ignored local file `.agent-relay-auto/planner-channel.json` and displays only a masked ID. Wake tools are `codex`, `opencode`, `claude-code`, and `deepseek-harness`, with truthful `verified` / `experimental` / `static_only` / `unavailable` labels. After Reviewer PASS, only the original Planner may execute guarded `report-done` with the persisted `wake_key` and matching `review_delivery_id`; Runner never writes `DONE` directly.

A remote turn ending is not task completion: Runner must re-read `STATE.md == DONE`. Model retries and UI presentation retries are independent; after `DONE`, Runner may retry opening the original conversation but never submits another model turn. A durable local report transaction repairs a crash-induced split between task state and the project index.

## Initialize a repository

```text
$agent-relay-auto initialize this repository
$agent-relay-auto 初始化当前仓库
```

The Skill checks the repository, asks for the project language (`en-US` or `zh-CN`), asks which Agent serves Planner, Implementer, and Reviewer, then creates project files, Profiles, and bindings. It does not create a real task, overwrite existing project instructions, or modify product code.

## Agent choices

| Choice | Stable tool ID |
|---|---|
| Codex | `codex` |
| Cursor | `cursor` |
| Claude Code | `claude-code` |
| WorkBuddy | `workbuddy` |
| ZCode | `zcode` |
| Trae | `trae` |
| DeepSeek Harness | `deepseek-harness` |
| OpenCode | `opencode` |
| Other | User-provided stable ID |

One Agent may serve multiple roles, but every participant needs a unique `participant_id`. Role and tool ID are immutable after registration.

## Create and continue a task

```text
Create a task to implement user login.
continue
$agent-relay-auto continue
```

The task lives under `docs/agent/tasks/<TASK-ID>/` and contains `STATE.md`, `requirement.md`, `plan.md`, `execution.md`, `review.md`, `decisions.md`, and append-only `progress/` records. `STATE.md` is the single live state source.

Every Agent reads `PROJECT_STATUS.md`, `STATE.md`, `role-bindings.md`, its Profile, its role file, and the previous handoff before acting. If it is not the current participant, it reports the wait state and remains read-only.

## Planner

```text
Act as the Planner and prepare the plan for the active task.
```

Planner owns requirements, scope, constraints, risks, decisions, `plan.md`, and acceptance criteria. Planner does not modify product code.

## Implementer

```text
Act as the Implementer and execute the approved plan.
```

Before changing product code, Implementer must choose `USE` or `DO_NOT_USE` for subagents. Implementer changes code and tests, records a `delivery_id`, test evidence, and `execution.md`, then hands off to Reviewer.

For rework:

```text
Address the current Reviewer findings.
```

Rework creates fresh delivery evidence and preserves history.

## Reviewer and completion

```text
Act as the Reviewer and inspect the active task.
Verify the current task and close it when acceptance is complete.
```

Reviewer independently checks requirements, plan, actual diff, tests, and delivery version. Results may be `CHANGES_REQUESTED`, `VERIFYING`, `PLANNING`, `BLOCKED`, or `DONE`. `DONE` means acceptance only; it does not authorize merge, release, deployment, deletion, rollback, or push.

## Replace an Agent

```text
$agent-relay-auto replace agent
$agent-relay-auto switch agent
$agent-relay-auto 更换 Agent
$agent-relay-auto 替换 Agent
```

Choose the role, scope (`current-task`, `project-default`, or `both`), a same-role participant, the reason, and authorization. Repeated switching is supported, for example `Codex → Cursor → OpenCode → Codex`. Old identities and `MANAGEMENT` history remain. Replacing the current participant increments `stage_round`, clears old writer/checkpoint ownership, and replacing Implementer resets the subagent decision.

## Pause, resume, and block

```text
Pause the active task and record a checkpoint.
continue
Record that the task is blocked by an API credential problem.
```

Before resuming, check disk differences, processes, side effects, and delivery evidence. Do not blindly repeat an interrupted operation.

## State helper

```bash
python3 .agents/skills/agent-relay-auto/scripts/workflow_state.py \
  --repo . status
```

The helper provides a short-lived local lock, revision compare-and-swap, and atomic state replacement. It protects coordination state only, not product code.

Example replacement:

```bash
python3 .agents/skills/agent-relay-auto/scripts/workflow_state.py \
  --repo . replace-agent \
  --role implementer --from cursor-impl --to opencode-impl \
  --scope current-task --expected-revision 10 \
  --reason "Cursor quota exhausted" \
  --authorization "User approved in the current conversation"
```

Release a stale lock only after confirming that the old session stopped and obtaining explicit authorization.

## Write eligibility

Business writes require an active task, a confirmed participant identity, matching role and assignment, no foreign writer session, and verified worktree, baseline, and delivery evidence. Remain read-only when the task is inactive, the Agent is not current, another writer is active, the revision is stale, or state/history is contradictory.

## Shared tool entry points

Codex, Cursor, DeepSeek Harness, and OpenCode share:

```text
AGENTS.md
docs/agent/
.agents/skills/agent-relay-auto/
```

DeepSeek Harness requires `dsh-agent-instructions` and project Skill loading. OpenCode discovers the root `AGENTS.md` and `.agents/skills/`. Do not create duplicate `.dsh/skills` or `.opencode/skills` trees.

## Standard flow

```text
Initialize → choose language and role Agents → Planner
          → Implementer → Reviewer → rework if needed
          → final verification → DONE
```

See the [Skill instructions](../shared/.agents/skills/agent-relay-auto/SKILL.md), [initialization reference](../shared/.agents/skills/agent-relay-auto/references/initialization.md), [protocol](../shared/.agents/skills/agent-relay-auto/references/protocol.md), and [installation guide](../distribution/INSTALL.md) for details.

## Automated Runner

Initialization shows the defaults: three rework rounds, one automatic replan, one Agent failure retry, same-role fallback disabled, and `balanced` cost control (warn after run 8 and block new runs after run 12). Existing configuration displays all Planner, Implementer, and Reviewer Agent/model/reasoning tuples with Confirm or Modify choices.

The Skill must first confirm each role's `participant_id`, Agent, model, and reasoning setting in the conversation. Codex uses `reasoning_effort`, OpenCode uses `variant`, and Claude Code uses `effort`. If model discovery is unavailable, the user may provide a stable model ID, which remains pending until its first launch validation.

After configuration, the Skill shows one three-role summary for confirmation and separately asks whether to install and start the Runner. It may install the macOS launchd Runner, register the project, and start the service only when the user explicitly approves and `configure_runtime.py inspect` returns `ready_to_start: true`. A missing configuration never sends the user looking for an “Adapter factory.”

Automatic mode currently supports the non-interactive Codex, OpenCode, and Claude Code adapters. Other Agents continue through the manual relay. Different projects run independently; the first version executes one active task at a time within each project.

After an automatic handoff, the current role reports that Runner is starting the next role and waits for its result; it does not ask the user to open another window or type `continue`. Runner status distinguishes healthy execution, a project configuration block, an unloaded service, and a launchd crash loop. One broken project does not stop other projects. Bounded, redacted output logs are stored under `.agent-relay-auto/runs/`.

```text
$agent-relay-auto runner status
$agent-relay-auto start runner
$agent-relay-auto stop runner
$agent-relay-auto restart runner
$agent-relay-auto view logs
$agent-relay-auto follow logs
$agent-relay-auto pause current task
$agent-relay-auto interrupt current role
$agent-relay-auto resume current task
```

The Runner starts a next role only after lock, revision, and legal state-transition checks. Reviewer evidence and a Planner final report are required before automatic `DONE`. `DONE` still does not authorize merge, push, release, or deploy.
