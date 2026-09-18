# Agent Relay Auto 项目介绍

Agent Relay Auto 是一个轻量级多 Agent 接力协作框架。它把原本停留在聊天窗口里的需求、计划、决策、实施证据和审查结论，保存为代码仓库中的可读文件，让不同 Agent、模型、电脑和工作环境可以围绕同一个项目继续工作。

它的核心不是让 Agent 共享一段对话，而是让 Agent 共享一份可验证的项目状态：

```text
需求 → 计划 → 实施 → 审查 → 返修 → 验证 → 交付
                  ↓
        项目文件成为长期上下文
```

## 它解决什么问题

单个对话无法可靠承担长期软件工程协作：上下文会截断，模型会更换，Agent 可能耗尽额度，聊天窗口也可能关闭。若关键决定只存在于对话中，下一位参与者就必须重新猜测背景，容易出现重复工作、越权修改和错误交接。

Agent Relay Auto 将这些信息沉淀在项目仓库中，包括：

- 需求、范围、非目标和验收标准；
- 架构约束、决策和风险；
- 实施记录、测试结果和交付版本；
- 独立 Reviewer 的问题、结论和返修要求；
- 当前任务、角色绑定、revision 和下一位参与者。

因此，切换 Agent 不等于丢失项目认知。新 Agent 读取项目状态和上一个交接记录，就可以恢复工作。

## 三个稳定角色

角色与具体工具解耦。同一个工具可以承担多个角色，同一个角色也可以在工具之间切换。

| 角色 | 主要职责 | 边界 |
| --- | --- | --- |
| Planner | 澄清范围、生成计划、记录决策和验收标准 | 不修改产品代码；范围扩大或需求歧义时请求用户决策 |
| Implementer | 按批准计划修改代码、编写测试、记录实施证据并处理返修 | 不自行批准交付；必须把结果交给 Reviewer |
| Reviewer | 独立检查需求、计划、差异、测试和交付证据 | 不直接修复产品代码；通过后才能形成完成结论 |

标准闭环是：

```text
Planner
  ↓ plan.md
Implementer
  ↓ execution.md + tests
Reviewer
  ├─ 通过 → 交付报告 → DONE
  ├─ 需修改 → Implementer 返修 → 再审查
  ├─ 需重规划 → Planner 重规划
  └─ 无法继续 → BLOCKED，等待用户处理
```

`DONE` 只表示需求验收完成，不代表自动合并、推送、发布、部署或接受高风险操作。

## 项目状态如何保存

初始化后，项目会拥有一个共享的状态区域。实际项目任务位于 `docs/agent/tasks/<TASK-ID>/`，典型结构如下：

```text
docs/agent/
├── PROJECT_STATUS.md       # 项目入口、活动任务和当前阶段
├── knowledge-index.md      # 已验证的长期项目认知
├── role-bindings.md        # 角色与 participant_id 绑定
├── profiles/               # 参与者的工具、角色和能力信息
└── tasks/<TASK-ID>/
    ├── STATE.md            # 任务的唯一实时状态源
    ├── requirement.md      # 需求、范围和验收标准
    ├── plan.md             # Planner 的计划和决策
    ├── execution.md        # Implementer 的实施和测试证据
    ├── review.md            # Reviewer 的审查结论
    ├── decisions.md        # 需要长期保留的决定
    └── progress/            # 追加式阶段记录
```

`STATE.md`、`revision`、角色绑定和交接记录共同防止过期 Agent 覆盖新的项目状态。更换 Agent 时，旧身份、原因、授权和交接范围会被保留，支持 `A → B → A` 多次来回切换。

## 支持的 Agent

当前统一协议支持以下工具 ID：

| 工具 | ID |
| --- | --- |
| Codex | `codex` |
| Cursor | `cursor` |
| Claude Code | `claude-code` |
| WorkBuddy | `workbuddy` |
| ZCode | `zcode` |
| Trae | `trae` |
| DeepSeek Harness | `deepseek-harness` |
| OpenCode | `opencode` |
| Other | 用户提供稳定 ID |

