# Agent Relay Auto 原 Planner 会话自动回报设计

日期：2026-09-20

状态：会话设计已批准，书面规格等待用户审阅

目标版本：v1.8.0

适用范围：`/Volumes/HP P900/mjwork/多agent项目状态共享自动版`

## 1. 背景与问题

v1.7.0 已将 Planner 固定为前台用户会话，Runner 只在后台调度 Implementer 和 Reviewer。这解决了 Planner 需要实时与用户沟通的问题，但当 Reviewer 通过并将任务推进到 `REPORTING` 后，用户仍需回到 Planner 窗口手动输入“继续”，Planner 才会读取证据、生成最终报告并进入 `DONE`。

本设计消除这个最后的人工接力点：Runner 用零 Token 的本地轮询检测 `REPORTING`，恢复原 Planner 会话，向该会话提交一次受约束的最终回报请求，并让结果自动出现在原 Planner 对话中。

## 2. 已批准的产品边界

1. Runner 每 45 秒检查一次本地状态；空闲检查不调用模型。
2. Reviewer 写入有效 `PASS` 和证据后，任务自动进入 `REPORTING`。
3. Runner 必须恢复原 Planner 会话，不得创建新会话代替。
4. Planner 窗口最小化、关闭或应用已退出时，允许 Runner 启动应用并重新打开原会话。
5. 重新创建的窗口可以是新的操作系统窗口，但其承载的必须是原 `thread_id/session_id` 对应的会话。
6. Planner 读取项目文件中的计划、实施、测试和 Review 证据，生成最终报告，并且只能通过受约束的 `report-done` 将任务转为 `DONE`。
7. `DONE` 仍仅表示需求验收和交付报告完成，不授权 merge、push、release、deploy 或其他高风险操作。
8. 第一版支持 Codex、OpenCode、Claude Code 和 DeepSeek Harness Planner；Cursor 暂不支持。
9. 未通过真实端到端会话恢复测试的工具只能标记为“实验性”，不得宣称正式支持。

## 3. 非目标

本版本不实现：

- Cursor Planner 的原会话唤醒；
- 通过创建新会话来伪装原会话恢复；
- Runner 代替 Planner 理解或总结交付；
- Runner 代替 Reviewer 判定验收通过；
- 空闲轮询时调用模型或持续占用 Planner Token；
- 跨机器会话恢复或分布式调度；
- 因打开界面失败而重复调用模型；
- 自动合并、推送、发布或部署。

## 4. 选择的架构：工具专用会话桥接器

为不同 Planner 工具实现独立桥接器，共用一个稳定接口：

```python
class PlannerWakeAdapter:
    def probe(self, channel) -> CapabilityResult: ...
    def resume(self, channel) -> ResumeResult: ...
    def submit_report(self, channel, request) -> SubmissionReceipt: ...
    def observe(self, receipt) -> CompletionResult: ...
    def present(self, channel) -> PresentationResult: ...
```

调用顺序：

```text
probe
  → resume 原会话
  → submit_report 提交一次回报请求
  → observe 等待 Planner 完成
  → present 打开原会话界面
  → 核对 STATE.md 的最终状态
```

`submit_report` 一旦返回持久回执，后续 `present` 失败也不得重复提交模型请求；只能重试打开界面。

### 4.1 CodexPlannerBridge

- 使用 Codex App Server 读取并恢复已登记 `thread_id`。
- 通过 `turn/start` 向相同 Thread 提交回报请求。
- 等待 `turn/completed`，并将 Turn 回执与 `wake_key` 关联。
- 启动 Codex 并定位到原任务。
- “会话恢复”和“桌面界面精确定位”分别探测，两者都验证后才能标记完整支持。

### 4.2 OpenCodePlannerBridge

- 使用显式 `session_id`，不使用含义不稳定的“最近会话”。
- 使用 `opencode run --session <id>` 向原会话提交回报。
- 使用 `opencode <project> --session <id>` 启动或恢复 TUI。
- 不得使用 `--fork`。

### 4.3 ClaudeCodePlannerBridge

- 使用 `claude -p --resume <session-id>` 在原会话中执行回报轮次。
- 解析 JSON 输出并核对返回的 `session_id`。
- 使用 `claude --resume <session-id>` 重新打开交互终端。
- 不得使用只表示最近会话的 `--continue`。

