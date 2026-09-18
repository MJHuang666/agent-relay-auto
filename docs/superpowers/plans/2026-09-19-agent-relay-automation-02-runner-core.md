# Agent Relay 自动闭环阶段 2：Runner 核心 Implementation Plan

> **执行要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（当前会话）或 `superpowers:executing-plans`（独立会话），逐任务执行、验证和提交。

**Goal:** 建立不替 Agent 做业务判断的本地 Runner，使不同项目可并行、同一项目严格串行，并用假适配器验证自动领取、返修、重规划、报告和 DONE 闭环。

**Architecture:** 一个常驻 Runner 管理项目注册表，每个项目一个独立 `ProjectSupervisor`。Supervisor 只观察权威文件状态、CAS 领取并启动适配器；所有下一阶段选择来自合法状态转换。进程、日志和通知通过可注入接口隔离，测试不依赖真实模型或 launchd。

**Tech Stack:** Python 3 标准库、`unittest`、`subprocess`、JSONL、macOS `osascript`（仅通知实现）。

**Spec:** `docs/superpowers/specs/2026-09-19-agent-relay-automation-design.md`

**Global Constraints:** 不设机器级并发上限；每项目一个活动任务和一个角色进程；Runner 不从自然语言猜 verdict；不保管密钥；本阶段不接真实 Codex/OpenCode/Claude。

---

## Task 1: 配置、项目注册表和运行快照

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/config.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/registry.py`
- Create: `tests/test_runtime_config.py`
- Create: `tests/test_project_registry.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class AutomationPolicy:
    max_rework_rounds: int = 3
    max_auto_replans: int = 1
    max_agent_retries: int = 1
    allow_same_role_fallback: bool = False

@dataclass(frozen=True)
class CostControl:
    mode: str = "balanced"
    warn_after_agent_runs: int = 8
    stop_after_agent_runs: int = 12
    require_confirmation_after_warning: bool = False
    record_provider_usage: bool = True

class ProjectRegistry:
    def register(self, repo: Path) -> None: ...
    def enabled_projects(self) -> tuple[Path, ...]: ...
```

**Steps:**

1. [ ] 写失败测试，覆盖默认值、自定义预设、无效负数、备用 Agent 默认关闭、重复/移动项目注册和项目运行快照不随用户默认值变化。
2. [ ] 运行 `python3 -m unittest tests.test_runtime_config tests.test_project_registry -v`，确认失败。
3. [ ] 实现受限 YAML 读取和 dataclass 验证；用户级文件默认位于 `~/.config/agent-relay/`，测试必须注入临时目录。
4. [ ] 项目注册表仅保存规范化路径、启用状态和最后观察 revision，不保存源码或密钥。
5. [ ] 运行测试，预期通过。
6. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime tests/test_runtime_config.py tests/test_project_registry.py
git commit -m "feat: add relay runtime configuration and registry"
```

## Task 2: 运行目录、结构化事件、脱敏和轮转

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/run_store.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/redaction.py`
- Create: `tests/test_run_store.py`
- Create: `tests/test_redaction.py`

**Interfaces:**

```python
class RunStore:
    def create(self, metadata: RunMetadata) -> Path: ...
    def append_event(self, run_id: str, event: Mapping[str, object]) -> None: ...
    def write_heartbeat(self, run_id: str, heartbeat: Mapping[str, object]) -> None: ...
    def finish(self, run_id: str, exit_code: int, usage: Mapping[str, object] | None) -> None: ...
    def cleanup(self, now: datetime) -> tuple[Path, ...]: ...

def redact_text(text: str, secret_names: Iterable[str], environment: Mapping[str, str]) -> str: ...
```

**Steps:**

1. [ ] 写失败测试，要求目录包含 `metadata.json`、`events.jsonl`、stdout/stderr、usage、heartbeat；10 MB 后轮转且最多 5 份。
2. [ ] 写脱敏测试，覆盖 Authorization Bearer、常见 API key 名、已知环境变量值；不得修改普通模型 ID。
3. [ ] 写清理测试：DONE 超过 30 天可删；活动/BLOCKED 永不自动删；仓库 `progress/` 等长期证据不在清理范围。
4. [ ] 实现并在每次落盘前脱敏；provider usage 缺失时写 `{"status":"unavailable"}`，不得估算。
5. [ ] 运行 `python3 -m unittest tests.test_run_store tests.test_redaction -v`。
6. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime tests/test_run_store.py tests/test_redaction.py
git commit -m "feat: add runner audit logs and redaction"
```

