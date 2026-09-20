# Agent Relay Auto 自动闭环设计规格

> v1.7.0 纠偏：Planner 只在前台运行。本文中允许 Runner 在后台启动 Planner 重规划或汇报的旧语义，已被 `2026-09-20-agent-relay-auto-foreground-planner-reliability-design.md` 取代。Runner 返回 `waiting_foreground_planner`，后台只运行 Implementer 和 Reviewer。

日期：2026-09-19

状态：设计已批准，等待实现计划

适用范围：`/Volumes/HP P900/mjwork/多agent项目状态共享自动版`

## 1. 概要

本设计在 Agent Relay Auto 现有 Planner、Implementer、Reviewer 文件协作协议之上增加本地 Runner，使一个任务在需求明确后能够自动完成规划、实施、审查、返修、重新规划、交付报告和结束状态转换。

用户始终通过 Planner 交互。Implementer 与 Reviewer 默认由 Runner 调用非交互 CLI 执行；Planner 在不需要用户决策的重规划和最终报告阶段也可以由后台 CLI 执行。任何角色遇到需求歧义、范围扩大、密钥、付费资源、高风险操作或无法验证的验收条件时，都必须进入 `WAITING_USER` 或 `BLOCKED`，不得猜测用户意图。

Reviewer 提交可核对的通过结论后，任务进入 `REPORTING`。Planner 只整理交付摘要，不得改变 Reviewer 结论；有效报告生成后，任务自动进入 `DONE`。`DONE` 仅表示需求验收完成，不授权自动合并、推送、发布、部署、删除或其他高风险操作。

## 2. 目标与非目标

### 2.1 目标

1. 用户向 Planner 提交任务后，在不需要额外决策时自动完成闭环。
2. 通过仓库文件而不是单个聊天窗口保存角色上下文。
3. 使用锁、expected revision、原子状态写入和幂等键防止重复领取与重复执行。
4. 允许 Agent 失败重试以及经用户启用的同角色备用 Agent 切换。
5. 提供可审计的运行日志、状态追踪、中断、检查点和恢复能力。
6. Runner 随 Skill 分发，由初始化流程安装、配置和管理。
7. 不同项目相互独立并行；每个项目第一版只运行一个活动任务和一个角色进程。
8. 第一版支持项目内多个任务排队，并为未来 Git worktree 并行保留兼容结构。
9. 控制重复上下文读取、返修循环和无界子代理造成的 Token 消耗。

### 2.2 非目标

第一版不实现：

- 自动 merge、push、release、deploy；
- 自动接受需求扩张或高风险操作；
- 跨机器调度和分布式锁；
- 同一 checkout 内的多任务并行写入；
- 无 Git 项目的并行实施；
- 对没有稳定非交互接口的 GUI Agent 进行模拟点击调度；
- 根据模型自然语言输出猜测任务已完成；
- 全局机器级并发限制或跨项目 FIFO 队列。

## 3. 总体架构

```text
用户
  ⇅
Planner 交互入口
  ⇅ 需求、问题、决策、最终报告
仓库状态与交付文件
  ⇅
本地 Runner（launchd 后台服务）
  ├─ Project Supervisor A
  │    └─ Planner CLI / Implementer CLI / Reviewer CLI
  ├─ Project Supervisor B
  │    └─ Planner CLI / Implementer CLI / Reviewer CLI
  └─ Project Supervisor C
       └─ Planner CLI / Implementer CLI / Reviewer CLI
```

Runner 只负责读取合法状态、获取执行权、启动 Agent、监控进程和验证状态转换。它不替角色制定计划、不替 Reviewer 判断通过，也不根据 stdout 中的“完成”字样改变任务状态。

每个已注册项目拥有独立 Supervisor、状态锁、运行记录、成本统计和通知。一个项目的 `WAITING_USER`、`BLOCKED`、崩溃或额度耗尽不应阻止其他项目执行。

