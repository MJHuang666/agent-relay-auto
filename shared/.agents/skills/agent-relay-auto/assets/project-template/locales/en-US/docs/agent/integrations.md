# Tool Integrations

Files being present proves only that the protocol is readable. Verify each automatic entry with a fresh real session.

| Tool | Protocol Readable | Automatic Entry | Template Supplied | Verification Status | Verified Version / Date |
|---|---:|---|---:|---|---|
| Codex | Yes | Root `AGENTS.md` + `.agents/skills/` | Yes | Pending | - |
| Cursor | Yes | `.cursor/rules/` + `.cursor/commands/` + `.agents/skills/` | Yes | Pending | - |
| Claude Code | Yes | Configure for the target version | No | Not configured | - |
| WorkBuddy | Yes | Configure for the target version | No | Not configured | - |
| ZCode | Yes | Configure for the target version | No | Not configured | - |
| Trae | Yes | Configure for the target version | No | Not configured | - |
| DeepSeek Harness | Yes | Root `AGENTS.md` + `.agents/skills/agent-relay-auto/`; enable `dsh-agent-instructions` and filesystem skill loading | Yes | Static verification complete; fresh session pending | Local source / 2026-09-17 |
| OpenCode | Yes | Root `AGENTS.md` + `.agents/skills/agent-relay-auto/` | Yes | Verified | 1.3.17 / 2026-09-17 |
| Other | Yes | Record the entry supported by that tool | No | Not configured | - |

Start a fresh session, say only `continue`, and verify that the tool reads project status, task state, language, identity, and role before changing this table to verified.

DeepSeek Harness and OpenCode share `.agents/skills/agent-relay-auto/` as the single source of truth. Do not create duplicate `.dsh/skills` or `.opencode/skills` trees. If OpenCode does not discover the skill, check skill permissions and higher-priority same-name copies.

## Original Planner Auto-reporting

| Planner Tool ID | Exact-session Submit | Original UI Reopen | End-to-end Status |
|---|---|---|---|
| `codex` | `verified` | `experimental` | `experimental` |
| `opencode` | `verified` | `verified` | `experimental` |
| `claude-code` | `verified` | `verified` | `experimental` |
| `deepseek-harness` | `static_only` | `experimental` | `static_only` |

Initialization writes the exact binding to ignored `.agent-relay-auto/planner-channel.json` and displays only a masked ID. `REPORTING` uses a 45-second default poll and does not require user `continue`. `DONE` is acceptance only; it does not authorize merge, push, release, or deploy.
