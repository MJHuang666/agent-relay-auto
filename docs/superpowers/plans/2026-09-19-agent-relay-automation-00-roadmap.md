# Agent Relay 自动闭环总路线 Implementation Plan

> **执行要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（当前会话）或 `superpowers:executing-plans`（独立会话）。四个阶段必须按顺序执行；每阶段通过验收并提交后再进入下一阶段。

**Goal:** 把已批准的 Runner 自动闭环规格落实为四个可独立验证和回滚的实施阶段，最终形成可由 Skill 安装、可由 launchd 托管、支持三种真实 CLI 的本地自动协作系统。

**Architecture:** Markdown 项目状态是事实源；状态协议层负责合法性和 CAS，Runner 核心负责项目级调度，适配器层负责真实 CLI 与恢复，分发层负责初始化、服务生命周期和发行。上层只能调用下层公开接口，不得绕过状态锁直接改业务状态。

**Tech Stack:** Python 3 标准库、`unittest`、Markdown/fenced YAML、JSON/JSONL、macOS launchd、Codex/OpenCode/Claude Code CLI。

**Spec:** `docs/superpowers/specs/2026-09-19-agent-relay-automation-design.md`

**Global Constraints:** 只在“多agent项目状态共享自动版”仓库实施；不同项目可并行，同一项目第一版只执行一个任务；Reviewer PASS 后经 Planner REPORTING 自动 DONE；DONE 不授权 merge、push、release、deploy；发行只做本地提交和包，不自动推送。

---

## Dependency Order

```text
01 状态协议与任务队列
  ↓ 提供 schema / CAS / transitions / queue
02 Runner 核心
  ↓ 提供 supervisor / process / logs / fake E2E
03 CLI 适配器与恢复
  ↓ 提供 real adapters / interrupt / reconciliation
04 Skill、launchd 与发行
  ↓ 提供 installer / UX / CI / release package
```

不得把阶段 04 的 launchd 安装提前到假适配器闭环通过之前；不得在阶段 03 的 fixture 契约通过前运行付费真实模型会话。

## Phase Documents

1. [阶段 1：状态协议与任务队列](2026-09-19-agent-relay-automation-01-state-protocol.md)
2. [阶段 2：Runner 核心](2026-09-19-agent-relay-automation-02-runner-core.md)
3. [阶段 3：CLI 适配器、中断与恢复](2026-09-19-agent-relay-automation-03-cli-adapters-recovery.md)
4. [阶段 4：Skill、launchd 与发行](2026-09-19-agent-relay-automation-04-skill-service-release.md)

## Specification Coverage

| Approved design area | Owning phase | Acceptance evidence |
|---|---|---|
| 状态机、自动批准、DONE 语义 | 01 | transition/CLI unit tests |
| 项目任务集合、串行队列、未来并行边界 | 01 | schema and queue tests |
| revision、锁、幂等领取 | 01 | CAS/concurrency tests |
| 配置快照、返修/重规划/成本限制 | 01, 02 | schema and fake E2E |
| 项目 Supervisor、跨项目并行 | 02 | integration timing test |
| 日志、脱敏、轮转、通知 | 02 | run-store/notifier tests |
| Codex/OpenCode/Claude Code | 03 | fixture contracts and isolated validation |
| 暂停、中断、恢复、崩溃对账 | 03 | signal/reconciliation tests |
| 初始化配置、Runner 生命周期 | 04 | wizard/installer tests |
| 中英文 Skill、manual fallback、迁移 | 04 | contract/clone tests |
| CI、发行包、SHA-256 | 04 | release validation record |

## Cross-Phase Change Rules

1. 若实施发现规格歧义，停止当前任务并更新设计规格，经用户批准后再修改计划。
2. 若阶段内接口需要改变，先更新该阶段测试和所有后续计划中的签名，再写实现。
3. 每个阶段末运行全量测试、发行检查和 `git diff --check`；失败不得进入下一阶段。
4. 每个真实 CLI 验证独立记录结果；缺少凭证只把该适配器标为 `unavailable` 或 `static-only`，不得伪造成功。
5. 任一阶段均不得自动安装真实后台服务、推送远端或创建 Release；这些动作需要用户单独授权。

## Final Acceptance Gate

全部四个阶段完成后，交付必须同时满足：

- [ ] 假 CLI 完整闭环和至少一个已授权真实 CLI 隔离闭环可核对；
- [ ] Reviewer 无证据无法 PASS，Planner 无最终报告无法 DONE；
- [ ] 同项目不并发写产品文件，不同项目能独立并行；
- [ ] 中断后没有虚假完成，Runner 重启不会重复启动存活任务；
- [ ] 初始化可确认/修改三角色模型配置，备用 Agent 默认关闭；
- [ ] 运行日志、长期证据、usage 可用性和限制计数均可追踪；
- [ ] manual mode、旧任务恢复和 clone recovery 仍通过；
- [ ] 本地发行包可从零安装 dry-run，SHA-256 匹配；
- [ ] 没有执行 merge、push、release 或 deploy。