## 4. 角色与交互边界

### 4.1 Planner

Planner 是用户唯一的业务交互入口，负责：

- 获取需求、约束、非目标和验收条件；
- 提供需要用户决定的选项；
- 在原始范围内生成或修订计划；
- 记录用户授权和决策；
- 在 Reviewer 通过后整理最终交付报告；
- 向用户交付结果并接收下一个任务。

Planner 不修改产品代码，不改变 Reviewer 的 verdict，不把报告生成视为重新审查。

Planner 有两个运行表面：

```yaml
planner:
  interactive:
    surface: codex-chat
    model: <用户选择>
  automation:
    agent: codex
    model: <用户选择>
    reasoning_effort: high
```

交互表面负责实时沟通。后台表面只处理不需要新授权的规划、重规划和报告生成。配置文件不得声称已静默改变一个已打开聊天窗口的模型；如果当前窗口与项目配置不一致，Skill 必须提示用户切换或创建指定模型的新 Planner 线程。

### 4.2 Implementer

Implementer 按计划修改代码、测试并记录交付证据，同时负责处理 Reviewer 返修。

每个任务在首次进入实施前必须确定 `subagent_policy: USE | DO_NOT_USE`。若为 `UNSELECTED`，Planner 向用户提问，Runner 不得启动 Implementer。子代理只在 `USE` 时允许，并受任务范围、成本控制和工具能力约束。

### 4.3 Reviewer

Reviewer 独立读取需求、计划、实际代码、diff、测试和交付证据，输出以下 verdict 之一：

- `PASS`
- `CHANGES_REQUESTED`
- `REPLAN_REQUIRED`
- `BLOCKED`

Reviewer 不直接修改产品代码。没有完整审查报告、有效证据和合法状态转换时，Runner 不得把自然语言中的“通过”解释为 `PASS`。

## 5. 自动状态机

任务主状态如下：

```text
QUEUED
  ↓ 被项目调度器激活
INTAKE
  ↓ 需求明确
PLANNING
  ├─ 需要用户决定 → WAITING_USER
  ├─ 无法继续 → BLOCKED
  └─ 计划完成且未扩大范围 → IMPLEMENTING

IMPLEMENTING
  ├─ 需要用户决定 → WAITING_USER
  ├─ 进程失败 → 重试 / 备用 Agent / BLOCKED
  └─ 实施与测试证据完成 → REVIEWING

REVIEWING
  ├─ PASS → REPORTING
  ├─ CHANGES_REQUESTED → IMPLEMENTING
  ├─ REPLAN_REQUIRED → PLANNING
  ├─ 需要用户决定 → WAITING_USER
  └─ 无法继续 → BLOCKED

REPORTING
  ├─ 有效最终报告 → DONE
  └─ 报告失败 → 重试 / 备用 Agent / BLOCKED
```

用户明确取消时进入 `CANCELLED`。`BLOCKED` 是可恢复状态，不代表永久失败。

`WAITING_USER` 必须保存：

```yaml
suspended_status: REVIEWING
resume_role: planner
question_id: Q-003
requested_by: reviewer-main
question_ref: questions/Q-003.md
```

用户回答后生成不可覆盖的决策记录，校验 question ID 和 revision，再恢复到指定状态。不得从头重跑整个任务。

### 5.1 计划自动批准边界

Planner 的计划在同时满足以下条件时自动进入实施：

- 没有扩大用户原始范围；
- 验收条件明确且可验证；
- 不需要新的密钥、付费资源或生产权限；
- 不包含数据删除、生产变更或其他高风险操作；
- 没有互相冲突的需求。

不满足时进入 `WAITING_USER` 或 `BLOCKED`。

### 5.2 DONE 语义

`REVIEWING → PASS → REPORTING → DONE` 是唯一正常自动完成路径。最终报告至少包含：

