# Repository Initialization

Use this procedure when the user asks to initialize Agent Relay Auto, using either `初始化当前仓库` or `initialize this repository`, or explicitly invokes the Skill in a repository without `docs/agent/PROJECT_STATUS.md`.

The template source is `assets/project-template/`, resolved relative to this Skill directory. Markdown remains usable without Python, but Python 3 enables the bundled lock, revision-CAS, and atomic-write safety helper. Report the degraded manual single-writer mode when Python is unavailable.

## Preflight

1. Resolve the target repository root from the current workspace. Never initialize a parent directory, home directory, or another repository by inference.
2. Inspect existing `AGENTS.md`, `.agents/`, `.cursor/`, and `docs/agent/` paths before writing.
3. If the target is not clear, ask for the repository path. If it is clear, proceed without asking for confirmation again.
4. Do not initialize inside this Skill's own `assets/` directory.

## Choose Language First

Before asking which tools serve the roles, ask the user to select exactly one project language:

1. 中文（`zh-CN`）
2. English（`en-US`）

Write the choice to `docs/agent/PROJECT_STATUS.md` as `language: zh-CN` or `language: en-US`. If the user uses a bilingual command but does not choose a language, ask this question and pause role selection until it is answered. All subsequent user-facing communication and newly authored task documents use the selected language. Stable YAML keys and enum values remain unchanged.

## Install the Baseline

Copy the shared documentation from `assets/project-template/shared/docs/` into repository root `docs/`. Do not copy `tasks/TASK-EXAMPLE-001`; examples are distribution documentation, not initialized project state.

Then try to copy the project runtime Skill:

```text
.agents/skills/agent-relay-auto/
```

If the host sandbox blocks writes to `.agents/`, do not fail or create workaround files. Continue with the already loaded global Skill plus `docs/agent/protocol.md`, install the Codex/Cursor adapters, and report project-level Skill installation as pending. A later trusted installer may copy it. The workflow must remain usable without the project-level Skill. Treat this host-policy denial as an expected compatibility fallback, not as a workflow error; do not create repository-local error logs such as `.learnings/` solely because of it.

Overlay the corresponding files from `assets/project-template/locales/<language>/` after the baseline copy. The overlay must not replace pre-existing project files; it only localizes files created in this initialization.

Then install tool adapters:

- Codex: if root `AGENTS.md` is absent, copy `assets/project-template/adapters/codex/AGENTS.md`. If it has an `<!-- agent-relay-auto:start -->` block, leave that block unchanged. If it has the legacy `<!-- project-role-workflow:start -->` block, replace only that complete marked block with the Agent Relay Auto block, preserving all text outside the markers. Otherwise append the Agent Relay Auto block without changing existing text. Never leave both marked blocks in one file.
- Cursor: copy missing files from `assets/project-template/adapters/cursor/.cursor/` to root `.cursor/`. Preserve any existing same-path file and report it for manual comparison.

For all other same-path collisions, preserve the target file. Fill only missing files and report differing files. Never replace `PROJECT_STATUS.md`, `role-bindings.md`, Profiles, task records, architecture constraints, or product instructions with template content.

Ignore `._*` and `.DS_Store` files.

## Configure Identities

The copied baseline intentionally has `active_task: null` and no real participant registrations.

After the language is recorded, ask the user for the tool that will serve each role:

1. Planner
2. Implementer, including rework
3. Reviewer

Present these numbered tool choices for each role:

1. Codex (`codex`)
2. Cursor (`cursor`)
3. Claude Code (`claude-code`)
4. WorkBuddy (`workbuddy`)
5. ZCode (`zcode`)
6. Trae (`trae`)
7. DeepSeek Harness (`deepseek-harness`)
8. OpenCode (`opencode`)
9. Other (ask for a stable custom tool ID)

One tool may serve multiple roles, but every identity needs a unique `participant_id`. Store the stable tool ID, not the display label.

After role/tool selection, inspect existing Runner configuration:

```text
python3 .agents/skills/agent-relay-auto/scripts/configure_runtime.py inspect --repo <repo>
```

If no complete configuration exists, present defaults (`max_rework_rounds: 3`, `max_auto_replans: 1`, `max_agent_retries: 1`, `allow_same_role_fallback: false`, balanced cost control), then configure each role in the conversation:

1. Confirm the role's immutable `participant_id` and Agent tool ID.
2. For Codex or OpenCode, run `configure_runtime.py discover --tool <tool-id>` and present the returned models. Claude Code accepts a user-selected alias or full model ID when discovery is unavailable.
3. Ask for the model and tool-specific reasoning setting: Codex `reasoning_effort`, OpenCode `variant`, Claude Code `effort`.
4. Mark a dynamically returned model `verified`; mark an explicitly entered stable ID `pending` until first launch validation.

Background automatic execution supports `codex`, `opencode`, and `claude-code`. Exact Planner wake supports `codex`, `opencode`, `claude-code`, and `deepseek-harness`; DeepSeek Harness remains `static_only` until a real credentialed session is verified.

If configuration already exists, show the complete three-role participant/Agent/model/reasoning table and all reported problems. Offer Confirm or Modify only when the configuration is complete; any missing participant, placeholder/default model, unsupported automatic Agent, or damaged policy forces Modify.

Show the proposed automation policy and role table one final time and obtain confirmation. Register the exact current Planner conversation by passing `planner_channel.tool` and `planner_channel.conversation_id` to `configure_runtime.py apply`. The local ignored file `.agent-relay-auto/planner-channel.json` is the binding; never commit it or echo the full ID. Show the masked ID, project path, 45-second poll interval, retry limits, and capability labels returned by `inspect`. Existing projects without this binding must run `$agent-relay-auto continue` once in the intended Planner conversation before startup.

Then ask separately whether to install and start the macOS launchd Runner. Apply all non-secret answers, including that choice as `runner_confirmed`, and inspect again. If installation was accepted, require `ready_to_start: true`, install the versioned runtime, and run `runnerctl.py start --repo <repo>`; that command validates configuration and the Planner channel before registering the project or calling launchctl. Declining writes or keeps `mode: manual`. Never install first and ask the user to repair an Adapter factory or runtime policy afterward.

For each identity, create a Profile from `docs/agent/profiles/_templates/participant.md` and register the immutable `(participant_id, tool, role)` tuple in `docs/agent/role-bindings.md`. Do not infer these choices from the current tool or create a real task during initialization.

## Verify

Before reporting success, verify:

- `docs/agent/PROJECT_STATUS.md` exists and keeps `active_task: null`.
- all three role files and every task template file exist.
- `docs/agent/protocol.md` exists; the project-level Skill is either installed or explicitly reported pending because the host denied `.agents/` writes.
- the Codex block is present in root `AGENTS.md` without losing prior content.
- Cursor rule and command files exist unless preserved collisions were reported.
- local Markdown links resolve.
- `scripts/workflow_state.py --repo <target> status` can read the initialized project when Python 3 is available.
- automatic mode has explicit participant/model/reasoning values for all three roles; `configure_runtime.py inspect` reports `ready_to_start: true` before Runner installation.
- automatic mode has an exact Planner channel, displayed only as a masked conversation ID, and reports one of `verified`, `experimental`, `static_only`, or `unavailable` for each capability.
- when Runner installation was confirmed, `runnerctl.py status --repo <target>` reports a loaded service and the project registry contains the target path.
- no product code or real task was created.

Report created files, preserved collisions, configured language and identities, and adapters that still require a real new-session verification.