### 4.4 DeepSeekHarnessPlannerBridge

- 优先通过 ACP/API 恢复持久 `session_id`。
- 向恢复的 Agent 调用 `followup()`，并等待 Agent 进入 idle。
- 用 `dsh --profile tui --resume <session-id>` 作为可验证的原会话界面恢复路径。
- Web UI 只在能通过稳定 URL 或官方接口定位指定 Session 后才列为支持的展示面。
- 发布状态由真实端到端测试决定；源码级兼容不等于“已验证”。

## 5. 会话注册与本机状态

Planner 首次创建任务或旧项目首次迁移时，Skill 尝试自动登记当前会话：

```yaml
schema_version: 1
project_id: agent-relay-auto
participant_id: planner-codex
tool: codex
conversation_id: thr_xxx
project_path: /absolute/project/path
registered_at: 2026-09-20T10:00:00+08:00
```

文件位于：

```text
.agent-relay-auto/planner-channel.yaml
```

`.agent-relay-auto/` 是本机运行目录，必须加入 `.gitignore`。会话 ID、机器绝对路径、PID 和界面状态不得提交。可移植的任务计划、进度、证据和报告继续保存在 `docs/agent/`。

运行目录至少包含：

```text
.agent-relay-auto/
├── planner-channel.yaml
├── wake-events.jsonl
├── runner.pid
└── logs/
    ├── runner.log
    └── planner-wake.log
```

如果 Skill 无法自动识别当前会话，不要求用户手写 Adapter 配置或查找 ID。它应引导用户在希望作为 Planner 的原会话中再次执行 `$agent-relay-auto 继续`，由 Skill 完成登记。

## 6. 轮询、幂等与回执

Runner 默认每 45 秒只读检查项目状态。非 `REPORTING` 时不创建会话、不提交 Prompt、不调用模型。

每次回报唤醒的幂等键为：

```text
task_id + revision + planner_participant_id + conversation_id
```

`wake-events.jsonl` 记录：

```json
{
  "wake_key": "TASK-001:18:planner-codex:thr_xxx",
  "status": "completed",
  "attempt": 1,
  "receipt_id": "turn_xxx"
}
```

必须区分三个不同事实：

1. 请求未提交：可安全重试。
2. 请求已提交但未观察到结果：必须先查询原会话或回执，不得盲目重发。
3. Planner 已完成而 Runner 未及时看到：以 `STATE.md == DONE` 为准，只补写本地运行记录。

## 7. 状态机和报告子状态

主状态保持兼容：

```text
REVIEWING
  │ Reviewer PASS
  ▼
REPORTING
  │ 原 Planner 验证证据并 report-done
  ├─→ DONE
  └─→ BLOCKED
```

Runner 运行细节作为 `REPORTING` 的子状态：

```yaml
status: REPORTING
reporting:
  phase: active
  wake_key: TASK-001:18:planner-codex:thr_xxx
  attempt: 1
  receipt_id: turn_xxx
  started_at: 2026-09-20T10:00:00+08:00
  last_heartbeat_at: 2026-09-20T10:00:20+08:00
```

子状态至少覆盖 `pending`、`submitted`、`active`、`completed`、`failed` 和 `presentation_failed`。主状态仍是其他 Agent 的协调权威，子状态不得绕过原有角色和 revision 规则。

## 8. Planner 唤醒请求

Runner 只发送固定协议消息，不自行生成任务结论：

```text
任务已到达 REPORTING。

请恢复 Planner 身份，从项目状态文件读取当前任务，不依赖本条消息中的任务结论。

必须依次完成：
1. 校验 task_id、revision、participant_id 和 Reviewer PASS。
2. 读取计划、实施记录、测试证据、Review 结论和交付引用。
3. 证据完整时，生成最终交付报告并执行 report-done。
4. 证据缺失、状态冲突或任务并非由你负责时，不得推测完成；记录原因并进入 BLOCKED。
5. 不得修改产品代码，不得执行 merge、push、release 或 deploy。

wake_key: ...
expected_task_id: ...
expected_revision: ...
```

Planner 必须从文件重建上下文，而不是相信唤醒消息已经概括了交付结果。