- 原始目标；
- 实际完成内容；
- 交付版本与文件位置；
- 测试和 Reviewer 证据；
- 已知限制；
- 使用或检查方式；
- 明确未执行的 merge、push、release 和 deploy。

## 6. Runner 生命周期与 Skill 分发

Runner 源码、适配器、安装脚本和 launchd 模板随 `agent-relay-auto` Skill 分发：

```text
agent-relay-auto/
├── SKILL.md
├── scripts/
│   ├── setup_runner.py
│   ├── runner.py
│   ├── runnerctl.py
│   ├── configure_runtime.py
│   └── adapters/
├── assets/
│   ├── project-template/
│   └── launchd/
└── references/
```

安装 Skill 只复制文件，不自动创建常驻进程。首次执行“初始化当前仓库”时：

1. 检查 Runner 是否已安装及版本是否兼容；
2. 说明后台服务、文件位置和权限影响；
3. 通过聊天向导配置三个角色、模型和推理参数，并展示最终摘要；
4. 验证配置完整，再获得 Runner 安装与启动确认；
5. 把稳定运行版本复制到用户本地运行目录；
6. 安装 launchd 服务；
7. 注册当前项目并启动 Runner；
8. Runner 进入空闲监听，不调用任何模型。

launchd 不直接引用可被升级、移动或删除的 Skill 目录。建议运行位置：

```text
~/.local/share/agent-relay-auto/
├── bin/
├── runtime/
└── versions/

~/.config/agent-relay-auto/
├── config.yaml
├── projects.yaml
└── runtime-profiles.yaml

~/Library/LaunchAgents/com.agent-relay-auto.runner.plist
```

第一版以 macOS 本地 Runner 为正式目标。其他操作系统可以复用适配器和状态机，但服务安装不在第一版验收范围内。

## 7. 初始化与运行配置

初始化先选择项目语言，再检查本机 Agent CLI 和已有配置。

### 7.1 无已有配置

聊天向导依次完成：

1. 项目语言；
2. 自动化策略默认值或自定义值；
3. Planner Agent、模型和推理强度；
4. Implementer Agent、模型和推理强度；
5. Reviewer Agent、模型和推理强度；
6. 同角色备用 Agent；
7. 成本控制档位；
8. Runner 安装与通知设置；
9. 最终摘要确认。

模型列表由适配器动态查询，不维护容易过期的硬编码目录。无法查询时允许输入稳定模型 ID，并标记为待启动验证。

### 7.2 已有配置

初始化显示三个角色的 Agent、模型、推理强度、执行方式和备用 Agent，提供：

1. 确认并继续；
2. 修改配置。

CLI 缺失、登录失效、模型不可用或配置部分损坏时，不得提供无条件确认，必须突出问题并修复。

### 7.3 默认自动化策略

```yaml
automation:
  max_rework_rounds: 3
  max_auto_replans: 1
  max_agent_retries: 1
  allow_same_role_fallback: false
```

- 返修轮数不包含首次实施；
- 重规划次数不包含初始计划；
- 失败重试用于进程或基础设施失败，不用于 Reviewer 拒绝；
- 备用 Agent 默认关闭；启用后只能使用预登记的同角色身份，并按顺序切换；
- 每次切换写入独立 MANAGEMENT 记录；
- 新旧 Agent 可以 A → B → A 多次切换，但不能改写既有身份。

任务开始时保存运行配置快照。项目默认值后续改变，不得静默影响活动任务。

## 8. Agent 适配器

适配器负责：

- 检测 CLI 是否存在；
- 查询可用模型和推理选项；
- 构造非交互命令；
- 设置工作目录和权限边界；
- 捕获 stdout、stderr、退出码和 provider usage；
- 记录或恢复原生 session ID；
- 发送中断信号；
- 判断是否存在仍可能运行的远程任务。

第一版计划提供自动适配器：

1. Codex
2. OpenCode
3. Claude Code

