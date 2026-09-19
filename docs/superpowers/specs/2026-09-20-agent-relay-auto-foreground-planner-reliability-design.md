# Agent Relay Auto 前台 Planner 与可靠后台回合设计

日期：2026-09-20

状态：会话设计已批准，书面规格等待用户审阅

目标版本：v1.7.0

适用范围：`/Volumes/HP P900/mjwork/多agent项目状态共享自动版`

## 1. 背景与问题

现有 Runner 把 `PLANNING`、`IMPLEMENTING`、`REVIEWING` 和 `REPORTING` 都映射为可在后台启动的角色。这与实际产品边界不一致：Planner 是用户的前台业务入口，必须能够实时提出选项、澄清歧义和交付最终总结；Implementer 与 Reviewer 才适合由非交互 CLI 在后台运行。

`test-auto-relay2` 的事故还暴露出四个独立的可靠性缺口：

1. Runner 启动 Agent 时没有把本次 `run_id` 明确告知 Agent。Agent 读取到 `writer_session: run-...` 后无法判断它就是当前合法 writer，容易把自己的 lease 误判为外部残留会话。
2. 用户回答已写入 decision 文件，但 `subagent_policy` 与 `subagent_decision_ref` 没有在同一个锁和 revision 事务中更新，导致 Runner 重复启动同一问题回合。
3. Implementer 缺少受约束的完成命令，只能手工同步多个状态字段。任何遗漏都会形成“产品文件已生成，但交付和状态未推进”的半完成状态。
4. Agent 进程退出、超时、Runner 重启和业务状态转换没有统一的持久化回合协议。退出码为 0 但阶段未推进时，Runner 会再次领取同一阶段，造成无界空转。

Codex 的 `--ephemeral` 只控制会话文件是否持久化，不定义一次性退出、超时、writer 释放或状态交接。它可以继续用于减少后台会话残留，但不能作为上述问题的生命周期修复。

## 2. 设计目标

本次设计必须实现：

1. Planner 永远由用户当前前台会话承担，Runner 不在后台启动 Planner。
2. Implementer、Reviewer 由 Runner 自动领取、执行、返修和审查。
3. 每个后台 Agent 能无歧义地识别自己的角色、participant、run ID、起始 revision、输入和必需输出。
4. 所有业务阶段转换都通过锁、expected revision、run identity 和原子写入完成。
5. 用户决策文件和对应状态字段在同一事务中生效。
6. 进程退出、超时、中断或 Runner 重启后都能恢复到确定状态，不遗留无法解释的 writer。
7. Agent 成功退出但没有提交合法交接时，不得视为成功，也不得无限重启。
8. 一个项目的故障不影响其他项目；同一项目第一版仍只有一个活动任务和一个后台角色回合。
9. Reviewer 通过后回到前台 Planner，由 Planner 读取证据、总结并向用户交付，然后进入 `DONE`。

## 3. 非目标与权限边界

本版本不实现：

- 自动 merge、push、release、deploy 或生产写入；
- 把自然语言中的“完成”“通过”猜测为合法状态转换；
- 自动唤醒或向一个已经关闭的 Codex/Cursor 聊天窗口注入消息；
- 后台 Planner 或后台需求澄清；
- 同一 checkout 内多个任务同时修改产品代码；
- 跨机器调度或分布式锁；
- 未登记 participant 的自动替换；
- 自动释放无法证明已经停止的外部 writer。

`DONE` 仍只表示需求验收和交付报告完成，不扩大任何发布权限。

## 4. 选择的方案：混合式执行模型

### 4.1 角色执行面

```text
用户
  ⇅
前台 Planner 会话
  ⇅ 仓库状态、问题、决定、计划、最终报告
Runner
  ├─ 后台 Implementer CLI
  └─ 后台 Reviewer CLI
```

角色配置增加明确的执行方式：

```yaml
roles:
  planner:
    execution_mode: foreground
    participant_id: planner-codex
    agent: codex
    model: USER_SELECTED_PLANNER_MODEL
    reasoning_effort: high
  implementer:
    execution_mode: background
    participant_id: implementer-codex
    agent: codex
    model: USER_SELECTED_IMPLEMENTER_MODEL
    reasoning_effort: medium
  reviewer:
    execution_mode: background
    participant_id: reviewer-codex
    agent: codex
    model: USER_SELECTED_REVIEWER_MODEL
    reasoning_effort: high
```

`planner.agent/model/reasoning_effort` 用于初始化提示、身份展示和前台会话一致性检查，不再用于 Runner 构造 Planner 子进程。Runner 的 Adapter Factory 只要求后台角色具有可运行 CLI；Planner CLI 暂时不可用不得阻塞 Implementer 或 Reviewer。

### 4.2 状态与调度

