---
name: project-role-workflow
description: Legacy v1.4 compatibility entry for Agent Relay Auto. Redirects the former command name without carrying a second workflow implementation.
---

# Project Role Workflow compatibility entry

`project-role-workflow` was renamed to **Agent Relay Auto** in v1.5. Use the
sibling `agent-relay-auto` Skill and its current repository-local copy instead.

Map legacy calls directly:

| Legacy | Current |
|---|---|
| `$project-role-workflow 初始化当前仓库` | `$agent-relay-auto 初始化当前仓库` |
| `$project-role-workflow 继续` | `$agent-relay-auto 继续` |
| `$project-role-workflow 更换 Agent` / `$project-role-workflow 替换 Agent` | `$agent-relay-auto 更换 Agent` / `$agent-relay-auto 替换 Agent` |
| `$project-role-workflow initialize this repository` | `$agent-relay-auto initialize this repository` |
| `$project-role-workflow continue` | `$agent-relay-auto continue` |
| `$project-role-workflow replace agent` / `$project-role-workflow switch agent` | `$agent-relay-auto replace agent` / `$agent-relay-auto switch agent` |

Do not create, copy, or modify task state through this shim. Read
`../agent-relay-auto/SKILL.md` and continue there. This compatibility entry is
scheduled for removal in v2.0.