DeepSeek Harness 保留正式适配器接口，但只有检测到可调用 CLI 并通过真实会话测试后才能启用。Cursor、WorkBuddy、ZCode、Trae 及其他缺少稳定本地非交互入口的工具可以注册为手动参与者，不得伪装成自动可用。

统一能力声明示例：

```yaml
capabilities:
  noninteractive: true
  model_discovery: true
  native_resume: true
  structured_usage: false
  graceful_interrupt: true
```

缺少 `noninteractive` 能力的参与者被自动流程轮到时进入 `BLOCKED`，除非该任务明确采用手动模式。

## 9. 项目和任务调度

### 9.1 跨项目并行

不设置机器级全局 Agent 数量限制。不同项目默认完全独立并行：

```text
Project A → Implementer
Project B → Reviewer
Project C → Planner automation
```

每个项目拥有独立 Supervisor。外部模型账号的共享额度或服务商限流可能影响多个项目，但 Runner 不人为建立跨项目队列。单个项目被限流时只在该项目内重试或阻塞。

### 9.2 第一版项目内调度

```yaml
project_scheduler:
  task_execution_mode: serial
  max_active_tasks: 1
  max_agent_processes_per_task: 1
```

第一版允许创建多个任务记录，但只执行一个活动任务；其余任务处于 `QUEUED`。活动任务进入 `DONE`、`CANCELLED` 或由用户明确搁置并移出活动槽后，下一个任务才可被激活。`WAITING_USER` 和 `BLOCKED` 默认仍占用当前项目的活动槽，Runner 不得为了提高吞吐量自行绕过尚未解决的任务。激活、搁置和恢复都必须是带锁、授权记录和 revision 校验的项目管理事务。

项目状态从设计上使用任务集合：

```yaml
tasks:
  active:
    - TASK-001
  queued:
    - TASK-002
    - TASK-003
  blocked: []
  completed: []
```

自动版以任务集合为权威状态。迁移期间如保留旧 `active_task` 字段，它只能作为单活动任务兼容镜像，不得与 `tasks.active` 分别成为两个权威源。

### 9.3 未来项目内并行

未来可以切换为：

```yaml
project_scheduler:
  task_execution_mode: parallel-worktree
  max_active_tasks: 2
```

并行任务必须满足：

- 项目是 Git 仓库；
- 每个任务使用独立 worktree 和分支；
- 每个任务有独立 STATE、锁、revision、日志和运行快照；
- Planner 记录任务依赖和潜在冲突；
- 依赖任务仍然串行；
- Reviewer 只审查对应 worktree；
- `DONE` 不自动合并；
- 非 Git 项目继续使用排队模式。

## 10. 锁、revision 与幂等

每次角色领取使用：

```text
task_id + expected_revision + participant_id + stage_round
```

作为幂等和 CAS 输入。Runner 必须：

1. 获取当前任务短时状态锁；
2. 重新读取权威 STATE；
3. 校验项目活动任务、角色、参与者、execution 和 expected revision；
4. 写入唯一 `run_id` 和 writer session；
5. 原子替换 STATE 并增加 revision；
6. 释放短时锁；
7. 启动 CLI。

锁只保护协调状态，不保护产品文件。一个项目一次只允许一个活动角色，从流程上避免产品文件并发写入。

Runner 看到 revision 不匹配时必须丢弃旧启动方案并重新读取，不得重放。处于 `running` 的外部 writer 不能因为超时、沉默或日志停止就被假定已死亡。

## 11. 失败、重试和备用 Agent

### 11.1 可重试失败

- CLI 进程崩溃；
- 临时网络失败；
- 未产生合法状态转换；
- 可确认没有持续副作用的短暂工具错误。

默认对同一 Agent 重试一次。

### 11.2 不应浪费重试的失败

- 额度耗尽；
- 凭证缺失或失效；
- 模型不存在；
- 权限拒绝；
- 工具不支持非交互运行。