```text
PLANNING
  └─ Runner: waiting_foreground_planner
       前台 Planner 完成计划 → IMPLEMENTING

IMPLEMENTING
  └─ Runner: 启动 Implementer
       合法交付 → REVIEWING

REVIEWING
  ├─ PASS → REPORTING
  ├─ CHANGES_REQUESTED → IMPLEMENTING
  ├─ REPLAN_REQUIRED → PLANNING
  └─ BLOCKED / WAITING_USER

REPORTING
  └─ Runner: waiting_foreground_planner
       前台 Planner 总结交付 → DONE
```

Runner 对 `PLANNING` 和 `REPORTING` 返回稳定的 `waiting_foreground_planner` 决策，不创建 run、不写 writer lease、不消耗模型额度。第一次进入该等待状态时写一条去重通知；后续轮询不重复通知。

用户最小化应用或切换到其他应用时，后台 Implementer 和 Reviewer 可以继续工作。流程到达 `PLANNING`、`REPORTING`、`WAITING_USER` 或 `BLOCKED` 后停止推进并通知用户。由于本地 Runner 没有向既有聊天窗口注入消息的稳定接口，用户需要回到 Planner 会话执行“继续”；Planner 从文件恢复上下文，不依赖旧聊天记录。

## 5. 后台回合契约

### 5.1 启动清单

Runner 为后台角色生成结构化启动清单，至少包含：

```yaml
task_id: TASK-20260919-001
role: implementer
participant_id: implementer-codex
run_id: run-4eb5ae8a5a54
writer_session: run-4eb5ae8a5a54
start_status: IMPLEMENTING
start_revision: 50
stage_round: 2
plan_version: 1
subagent_policy: DO_NOT_USE
required_inputs:
  - requirement.md
  - plan.md
  - previous_progress
required_outputs:
  - execution.md
  - delivery evidence
completion_command: relay_state.py implementation-done ...
```

Agent 提示必须明确说明：

- “你就是 `participant_id`”；
- “本次 Runner 回合 ID 是 `run_id`”；
- “若 `STATE.md.writer_session` 等于该 run ID，这是你的合法 lease，不是 foreign writer”；
- 只有不相等时才按外部 writer 冲突处理；
- 修改前重新读取权威状态；
- 完成后必须调用指定状态命令，不能只在最终回复里描述完成；
- 不能启动下一角色、修改 Reviewer verdict 或越过用户授权边界。

清单同时写入 run 目录的 `launch-context.json`，使日志与启动输入可审计。

### 5.2 成功定义

后台回合成功必须同时满足：

1. 子进程正常退出；
2. 对应业务状态发生了该角色允许的合法转换；
3. 交付、审查或决定引用存在且非空；
4. 状态转换由相同 `run_id`、participant 和 expected revision 提交；
5. Runner 成功关闭该 run 的 writer lease 和运行记录。

退出码为 0 但业务状态仍停留在起始阶段时，结果为 `protocol_failure: no_handoff`，不是成功。

## 6. 原子状态命令

`relay_state.py` 增加下列受约束命令。Agent 不再手工拼接完整 `STATE.md` 交接。

### 6.1 `plan-done`

仅允许当前前台 Planner 从 `PLANNING` 转换到 `IMPLEMENTING`。命令验证 plan、批准/自动批准依据、当前 participant 和 expected revision，原子更新：

- `status`、`current_role`、`current_participant`；
- `previous_role`、`previous_participant`、`previous_progress`；
- `plan_version`、`approval_ref`、`next_expected_output`；
- `stage_round`、`revision`、`updated_at`；
- 对应进度记录和 `PROJECT_STATUS.md` 缓存。

首次实施若 `subagent_policy` 仍为 `UNSELECTED`，状态可以进入 `IMPLEMENTING`，但 Runner 返回 `waiting_user_decision`，不得启动 Implementer。

### 6.2 `answer`

增加严格参数：

```text
--decision-key subagent_policy
--decision-value USE|DO_NOT_USE
```

仅允许白名单 decision key/value。命令在同一个锁和 revision CAS 事务中：

1. 写入不可覆盖的 decision 文件；
2. 更新 `subagent_policy`；
3. 更新 `subagent_decision_ref`；
4. 清理问题字段并恢复 suspended status；
5. 增加 revision。

不能从自由文本猜测 `USE` 或 `DO_NOT_USE`。

### 6.3 `implementation-done`

仅允许当前 Implementer 和当前 `run_id` 从 `IMPLEMENTING` 转到 `REVIEWING`。命令验证：

- plan version 与批准版本一致；
- execution 文件存在；
- delivery reference 存在并包含版本/文件证据；
- 测试记录存在；
- participant、run ID、stage round 和 expected revision 匹配。

命令写入交付引用、前后角色、下一参与者、进度引用、阶段和 revision，但保留当前 run lease，直到子进程真正退出。这样 Reviewer 不会在 Implementer 仍写文件时启动。

