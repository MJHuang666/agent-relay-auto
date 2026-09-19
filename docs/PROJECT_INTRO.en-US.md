# Agent Relay Auto: Project Introduction

Agent Relay Auto is a lightweight multi-Agent relay framework for sustained work in one code repository. It moves requirements, plans, decisions, implementation evidence, and review conclusions out of an ephemeral chat and into readable project files, so different Agents, models, computers, and environments can continue the same work.

The core idea is not to make Agents share one conversation. It is to make them share one verifiable project state:

```text
Requirement → Plan → Implement → Review → Rework → Verify → Handoff
                                      ↓
                         project files become durable context
```

## The problem it solves

A single conversation is not a reliable long-term software-engineering workspace. Context can be truncated, a model can change, an Agent can run out of quota, and a chat window can disappear. When decisions exist only in chat, the next participant has to reconstruct the background, which leads to duplicated work, unsafe edits, and ambiguous handoffs.

Agent Relay Auto stores the durable part of the work in the repository:

- requirements, scope, non-goals, and acceptance criteria;
- architecture constraints, decisions, and risks;
- implementation records, test results, and delivery versions;
- independent Reviewer findings, conclusions, and rework requests;
- the active task, role bindings, revision, and next participant.

Changing an Agent therefore does not mean losing project cognition. A new Agent reads the project state and the previous handoff, then resumes from evidence instead of guessing from chat history.

## Three stable roles

Roles are independent from tools. One tool may serve multiple roles, and a role may move between tools without losing the shared project state.

| Role | Owns | Boundary |
| --- | --- | --- |
| Planner | Scope, non-goals, plans, decisions, and acceptance criteria | Does not change product code; asks the user when scope expands or requirements are ambiguous |
| Implementer | Code, tests, execution evidence, and review rework | Does not self-approve delivery; hands results to the Reviewer |
| Reviewer | Independent review, verification, and the completion decision | Does not directly repair product code; a pass requires evidence |

The normal loop is:

```text
Planner
  ↓ plan.md
Implementer
  ↓ execution.md + tests
Reviewer
  ├─ pass → delivery report → DONE
  ├─ changes requested → Implementer rework → review again
  ├─ re-plan required → Planner revises the plan
  └─ cannot continue → BLOCKED, waiting for the user
```

`DONE` means that the task has been accepted. It does not authorize an automatic merge, push, release, deployment, or high-risk operation.

## How project state is stored

After initialization, the repository has a shared state area. Active tasks live under `docs/agent/tasks/<TASK-ID>/`:

```text
docs/agent/
├── PROJECT_STATUS.md       # project entry point, active task, and current stage
├── knowledge-index.md      # verified long-term project cognition
├── role-bindings.md        # stable role and participant bindings
├── profiles/               # participant tools, roles, and capabilities
└── tasks/<TASK-ID>/
    ├── STATE.md            # the task's single live state source
    ├── requirement.md      # requirements, scope, and acceptance criteria
    ├── plan.md             # Planner output and decisions
    ├── execution.md        # implementation and test evidence
    ├── review.md           # independent review and conclusion
    ├── decisions.md        # durable task decisions
    └── progress/            # append-only stage records
```

`STATE.md`, `revision`, role bindings, and handoff records prevent a stale Agent from overwriting newer project state. Agent replacement preserves the old identity, reason, authorization, and scope, so repeated switches such as `A → B → A` remain auditable.

## Supported Agents

The shared protocol currently recognizes these tool IDs:

| Tool | ID |
| --- | --- |
| Codex | `codex` |
| Cursor | `cursor` |
| Claude Code | `claude-code` |
| WorkBuddy | `workbuddy` |
| ZCode | `zcode` |
| Trae | `trae` |
| DeepSeek Harness | `deepseek-harness` |
| OpenCode | `opencode` |
| Other | a user-supplied stable ID |

DeepSeek Harness and OpenCode reuse the root `AGENTS.md`, `.agents/skills/agent-relay-auto/`, and `docs/agent/`. They do not require duplicate private protocol directories.

## Quick start

### Install

Install `agent-relay-auto` as a personal Skill, or download the [latest release](https://github.com/MJHuang666/agent-relay-auto/releases/latest). Initializing a project also copies the required project-local Skill and template files.

### Initialize the current repository

```text
$agent-relay-auto initialize this repository
# or
$agent-relay-auto 初始化当前仓库
```

The initializer asks for the project language, the Agent bound to each role, and the automatic-mode policies. It fills only missing files and preserves existing project state and product code.

### Continue the current task

```text
$agent-relay-auto continue
# or
$agent-relay-auto 继续
```

The Agent first reads the project status, task state, its participant profile, and the previous stage's delivery. If it is not the current participant, it reports who is awaited and remains read-only. If it is the assigned participant, it performs only its role's work.

### Replace a role Agent

```text
$agent-relay-auto switch agent
$agent-relay-auto replace agent
# or
$agent-relay-auto 更换agent
$agent-relay-auto 替换agent
```

Replacement uses a short-lived file lock, expected-revision checks, and atomic writes to prevent two sessions from updating the same role at once. It preserves history and does not require the new Agent to use the same model.

For the full command reference, see the [English usage guide](AGENT_RELAY_AUTO_USAGE.en-US.md).

## Manual mode and the automatic Runner

### Manual/file-based mode

This is the most stable mode today. The user opens the Agent assigned to the current role, runs `continue`, and lets it work from the repository state. Projects remain isolated and can run independently in parallel.

### Automatic Runner mode

The automatic edition includes the Runner, runtime configuration, logging, and recovery design. Its goal is to start the next role after a valid state transition and move to `DONE` only after the Reviewer writes complete evidence. Initialization can configure retry, re-planning, cost warnings, and whether same-role backup Agents are allowed.

The current release has completed a real Codex automatic-loop validation and connects non-interactive OpenCode and Claude Code adapters; those two still require first-launch validation in each user's credential and model environment. Runner isolates project failures, continuously drains Agent output, and reports real launchd health. Ambiguity, credentials, permissions, and high-risk external operations still enter `BLOCKED` and return to the user.

In both modes, the Runner has no authority to merge, push, release, deploy, or write to production.

## Safety and collaboration boundaries

- Repository files are the state source, not a replacement for Git; important deliveries should still be committed and version-checked.
- The lock protects coordination state in one checkout. It does not lock product code or coordinate multiple machines.
- The Reviewer performs independent acceptance and does not directly edit product code.
- `DONE` is an acceptance state, not release authorization.
- Credentials, ambiguous requirements, scope expansion, and high-risk external actions must not be guessed by the Runner.
- Agents coordinate through `docs/agent/`, not through a chat window that may disappear.

## Main project directories

```text
.agents/skills/agent-relay-auto/   shared Skill, references, and state helpers
codex/                             Codex entry points and prompts
cursor/                            Cursor entry points and prompts
shared/docs/agent/                 initialization templates, protocol, and profiles
docs/                              project guides and verification reports
compat/                            compatibility entry for the former command name
```

Contributions are welcome through Issues and Pull Requests. Before contributing, read [CONTRIBUTING.md](../CONTRIBUTING.md), [SECURITY.md](../SECURITY.md), and [CHANGELOG.md](../CHANGELOG.md). Agent Relay Auto is licensed under [Apache-2.0](../LICENSE).