DeepSeek Harness 和 OpenCode 复用根目录 `AGENTS.md`、`.agents/skills/agent-relay-auto/` 和 `docs/agent/`，不会生成重复的私有协议目录。

## 快速开始

### 安装

将 `agent-relay-auto` 安装为个人 Skill，或从 [最新发行版](https://github.com/MJHuang666/agent-relay-auto/releases/latest) 下载发行包。项目仓库初始化后，也会复制项目所需的本地 Skill 和模板文件。

### 初始化当前仓库

```text
$agent-relay-auto 初始化当前仓库
# 或
$agent-relay-auto initialize this repository
```

初始化时选择项目语言、Planner/Implementer/Reviewer 的 Agent，以及自动模式的策略。初始化器只补齐缺失文件，不覆盖已有项目状态或产品代码。

### 继续当前任务

```text
$agent-relay-auto 继续
# 或
$agent-relay-auto continue
```

Agent 会先读取总项目状态、任务状态、自己的 Profile 和上一阶段交付物。如果还没有轮到自己，只读报告当前等待的角色；轮到自己时才执行对应职责。

### 更换角色 Agent

```text
$agent-relay-auto 更换agent
$agent-relay-auto 替换agent
# 或
$agent-relay-auto switch agent
$agent-relay-auto replace agent
```

更换使用短时文件锁、expected revision 和原子写入辅助脚本，避免两个会话同时更新同一个角色。切换不会清除历史记录，也不要求新 Agent 使用同一个模型。

完整命令和初始化问题请阅读：[中文使用手册](AGENT_RELAY_AUTO_USAGE.md)。

## 手动模式与自动 Runner

### 手动/文件协作模式

这是当前最稳定的使用方式。用户打开当前角色对应的 Agent，执行 `继续`，Agent 根据仓库中的状态工作并写下交接结果。不同项目之间可以并行；每个项目的状态彼此隔离。

### 自动 Runner 模式

自动版包含 Runner、运行配置、日志和恢复设计，目标是让合法状态转换自动启动下一角色，并在 Reviewer 写出完整证据后进入 `DONE`。初始化时可按项目选择最大返修轮数、重规划次数、失败重试、成本提醒和备用 Agent 切换。

当前版本的自动 Runner 仍属于实验性能力，部分运行时适配和控制命令正在修复，不能把它当作已经完成生产验收的无人值守服务。启用前应先阅读验证报告；遇到不确定、权限、密钥或高风险操作时，应进入 `BLOCKED` 并交给用户。

无论手动还是自动模式，Runner 都不拥有合并、推送、发布、部署或生产写入权限。

## 安全与协作边界

- 项目文件是状态来源，但不是 Git 的替代品；重要交付仍应提交并核对版本。
- 锁只保护单个 checkout 的协调状态，不锁产品代码，也不协调多台机器。
- Reviewer 负责独立验收，不直接改产品代码。
- `DONE` 是验收状态，不是发布授权。
- 凭证、需求歧义、范围扩大和高风险外部操作不能由 Runner 猜测处理。
- 不同 Agent 之间应通过 `docs/agent/` 交接，而不是依赖某个聊天窗口仍然存在。

## 项目目录中的主要内容

```text
.agents/skills/agent-relay-auto/   共享 Skill、参考文档和状态辅助脚本
codex/                             Codex 的入口和提示文件
cursor/                            Cursor 的入口和提示文件
shared/docs/agent/                 初始化模板、协议和角色 Profile
docs/                              项目说明、使用手册和验证报告
compat/                            旧命令名的兼容入口
```

欢迎通过 Issue 或 Pull Request 改进协议、文档和验证用例。请先阅读 [贡献指南](../CONTRIBUTING.md)、[安全政策](../SECURITY.md) 和 [变更记录](../CHANGELOG.md)。本项目使用 [Apache-2.0](../LICENSE) 许可证。