此类失败在启用备用 Agent 时直接切换到预登记的同角色备用身份，否则进入 `BLOCKED`。

### 11.3 安全停止条件

达到以下任一条件时不得强行完成：

- 最大返修轮数；
- 最大自动重规划次数；
- Agent 失败重试上限；
- 成本硬限制；
- 运行时间限制；
- 需求歧义或范围扩大；
- 密钥、付费资源、生产权限或高风险操作；
- 无法确认旧进程或远程任务已停止。

## 12. 成本与 Token 控制

初始化提供 `economy`、`balanced`、`quality` 三档，默认 `balanced`。用户修改预设值后记录为 `custom`。

默认有效配置：

```yaml
cost_control:
  mode: balanced
  warn_after_agent_runs: 8
  stop_after_agent_runs: 12
  require_confirmation_after_warning: false
  record_provider_usage: true
```

一次 Agent run 指 Runner 启动一次顶层 Planner、Implementer 或 Reviewer 进程。失败重试和恢复后的新进程也计数；用户主动暂停不计失败重试，但恢复启动仍计成本运行。可观测的子代理单独记录；无法从提供商取得的使用量标为 `unavailable`，不得估算成事实。

达到第 8 次时只提醒并继续。达到第 12 次时不终止正在执行的进程；该 run 结束后，禁止启动下一个 Agent，并进入：

```text
BLOCKED
reason: COST_LIMIT_REACHED
```

用户可以增加运行额度、更换模型或 Agent、调整范围、保持阻塞或取消任务。

上下文优化要求：

- Runner 提供角色所需的最小入口和相关文件索引；
- STATE 保持精简；
- 原始测试输出写日志，交接只记录结论和证据路径；
- Implementer 返修优先恢复同一会话，过长或失效时从检查点新建；
- Reviewer 阅读计划、真实 diff、相关源码和测试证据，不重复扫描无关目录；
- Planner 最终报告基于已验证交付物，不重新分析整个仓库；
- 相同 revision 不重复启动。

## 13. 日志与状态追踪

日志分三层。

### 13.1 Runner 全局服务日志

```text
~/Library/Logs/AgentRelay/
├── runner.log
├── runner.error.log
└── runner-events.jsonl
```

记录服务启动、停止、项目注册、异常、升级和 Supervisor 生命周期，不保存项目完整源码。

### 13.2 项目本机详细日志

```text
<repo>/.agent-relay-auto/
├── runtime/current-runs.json
└── runs/<task-id>/<run-id>/
    ├── metadata.json
    ├── events.jsonl
    ├── stdout.log
    ├── stderr.log
    ├── usage.json
    └── heartbeat.json
```

`.agent-relay-auto/` 必须加入目标项目 `.gitignore`。运行元数据至少包含 task、role、participant、Agent、model、PID、进程启动时间、run ID、起始 revision、状态、退出码和最新 heartbeat。

状态界面只显示真实状态、角色、耗时、最后事件和可用 usage，不生成虚假进度百分比。

### 13.3 仓库长期审计记录

任务的 `progress/`、`checkpoints/`、`execution.md`、`review.md` 和 `final-report.md` 保存可迁移事实：输入、动作、结论、证据、交付版本、中断、恢复和下一参与者。完整 stdout/stderr 不提交 Git。

默认日志策略：

- 单文件 10 MB 轮转；
- 每种日志保留 5 个轮转文件；
- 已完成任务详细日志保留 30 天；
- 活动任务和 BLOCKED 任务不自动清理；
- 输出前过滤 Token、API Key 和常见密钥环境变量；
- 清理操作不得删除仓库长期审计记录。

## 14. 暂停、中断与恢复

### 14.1 安全暂停

“暂停当前任务”请求 Agent 在最近安全边界写入 checkpoint，然后退出。STATE 保持原业务 status，设置 `execution: paused`，清空已确认停止的 writer session，并记录暂停原因和 resume status。