### 6.4 `verdict`

保留现有 Reviewer 命令，但增加当前 participant、run ID、review 文件、delivery ID 和 expected revision 校验。合法结果：

- `PASS` → `REPORTING` / Planner；
- `CHANGES_REQUESTED` → `IMPLEMENTING` / Implementer，并增加返修轮数；
- `REPLAN_REQUIRED` → `PLANNING` / Planner，并增加自动重规划次数；
- `BLOCKED` → `BLOCKED`，要求原因和解除条件。

### 6.5 `report-done`

仅允许前台 Planner 从 `REPORTING` 转到 `DONE`。报告必须引用 Reviewer 通过证据、交付版本、测试、限制和明确未执行事项。Planner 不得改变 Reviewer verdict。

## 7. 持久化进程生命周期

### 7.1 Run Worker

Runner 不再直接依赖内存中的 `Popen` 对象作为唯一进程事实。每个后台回合通过一个轻量 Run Worker 启动。Worker：

1. 直接把 stdout、stderr 写入项目 run 目录；
2. 原子写入 `process.json`，包含 PID、进程组、启动时间和命令指纹；
3. 定期写入 `heartbeat.json`；
4. 子进程退出后原子写入 `exit.json`，包含退出码、结束时间和终止原因；
5. 即使 Runner 服务重启，也继续保留可恢复的持久证据。

Run 目录结构：

```text
.agent-relay-auto/runs/{task-id}/{run-id}/
├── metadata.json
├── launch-context.json
├── process.json
├── heartbeat.json
├── exit.json
├── events.jsonl
├── stdout.log
├── stderr.log
└── usage.json
```

### 7.2 超时与心跳

项目策略增加：

```yaml
runtime:
  agent_timeout_minutes: 30
  heartbeat_interval_seconds: 10
  heartbeat_stale_seconds: 45
  interrupt_grace_seconds: 30
```

超时首先向已核对身份的进程组发送可恢复中断，等待 grace period；仍未退出时再终止。Runner 记录 `timeout`，关闭自己的 lease，并按 `max_agent_retries` 决定重试或 `BLOCKED`。

心跳过期本身不证明进程已经停止。只有 PID、启动时间、进程组与命令指纹核对后确认目标不存在，才可以进行自动恢复；身份无法确认时进入 `BLOCKED`，不自动释放 writer。

### 7.3 Runner 重启恢复

Supervisor 启动时扫描 `run_status: starting|running`：

- `exit.json` 已存在：按持久退出结果完成收尾；
- Worker 仍存活且身份匹配：重新进入监控，不重复 claim；
- Worker 已停止且没有 exit 文件：记录 `interrupted_unknown_exit`，安全关闭相同 run ID 的 lease并执行失败策略；
- 状态 run ID 与持久记录不一致：进入 `BLOCKED`，保留全部证据；
- 发现另一个活动 writer：保持只读，不自动接管。

## 8. 失败、重试与防空转规则

Runner 处理结果时先比较 `start_status` 与当前业务状态：

| 进程结果 | 业务状态 | 处理 |
|---|---|---|
| exit 0 | 合法推进 | 完成 run，启动下一后台阶段或等待前台 Planner |
| exit 0 | 未推进 | `protocol_failure: no_handoff` |
| 非零退出 | 任意未完成阶段 | `agent_failure` |
| 超时/中断 | 未推进 | `timeout` / `interrupted` |
| 状态身份冲突 | 任意 | `BLOCKED` |

`protocol_failure` 与进程失败共用 `max_agent_retries`，但 Reviewer 的 `CHANGES_REQUESTED` 不计为 Agent 失败。超过限制后写入明确的 `blocked_reason`、`unblock_condition`、最后 run ID 和日志位置。

相同 `task_id + stage_round + participant_id + start_revision` 不得生成两个活动 run。已完成 claim 的重放返回幂等结果，不创建第二个进程。

## 9. 通知与前台恢复

Runner 在以下事件产生一次去重通知：

- 等待前台 Planner 制定/修订计划；
- 等待前台 Planner 生成最终报告；
- 等待用户回答；
- 任务进入 `BLOCKED`；
- 任务进入 `DONE`；
- Runner 服务或项目配置异常。

通知正文只包含项目、任务、状态、需要的动作和状态文件路径，不包含密钥或完整模型输出。第一版使用项目内通知记录和 macOS 本地通知；不承诺自动聚焦应用窗口。

用户回到 Planner 并执行“继续”后，Planner读取 `PROJECT_STATUS.md`、活动任务 `STATE.md`、上一个进度记录、交付和 Reviewer 证据，再继续当前前台阶段。恢复不依赖原聊天上下文。

## 10. 配置、迁移与兼容性