## Task 3: 进程管理、假适配器和 Supervisor

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/__init__.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/base.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/adapters/fake.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/process_manager.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/supervisor.py`
- Create: `tests/fixtures/fake_agent_cli.py`
- Create: `tests/test_process_manager.py`
- Create: `tests/test_supervisor.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class LaunchRequest:
    repo: Path
    task_id: str
    role: str
    participant_id: str
    model: str
    reasoning: str | None
    run_id: str
    expected_revision: int

class AgentAdapter(Protocol):
    def capabilities(self) -> AdapterCapabilities: ...
    def build_command(self, request: LaunchRequest) -> tuple[str, ...]: ...
    def classify_exit(self, result: ProcessResult) -> ExitClassification: ...

class ProjectSupervisor:
    def tick(self) -> SupervisorDecision: ...
```

**Steps:**

1. [ ] 写假 CLI，可按 fixture 参数模拟成功、合法转换缺失、暂时失败、额度失败、长时间运行和结构化 usage。
2. [ ] 写失败测试证明 Supervisor 在同一 revision 只启动一次，运行中不会再次启动，同项目第二任务不启动，不同 Supervisor 不共享锁或队列。
3. [ ] 写失败测试证明 Runner 只在 Agent 已落盘合法 transition 后推进；stdout 中出现 `PASS` 不改变状态。
4. [ ] 运行 `python3 -m unittest tests.test_process_manager tests.test_supervisor -v`，确认失败。
5. [ ] 实现 `Popen(start_new_session=True)`、stdout/stderr 流式写入、heartbeat 和退出分类；命令参数用 tuple，不经 shell。
6. [ ] Supervisor 流程固定为：读取→验证→选择角色→CAS claim→创建 run→启动→监控→重新读取状态→记录结果。
7. [ ] 运行测试，预期通过。
8. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime tests/fixtures/fake_agent_cli.py tests/test_process_manager.py tests/test_supervisor.py
git commit -m "feat: add project supervisor and fake agent adapter"
```

## Task 4: Runner 主循环、通知和完整假闭环

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/notifications.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/runner.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runner.py`
- Create: `tests/test_notifications.py`
- Create: `tests/test_runner_integration.py`

**Interfaces:**

```python
class Notifier(Protocol):
    def notify(self, project: str, task_id: str, state: str, reason: str) -> None: ...

class RelayRunner:
    def run_once(self) -> tuple[SupervisorDecision, ...]: ...
    def serve(self, poll_interval_seconds: float = 2.0) -> None: ...
    def stop(self) -> None: ...
```

**Steps:**

1. [ ] 写失败集成测试：Planner→Implementer→Reviewer→REPORTING→Planner→DONE，并断言没有 merge/push/release/deploy 命令。
2. [ ] 增加 Reviewer 返修三次以内成功、第四次 BLOCKED；一次重规划后成功、第二次 BLOCKED；第 8 run 警告、第 12 run 后阻止下一启动。
3. [ ] 增加 WAITING_USER/BLOCKED/DONE 通知测试；通知器必须可替换为空实现，测试不得弹真实通知。
4. [ ] 实现 Runner 的 signal handler、项目级异常隔离和全局 JSONL 服务事件；一个项目异常不得停止其他 Supervisor。
5. [ ] macOS 通知只调用 `osascript -e 'display notification ...'`，参数必须经过安全字符串编码，不抢焦点。
6. [ ] 运行 `python3 -m unittest tests.test_notifications tests.test_runner_integration -v`。
7. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts tests/test_notifications.py tests/test_runner_integration.py
git commit -m "feat: complete fake automated relay loop"
```

## Phase Acceptance

1. [ ] `python3 -m unittest discover -s tests -v`
2. [ ] `bash .github/scripts/validate-release.sh`
3. [ ] `git diff --check`
4. [ ] 用两个临时仓库并发运行假任务，证明墙钟时间重叠且状态/日志互不串写。
5. [ ] 在单个临时仓库排入两个任务，证明第二任务保持 QUEUED。
6. [ ] 确认 Runner 仍未注册 launchd，且所有外部命令均来自 fake adapter。
