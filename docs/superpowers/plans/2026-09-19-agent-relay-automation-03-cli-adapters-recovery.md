# Agent Relay 自动闭环阶段 3：CLI 适配器、中断与恢复 Implementation Plan

> **执行要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（当前会话）或 `superpowers:executing-plans`（独立会话），逐任务执行、验证和提交。

**Goal:** 为 Codex、OpenCode、Claude Code 提供真实、可探测、非交互的适配器，并让 Runner 能安全暂停、中断、恢复及在崩溃后避免重复副作用。

**Architecture:** 每个适配器只负责能力发现、模型查询、命令构造、结构化事件解析、错误分类和原生会话恢复。通用 `RecoveryManager` 负责 PID+启动时间+run_id 核对、信号升级和 checkpoint fallback；无法确认远程任务停止时进入 BLOCKED。

**Tech Stack:** Python 3 标准库、各 CLI 的 JSON/stream-JSON 输出、Codex app-server JSON-RPC、`unittest`、fixture CLI。

**Spec:** `docs/superpowers/specs/2026-09-19-agent-relay-automation-design.md`

**Global Constraints:** 模型列表动态查询；凭证与 token 不落盘；真实会话测试必须用隔离仓库且不修改本项目产品文件；DeepSeek Harness 未经真实验证不得标为自动可用；Cursor 等无稳定非交互入口维持 manual。

---

## Task 1: 固化适配器契约与错误分类

**Files:**
- Modify: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/base.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/discovery.py`
- Create: `tests/test_adapter_contract.py`

**Interfaces:**

```python
class FailureKind(Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH = "auth"
    MODEL_UNAVAILABLE = "model_unavailable"
    PERMISSION = "permission"
    UNSUPPORTED = "unsupported"
    UNKNOWN_REMOTE_RUN = "unknown_remote_run"

@dataclass(frozen=True)
class AdapterCapabilities:
    noninteractive: bool
    model_discovery: bool
    native_resume: bool
    structured_usage: bool
    graceful_interrupt: bool

class AgentAdapter(Protocol):
    def detect(self) -> DetectionResult: ...
    def list_models(self) -> tuple[ModelOption, ...]: ...
    def build_command(self, request: LaunchRequest) -> tuple[str, ...]: ...
    def parse_event(self, line: str) -> AdapterEvent | None: ...
    def classify_exit(self, result: ProcessResult) -> ExitClassification: ...
    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]: ...
```

**Steps:**

1. [ ] 写契约测试，要求三种真实适配器和 fake 适配器具有同一接口；未实现 noninteractive 的适配器不能被 Supervisor 启动。
2. [ ] 写 fixture 错误文本测试，将额度、凭证、模型、权限与临时网络错误区分开；前四类不得消耗普通 retry。
3. [ ] 实现 registry 与共享分类器，保留 raw stderr 仅在已脱敏日志。
4. [ ] 运行 `python3 -m unittest tests.test_adapter_contract -v`。
5. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters tests/test_adapter_contract.py
git commit -m "refactor: formalize agent adapter contract"
```

## Task 2: Codex、OpenCode、Claude Code 适配器

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/codex.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/opencode.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/claude_code.py`
- Create: `tests/fixtures/codex_cli.py`
- Create: `tests/fixtures/opencode_cli.py`
- Create: `tests/fixtures/claude_cli.py`
- Create: `tests/test_codex_adapter.py`
- Create: `tests/test_opencode_adapter.py`
- Create: `tests/test_claude_code_adapter.py`

**Command contracts:**

```text
Codex discovery: codex app-server (JSON-RPC model/list)
Codex execution: codex exec --json --model <id> --cd <repo> <prompt>

OpenCode discovery: opencode models --verbose
OpenCode execution: opencode run --format json --model <provider/model> <prompt>
OpenCode resume: opencode run --format json --session <session-id> <prompt>

Claude execution: claude -p --output-format stream-json --model <id> --effort <level> <prompt>
Claude resume: claude -p --output-format stream-json --resume <session-id> <prompt>
```

实际参数若本机 CLI 帮助与上述不符，先更新测试中的已验证契约和本计划勘误记录，不得静默猜测。

**Steps:**

1. [ ] 为每个 fixture CLI 写失败测试，验证 working directory、模型、推理强度、结构化输出、session ID、usage 和 resume 参数。
2. [ ] Codex 模型发现通过 app-server 的 `model/list`，为测试实现受控 JSON-RPC fixture；app-server 失败时返回不可确认状态，不回退硬编码列表。
3. [ ] OpenCode 解析 `models --verbose`，保留完整 `provider/model` ID；同名 Skill 优先级不属于 CLI 适配器，不在此处复制 Skill。
4. [ ] Claude 使用 `--print` 非交互模式、`stream-json` 和明确 permission mode；`--max-budget-usd` 只在用户配置时传入。
5. [ ] 所有 prompt 只包含角色入口、STATE/计划/交付证据路径和必须执行的合法状态命令，不内联整个仓库内容。
6. [ ] 运行：

```bash
python3 -m unittest tests.test_codex_adapter tests.test_opencode_adapter tests.test_claude_code_adapter -v
```

7. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters tests/fixtures tests/test_codex_adapter.py tests/test_opencode_adapter.py tests/test_claude_code_adapter.py
git commit -m "feat: add codex opencode and claude cli adapters"
```