### 14.2 立即中断

“立即中断当前角色”执行：

1. 记录 `interrupt_requested`；
2. 向进程发送 SIGINT；
3. 等待默认 30 秒；
4. 仍未退出时发送 SIGTERM；
5. 核对 PID、进程启动时间和 run ID，确认进程停止；
6. 写入 `INTERRUPTED` run 记录；
7. 保存或核对 checkpoint；
8. 释放 writer session；
9. 将 execution 设为 paused。

默认不使用 SIGKILL。只有用户明确授权且风险说明完成后才允许强制终止。

### 14.3 恢复模式

适配器声明：

```yaml
recovery:
  mode: native-session | checkpoint-restart | unsupported
```

`native-session` 优先恢复工具原生 session。`checkpoint-restart` 启动新 CLI 会话，读取 STATE、最后有效 checkpoint、实际 Git diff、进程、测试、外部副作用和未完成步骤。恢复必须保持任务和阶段轮次，使用新 run ID，并按规则计入成本。

Implementer 的半成品修改不得自动回滚。恢复前先核对实际 diff 和残留进程，完成后重新运行受影响测试。

Reviewer 未提交完整报告和合法 verdict 时不算完成；中断后恢复原生会话或从稳定 delivery 重新审查。Runner 不得从部分日志推断通过。

### 14.4 Runner 崩溃和重启

Runner 启动时扫描各项目 current runs：

```text
核对 PID + process_started_at + run_id
  ├─ 进程仍存在 → 继续监控，禁止重复启动
  ├─ 已确认停止 → 执行恢复流程
  └─ 无法确认或远程任务可能仍运行 → BLOCKED / UNKNOWN_REMOTE_RUN
```

仅凭 PID 不足以证明同一进程仍存在，因为 PID 可能复用。Mac 重启后由 launchd 恢复 Runner；确认旧本地进程不可能仍存活后，从 checkpoint 继续。

如果本地 CLI 终止但服务商远程任务可能仍在运行，适配器必须查询原生状态；无法查询时阻塞，避免重复副作用。

## 15. 通知与用户命令

默认只在以下状态发送 macOS 通知：

- `WAITING_USER`
- `BLOCKED`
- `DONE`

通知包含项目、任务、请求角色和简短原因，不自动抢占焦点、不强制打开 Codex、不切换当前应用。用户返回任意可恢复 Planner 会话后执行“继续”即可读取待决策问题或最终报告。

计划支持的中英文命令包括：

```text
$agent-relay-auto 初始化当前仓库
$agent-relay-auto 继续
$agent-relay-auto 更换 Agent
$agent-relay-auto Runner 状态
$agent-relay-auto 启动 Runner
$agent-relay-auto 停止 Runner
$agent-relay-auto 重启 Runner
$agent-relay-auto 升级 Runner
$agent-relay-auto 运行状态
$agent-relay-auto 查看日志
$agent-relay-auto 跟踪日志
$agent-relay-auto 暂停当前任务
$agent-relay-auto 立即中断当前角色
$agent-relay-auto 恢复当前任务
```

英文命令提供等价语义。管理命令不能绕过状态锁、revision 和授权要求。

## 16. 配置与敏感信息分层

建议分层：

```text
仓库内，可提交：
docs/agent/automation-policy.yaml
docs/agent/tasks/<task>/runtime-snapshot.yaml

项目本机，忽略提交：
.agent-relay-auto/local.yaml
.agent-relay-auto/runs/

用户级，不属于仓库：
~/.config/agent-relay-auto/runtime-profiles.yaml
~/.config/agent-relay-auto/projects.yaml
```

仓库配置保存角色绑定、策略和可审计运行快照；本机配置保存 CLI 路径、原生 session 信息和主机能力；用户配置保存可复用默认值。

API Key、登录 Token、Cookie 和密钥值不得写入项目文件、运行快照或命令行日志。Runner 使用各 CLI 的既有安全登录状态或受控环境变量。