## 9. Revision、锁和 `report-done`

Runner 可以基于 revision N 创建唤醒请求，但 Planner 在执行任何写入前必须重新读取权威状态。如果状态已变为 revision N+1，旧请求作废，Runner 重新判断新 revision 是否仍需唤醒。

`report-done` 至少校验：

- `task_id`；
- `expected_revision`；
- `planner_participant_id`；
- `wake_key`；
- Reviewer `PASS` 证据；
- `review_delivery_id`；
- 最终报告引用。

全部校验通过后，在现有项目锁和 expected-revision CAS 事务中原子更新 `STATE.md`、`PROJECT_STATUS.md` 与进度文件。Runner 本身不得直接写入 `DONE`。

## 10. 崩溃、中断和重试

### 10.1 Runner 在提交前退出

没有持久回执，下次检查可以安全重试。

### 10.2 Runner 在提交后、保存回执前退出

恢复后先查询原会话、目标任务状态和已有 `wake_key`，确认未提交前不得重发。

### 10.3 Planner 轮次被中断

保持 `REPORTING`，记录最后心跳。只有在实际轮次或进程已终止得到证明后，才可恢复相同会话。

### 10.4 Planner 已完成，Runner 未观察到

`STATE.md == DONE` 是业务完成权威。Runner 只补写本地回执和日志，不重新唤醒。

### 10.5 重试配置

模型执行重试复用现有“Agent 失败重试”项；默认为 1，表示首次尝试后最多再试 1 次。界面打开重试不调用模型：

```yaml
reporting:
  model_retry_limit: 1
  presentation_retry_limit: 3
  presentation_retry_interval_seconds: 10
```

原会话无法恢复时，任务不得进入 `DONE`；超出重试后进入 `BLOCKED`并记录解除条件。如果任务已经 `DONE` 而只是界面打开失败，保持 `DONE`，发系统通知并让用户手动打开原会话，不再调用模型。

## 11. 初始化与迁移体验

`$agent-relay-auto 初始化当前仓库` 在完成语言、角色、Agent 和模型选择后，自动：

1. 识别当前 Planner 会话；
2. 获取 `thread_id/session_id`；
3. 探测会话恢复能力；
4. 探测本机应用或 TUI 启动能力；
5. 显示完整配置摘要；
6. 经用户确认后保存并启用自动回报。

可提交配置例如：

```yaml
runner:
  poll_interval_seconds: 45

reporting:
  enabled: true
  reopen_original_conversation: true
  launch_application_if_closed: true
  require_same_conversation: true
  model_retry_limit: 1
  presentation_retry_limit: 3
  presentation_retry_interval_seconds: 10
```

旧项目升级后第一次执行 `$agent-relay-auto 继续` 时，如果缺少 Planner Channel，Skill 应询问是否将当前会话登记为原 Planner 会话。选择“否”不修改现有任务。

## 12. Planner 替换

替换 Planner Agent 时，角色保持 Planner，但必须替换后续唤醒目标的会话绑定：

- 保留旧 participant 和旧会话的不可变交接记录；
- 新会话成为后续自动回报目标；
- 旧 `wake_key` 不迁移到新会话；
- 正在执行的回报必须先完成或中断，不得在 active 轮次中直接替换；
- A → B → A 可重新使用旧的稳定 participant ID，但必须重新确认目标会话。

替换操作继续使用项目锁、expected revision 和原子写入，不与产品代码修改合并为一次操作。

## 13. 能力探测与支持等级

每个桥接器分别记录：

```yaml
capabilities:
  resume_original_conversation: verified
  submit_turn: verified
  reopen_original_ui: verified
  end_to_end_reporting: verified
```

只有四项均为 `verified` 才能在初始化界面和集成表中显示“已验证”。其他状态为：

- `experimental`：用户可选，但必须明确告知端到端验证未完成；
- `static_only`：仅源码或接口层兼容，默认不启用；
- `unavailable`：当前本机不可选。

DeepSeek Harness 起始状态为 `static_only` 或 `experimental`，只有真实 Session 的恢复、followup、报告和界面定位全部验证后才提升。

## 14. 日志、可观测性与敏感信息

`planner-wake.log` 和 `wake-events.jsonl` 至少记录：