## Task 3: 安全暂停、立即中断和恢复

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/recovery.py`
- Modify: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/process_manager.py`
- Create: `tests/fixtures/signal_agent_cli.py`
- Create: `tests/test_interrupt_recovery.py`

**Interfaces:**

```python
class RecoveryMode(Enum):
    NATIVE_SESSION = "native-session"
    CHECKPOINT_RESTART = "checkpoint-restart"
    UNSUPPORTED = "unsupported"

class RecoveryManager:
    def request_safe_pause(self, task_id: str, run_id: str) -> None: ...
    def interrupt(self, task_id: str, run_id: str, grace_seconds: float = 30.0) -> InterruptResult: ...
    def reconcile(self, run: RunMetadata) -> ReconcileResult: ...
    def resume(self, task_id: str, expected_revision: int) -> str: ...
```

**Steps:**

1. [ ] 写 signal fixture：SIGINT 正常退出、忽略 SIGINT 后 SIGTERM、遗留子进程、输出 checkpoint 四种行为。
2. [ ] 写失败测试，验证先 SIGINT、默认 30 秒（测试注入 0.05 秒）后 SIGTERM；默认永不 SIGKILL。
3. [ ] 写 PID 复用测试：PID 相同但 `process_started_at` 不同，必须判定不是原进程。
4. [ ] 写恢复测试：native session 使用新 run ID 和原 stage round；checkpoint restart 先读取实际 git diff/测试/副作用；Reviewer 部分日志不能生成 PASS。
5. [ ] 实现安全暂停请求文件、信号发送、进程组核对、writer session 释放和 `execution: paused` 状态更新。
6. [ ] 无法确认远程会话结束时，转换为 `BLOCKED / UNKNOWN_REMOTE_RUN`，禁止重复启动。
7. [ ] 运行 `python3 -m unittest tests.test_interrupt_recovery -v`。
8. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime tests/fixtures/signal_agent_cli.py tests/test_interrupt_recovery.py
git commit -m "feat: add safe interrupt and recovery semantics"
```

## Task 4: Runner 重启对账与跨项目并行验证

**Files:**
- Modify: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/runner.py`
- Modify: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/supervisor.py`
- Create: `tests/test_runner_reconciliation.py`
- Create: `tests/test_cross_project_concurrency.py`

**Steps:**

1. [ ] 写 Runner 崩溃 fixture：子进程继续运行，重启后必须接管监控而非重复启动。
2. [ ] 写已停止进程测试：按 adapter recovery mode 恢复；无法确认远程状态时 BLOCKED。
3. [ ] 写两个临时项目并发计时测试，两个 0.5 秒 Agent 总墙钟时间应小于 0.9 秒；同项目两个任务仍不得重叠。
4. [ ] 实现启动扫描 `.agent-relay/runtime/current-runs.json`，使用 PID、启动时间、run_id 三元组对账。
5. [ ] 对账事件写入全局和项目日志，并将结论写入任务 progress/checkpoint，不只留在临时 stdout。
6. [ ] 运行：

```bash
python3 -m unittest tests.test_runner_reconciliation tests.test_cross_project_concurrency -v
```

7. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime tests/test_runner_reconciliation.py tests/test_cross_project_concurrency.py
git commit -m "feat: reconcile runner restarts and preserve project parallelism"
```

## Phase Acceptance

1. [ ] `python3 -m unittest discover -s tests -v`
2. [ ] `bash .github/scripts/validate-release.sh`
3. [ ] `git diff --check`
4. [ ] 只读执行 `codex --help`、`opencode --help`、`claude --help` 并把版本/能力写入验证记录。
5. [ ] 在无凭证环境验证错误如实分类且不伪造“已验证”。
6. [ ] 在有凭证时，每个适配器只在隔离临时仓库完成一次最小真实会话；结果写入 `docs/verification/`，失败不阻断其他适配器。
7. [ ] 确认没有修改用户级 CLI 登录状态，没有推送或发布。