## 17. 与 Agent Relay Auto v1.5 的关系

保留以下 v1.5 不变量：

- Planner、Implementer、Reviewer 三角色及权限边界；
- participant identity 与 tool/role 解耦；
- 任务 STATE 为任务实时权威；
- revision、stage round、writer session 和交接证据；
- Reviewer 不修代码；
- DONE 不授权合并、发布或部署；
- Agent 可多次更换且保留历史身份；
- 无法确认旧 writer 停止时不得接管。

自动版明确取代以下 v1.5 边界：

- Relay 从“不是调度器”扩展为带本地 Runner 的项目级调度系统；
- 交接不再要求用户每阶段手动打开下一个工具并输入“继续”；
- PROJECT_STATUS 从单任务标量扩展为任务集合和排队状态；
- Runner 在合法 handoff 后自动启动下一角色；
- Reviewer PASS 后通过 REPORTING 自动进入 DONE。

旧手动模式仍应作为降级路径保留。Runner 未安装、适配器不可用或用户停用自动化时，Skill 可以使用原有文件接力流程，但必须明确标记当前项目为 manual mode。

## 18. 验证与验收

实现阶段至少需要以下验证。

### 18.1 单元测试

- 状态机所有合法和非法转换；
- expected revision CAS 和原子写入；
- 状态锁竞争；
- 相同 revision 幂等启动；
- 返修、重规划、失败重试和成本计数；
- 备用 Agent 开关；
- WAITING_USER 问题与回答绑定；
- 任务队列激活；
- 日志脱敏、轮转和保留；
- 运行快照不受默认配置变化影响。

### 18.2 适配器契约测试

- CLI 检测和模型发现；
- 非交互启动参数；
- stdout、stderr、usage 和退出码捕获；
- SIGINT、SIGTERM 和超时；
- 原生 session resume；
- 无原生恢复时的 checkpoint restart；
- 缺少凭证、模型、权限和额度时的错误分类。

### 18.3 集成测试

- 使用假 CLI 完成成功闭环；
- Reviewer 请求返修后自动回到 Implementer；
- Reviewer 请求重规划后自动回到 Planner；
- 用户决策进入 WAITING_USER 并正确恢复；
- 成本提醒和硬停止；
- Runner 崩溃后不重复启动存活子进程；
- 中断 Implementer 后保留并核对实际 diff；
- 中断 Reviewer 后不产生虚假 PASS；
- 两个临时项目同时执行且互不阻塞；
- 同一项目两个任务只激活一个；
- launchd 安装、升级、停止、重启和卸载。

### 18.4 端到端验收

使用隔离测试仓库验证：

1. Planner 收集需求并自动批准无范围扩张的计划；
2. Implementer CLI 实施并产生真实代码和测试证据；
3. Reviewer CLI 独立审查；
4. PASS 后 Planner 生成最终报告；
5. 任务自动 DONE；
6. 未执行 merge、push、release、deploy；
7. 全部状态、运行、usage、日志、交接和证据可核对；
8. 中途关闭 Planner 窗口后仍能从文件恢复；
9. 不同项目可同时推进；
10. 项目内第二个任务保持 QUEUED，直到前一个任务释放活动槽。

## 19. 实现分期

建议按以下顺序实现，具体任务拆分由后续实现计划确定：

1. 自动状态协议、任务集合和配置 schema；
2. Runner 核心、项目 Supervisor、锁和幂等；
3. 假 CLI 适配器及完整测试；
4. Codex、OpenCode、Claude Code 适配器；
5. 日志、通知、中断和恢复；
6. Skill 初始化、安装、升级和管理命令；
7. 真实隔离仓库端到端验证；
8. 发行包、安装说明和迁移说明。

并行 worktree 多任务不是第一版实现项，但 schema、任务目录和 Supervisor 边界不得阻碍后续增加。