### 10.1 默认值

新初始化项目默认：

```yaml
roles:
  planner:
    execution_mode: foreground
  implementer:
    execution_mode: background
  reviewer:
    execution_mode: background
```

旧配置缺少 `execution_mode` 时，v1.7.0 按上述默认值解释。不得为了兼容旧行为而继续后台启动 Planner。

### 10.2 升级中的活动回合

安装升级前执行检查：

- 没有活动后台 Planner：可直接升级；
- 存在已停止的旧 Planner lease：通过持久证据和授权修复；
- 存在仍运行的旧后台 Planner：不自动杀死，暂停升级并提示用户先中断或等待完成；
- 当前 Implementer/Reviewer 正在运行：等待本回合结束，或由用户显式中断后再升级。

测试项目的业务状态不会被发行安装器静默修改。需要修复现有任务时，必须运行独立、可审计的 repair 操作。

### 10.3 Skill 与镜像

Canonical Skill、项目模板镜像、安装包、双语文档和已安装 Runner 必须保持版本一致。发行校验应拒绝脚本或协议镜像漂移。

## 11. 测试与验收

### 11.1 状态和调度测试

- `PLANNING` 返回 `waiting_foreground_planner`，不调用 Adapter。
- `REPORTING` 返回 `waiting_foreground_planner`，不调用 Adapter。
- `IMPLEMENTING` 只启动当前 Implementer。
- `REVIEWING` 只启动当前 Reviewer。
- `REPLAN_REQUIRED` 回到前台 Planner，不启动后台 Planner。
- Planner CLI 缺失不阻塞后台角色 Adapter Factory。

### 11.2 身份与原子事务测试

- 启动清单包含 participant、run ID、writer session、revision 和完成命令。
- 相同 run ID 被 Agent 识别为自己的 lease。
- 不同 run ID 仍被识别为冲突。
- `answer` 同时写入 decision、policy、decision ref 和 revision。
- stale revision 不产生部分写入。
- `implementation-done` 缺少 execution、delivery 或测试证据时拒绝转换。

### 11.3 生命周期测试

- exit 0 且阶段推进：正常完成。
- exit 0 但无交接：重试一次，然后 `BLOCKED`。
- 非零退出：按失败限制重试。
- 超时：先中断、后终止，并释放相同 run ID 的 lease。
- Runner 重启时从 process/heartbeat/exit 文件恢复。
- 活进程身份不确定时不得自动释放 writer。
- run 已由合法阶段命令推进时，进程退出收尾具有幂等性。

### 11.4 端到端测试

自动测试用例模拟前台 Planner，而不是由 Fake Adapter 启动 Planner：

```text
前台测试夹具 plan-done
  → Runner Implementer
  → Runner Reviewer PASS
  → Runner waiting_foreground_planner
  → 前台测试夹具 report-done
  → DONE
```

另需覆盖一次 `CHANGES_REQUESTED` 返修、一次 `REPLAN_REQUIRED`、一次 `WAITING_USER` 决策和一次 Runner 中途重启。

### 11.5 真实验收

使用隔离临时项目分别验证 Codex、OpenCode 和 Claude Code：

- 命令确实为非交互单回合；
- 当前 Agent 能识别自己的 run identity；
- 正常交付会进入下一阶段；
- 不交接会被识别为协议失败；
- Runner 重启后没有重复启动同一回合；
- 到达 `REPORTING` 后不产生后台 Planner 进程；
- 前台 Planner 可以仅凭仓库文件生成最终总结并进入 `DONE`。

缺少凭证的 Adapter 可以通过静态和 fixture 测试，但集成表必须标记“待真实会话验证”。

## 12. 文档纠偏

实现时同步修订旧设计与使用文档：

- 删除“Planner 在不需要授权时可由后台 CLI 执行”的默认描述；
- 明确 `--ephemeral` 只控制会话持久化；
- 明确 Planner 最小化时后台角色继续，但最终报告阶段会等待 Planner 回到前台；
- 明确 Runner 日志、heartbeat、exit 和 BLOCKED 证据位置；
- 明确自动模式下用户只需在前台 Planner 处理需求、决定、重规划和最终交付。

## 13. 完成标准

本设计只有在以下条件全部满足后才能宣称实现完成：

1. 所有新增和既有测试通过；
2. Canonical Skill 与模板镜像一致；
3. 发行校验、`git diff --check` 和安装同步检查通过；
4. 安装后的 Runner 版本、服务状态和真实日志经过核对；
5. 隔离项目完成前台 Planner → 后台 Implementer → 后台 Reviewer → 前台 Planner → `DONE` 的真实闭环；
6. 真实闭环没有后台 Planner、重复 claim、stale writer 或无限重试；
7. 未自动执行 merge、push、release、deploy 或其他越权操作。