- project ID、task ID、revision 和 participant ID；
- Planner tool 和经最小化处理的会话 ID；
- `wake_key`、attempt、receipt ID 和阶段时间；
- 能力探测、恢复、提交、完成观察和界面展示的独立结果；
- 模型调用次数与可用时的 provider usage；
- 失败类型、可重试性和解除条件。

日志不记录凭证、完整 Prompt、完整对话或不必要的绝对路径。会话 ID 只存放在本机忽略目录。

## 15. 测试与验收

### 15.1 单元和状态机测试

必须覆盖：

- Planner Channel 的序列化、忽略和项目归属校验；
- 幂等 `wake_key` 和重启去重；
- revision 变化后旧唤醒作废；
- 提交回执与界面展示重试的分离；
- Runner 无权直接写入 `DONE`；
- 会话丢失不得创建替代会话；
- Planner A → B → A 切换和过期回执隔离；
- `REVIEWING → REPORTING → DONE/BLOCKED`；
- `REPORTING → 中断 → REPORTING → DONE`；
- Runner 重启、项目移动、多 Runner 冲突和多项目并行。

### 15.2 工具端到端测试

每个工具在隔离临时仓库中执行同一验收流程：

1. 登记一个真实原 Planner 会话。
2. 创建最小任务并准备有效的 Implementer 交付和 Reviewer `PASS`。
3. 任务进入 `REPORTING` 后，不再输入“继续”。
4. 在一个轮询周期加合理启动时间内，原会话自动收到回报请求。
5. Planner 读取真实证据，生成报告并执行 `report-done`。
6. 任务进入 `DONE`，最终总结出现在原会话。
7. 会话列表和日志证明没有产生新 Planner 会话。

每个工具还需独立验证：

| 工具 | 必须验证 |
|---|---|
| Codex | 原 `thread_id`、App Server 恢复、Turn 回执、原任务界面 |
| OpenCode | 原 `session_id`、精确 CLI 恢复、TUI 展示 |
| Claude Code | 原 `session_id`、非交互回报、交互终端恢复 |
| DeepSeek Harness | 原 `session_id`、ACP/API `followup`、Agent idle、TUI/Web 原会话 |

### 15.3 故障注入

至少测试：

- Runner 在提交前退出；
- Runner 在提交后、保存回执前退出；
- Planner 执行中被终止；
- Planner 应用完全退出；
- 电脑休眠后恢复；
- 会话 ID 不存在或归属另一项目；
- Planner 额度耗尽或 provider 不可用；
- 唤醒期间 revision 变化；
- 项目目录移动；
- 同一项目启动两个 Runner；
- 两个不同项目同时到达 `REPORTING`。

### 15.4 Token 验收

通过日志证明：

- 空闲轮询连续多个周期时，模型调用数为 0；
- 正常任务只增加一次最终 Planner 回报调用；
- 打开界面失败不增加模型调用；
- Runner 重启和幂等恢复不产生重复报告；
- 每次模型调用可关联 `task_id`、`wake_key` 和回执 ID。

## 16. 最终用户体验

```text
初始化并配置一次
  → 在原 Planner 会话提出任务
  → Planner 完成计划
  → Runner 自动调度 Implementer
  → Runner 自动调度 Reviewer
  → Reviewer PASS
  → Runner 在 45 秒轮询周期内检测 REPORTING
  → 自动恢复原 Planner 会话
  → Planner 自动总结并 report-done
  → 用户直接在原会话看到最终结果
```

正常流程中，用户不需要再输入“继续”。

## 17. 交付要求

实施阶段至少需要更新：

- Runner 核心、状态助手、日志与服务控制；
- 四个 Planner 桥接器与能力探测；
- Skill 中英文初始化、继续、替换和故障排查流程；
- 模板仓库文件、README、使用手册、集成能力表和发行说明；
- 同步的可安装 Skill 副本；
- CI 漂移校验、状态机测试、桥接器契约测试和真实端到端验证记录；
- v1.8.0 Skill 包、SHA-256 文件和本机安装同步校验。

实施计划必须在功能代码修改前单独完成并经用户批准。任何提交、测试或打包都不自动授权推送 GitHub、创建 Release 或合并分支。
