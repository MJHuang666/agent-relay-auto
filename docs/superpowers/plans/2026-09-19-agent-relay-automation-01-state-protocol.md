# Agent Relay 自动闭环阶段 1：状态协议与任务队列 Implementation Plan

> **执行要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（当前会话）或 `superpowers:executing-plans`（独立会话），逐任务执行、验证和提交。

**Goal:** 在不破坏 v1.5 手动接力的前提下，把 Markdown 权威状态扩展为可供 Runner 安全驱动的任务集合、自动状态机、CAS、运行快照和用户决策协议。

**Architecture:** 保留 `STATE.md` 与 `PROJECT_STATUS.md` 为权威事实源；把通用 Markdown/YAML、锁与原子写入能力从旧脚本抽到标准库运行时包。所有状态改变只能经 `StateStore` 在短时锁内完成，使用 `expected_revision` 做 CAS，并返回不可重复执行的 `TransitionResult`。

**Tech Stack:** Python 3 标准库、`unittest`、Markdown、fenced YAML、JSON。

**Spec:** `docs/superpowers/specs/2026-09-19-agent-relay-automation-design.md`

**Global Constraints:** 不引入 PyYAML；不自动 merge/push/release/deploy；不删除旧 `workflow_state.py` CLI；第一版每项目仅一个活动任务、每任务仅一个角色进程；所有模板同时维护 shared、zh-CN、en-US 三份。

---

## Task 1: 建立运行时包并抽取无损 Markdown 状态读写

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/__init__.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/models.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/markdown_state.py`
- Modify: `shared/.agents/skills/agent-relay/scripts/workflow_state.py`
- Test: `tests/test_markdown_state.py`
- Test: `tests/test_workflow_state.py`

**Interfaces:**

```python
class StateFormatError(ValueError): ...

def parse_fenced_yaml(text: str) -> dict[str, object]: ...
def set_yaml_value(text: str, path: tuple[str, ...], value: object) -> str: ...
def atomic_write_text(path: Path, content: str) -> None: ...
```

`parse_fenced_yaml` 必须支持标量、一层映射和 JSON 风格内联数组，例如 `active: ["TASK-001"]`；不得重排或覆盖 YAML 围栏外的人类说明。

**Steps:**

1. [ ] 写失败测试，覆盖字符串、整数、布尔、null、一层映射、内联数组和围栏外文本保持不变。

```python
def test_round_trip_preserves_markdown_and_reads_inline_task_lists(self):
    text = '# State\n\n```yaml\ntasks:\n  active: ["TASK-001"]\n  queued: ["TASK-002"]\n```\n\nHuman notes.\n'
    data = parse_fenced_yaml(text)
    self.assertEqual(data["tasks"]["active"], ["TASK-001"])
    updated = set_yaml_value(text, ("tasks", "queued"), ["TASK-003"])
    self.assertTrue(updated.endswith("Human notes.\n"))
```

2. [ ] 运行 `python3 -m unittest tests.test_markdown_state -v`，确认因模块不存在而失败。
3. [ ] 实现不可变值模型、简单 fenced-YAML 解析器和原子替换；布尔值只接受 `true`/`false`，数组通过 `json.loads` 解析。
4. [ ] 将 `workflow_state.py` 的解析、引用、原子写函数改为导入新模块，并保留原函数名的兼容包装。
5. [ ] 运行 `python3 -m unittest tests.test_markdown_state tests.test_workflow_state -v`，预期全部通过。
6. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts tests/test_markdown_state.py tests/test_workflow_state.py
git commit -m "refactor: extract relay markdown state primitives"
```

## Task 2: 定义任务集合、运行快照与兼容镜像 schema

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/schema.py`
- Create: `tests/test_automation_schema.py`
- Modify: `shared/docs/agent/PROJECT_STATUS.md`
- Modify: `shared/docs/agent/tasks/_template/STATE.md`
- Modify: `shared/.agents/skills/agent-relay/assets/project-template/shared/docs/agent/PROJECT_STATUS.md`
- Modify: `shared/.agents/skills/agent-relay/assets/project-template/shared/docs/agent/tasks/_template/STATE.md`
- Modify: `shared/.agents/skills/agent-relay/assets/project-template/locales/zh-CN/docs/agent/PROJECT_STATUS.md`
- Modify: `shared/.agents/skills/agent-relay/assets/project-template/locales/zh-CN/docs/agent/tasks/_template/STATE.md`
- Modify: `shared/.agents/skills/agent-relay/assets/project-template/locales/en-US/docs/agent/PROJECT_STATUS.md`
- Modify: `shared/.agents/skills/agent-relay/assets/project-template/locales/en-US/docs/agent/tasks/_template/STATE.md`

**Interfaces:**

```python
@dataclass(frozen=True)
class ProjectQueue:
    active: tuple[str, ...]
    queued: tuple[str, ...]
    blocked: tuple[str, ...]
    completed: tuple[str, ...]

def validate_project_state(data: Mapping[str, object]) -> ProjectQueue: ...
def validate_task_state(data: Mapping[str, object]) -> None: ...
def validate_active_task_mirror(data: Mapping[str, object]) -> None: ...
```

权威字段为 `tasks.active`；`active_task` 只能镜像 `tasks.active[0]` 或为 null。任务状态增加 `run_id`、`run_status`、`run_attempt`、`stage_round`、返修/重规划/失败/成本计数、`runtime_snapshot_ref`、`suspended_status`、`resume_role`、`question_id` 与 `question_ref`。

**Steps:**

1. [ ] 写失败测试：重复任务 ID、多个活动任务、镜像不一致、终态任务仍在 active、缺少运行快照引用均报明确错误。
2. [ ] 运行 `python3 -m unittest tests.test_automation_schema -v`，确认失败。
3. [ ] 实现 dataclass 和验证器；错误必须包含字段路径，例如 `tasks.active`。
4. [ ] 更新三套模板，默认 `tasks.active: []`、`tasks.queued: []`、`tasks.blocked: []`、`tasks.completed: []`，保留 `active_task: null`。
5. [ ] 在任务模板中加入自动运行字段，但默认 `run_id: null`、`run_status: idle`，避免初始化即伪造运行。
6. [ ] 运行 `python3 -m unittest tests.test_automation_schema tests.test_agent_relay_contract -v`，预期通过。
7. [ ] 提交：

```bash
git add shared/docs shared/.agents/skills/agent-relay/assets/project-template tests/test_automation_schema.py shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/schema.py
git commit -m "feat: define automated relay state schema"
```

## Task 3: 实现合法转换、CAS、幂等领取和任务队列

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/state_store.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/transitions.py`
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/queue.py`
- Create: `tests/test_state_store.py`
- Create: `tests/test_automation_transitions.py`
- Create: `tests/test_project_queue.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ClaimKey:
    task_id: str
    expected_revision: int
    participant_id: str
    stage_round: int

@dataclass(frozen=True)
class TransitionResult:
    task_id: str
    old_status: str
    new_status: str
    input_revision: int
    output_revision: int
    idempotent_replay: bool

class StateStore:
    def transition(self, task_id: str, expected_revision: int, event: str, payload: Mapping[str, object]) -> TransitionResult: ...
    def claim(self, key: ClaimKey, run_id: str) -> TransitionResult: ...

def activate_next_queued_task(repo: Path, expected_project_revision: int) -> str | None: ...
```

**Steps:**

1. [ ] 用表驱动失败测试覆盖规格中的每条合法路径及非法跨越，包括禁止 `REVIEWING → DONE`。
2. [ ] 写两个并发进程使用同一 `ClaimKey` 的测试，要求只有一个创建新 `run_id`，另一个返回 `idempotent_replay=True`。
3. [ ] 写队列测试，证明 `WAITING_USER`/`BLOCKED` 占用 active slot，只有 DONE/CANCELLED/明确搁置后才激活 FIFO 下一任务。
4. [ ] 运行 `python3 -m unittest tests.test_state_store tests.test_automation_transitions tests.test_project_queue -v`，确认失败。
5. [ ] 实现允许转换表；所有写入在 `state_lock` 内重新读取并校验 revision；项目队列更新与任务更新写入同一事务清单，任一写入失败则不提交另一半。
6. [ ] 为事务采用先写临时文件、fsync、再按固定顺序 replace 的机制，并留下 `transaction_id` 供启动恢复核对。
7. [ ] 运行上述测试 20 次竞争循环，命令：

```bash
for i in $(seq 1 20); do python3 -m unittest tests.test_state_store tests.test_automation_transitions tests.test_project_queue || exit 1; done
```

8. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts/agent_relay_runtime tests/test_state_store.py tests/test_automation_transitions.py tests/test_project_queue.py
git commit -m "feat: add relay state machine and serial task queue"
```

## Task 4: 用户决策、限制计数和最终报告门禁

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/agent_relay_runtime/commands.py`
- Create: `shared/.agents/skills/agent-relay/scripts/relay_state.py`
- Create: `tests/test_relay_state_cli.py`
- Modify: `shared/docs/agent/tasks/_template/decisions.md`
- Modify: `shared/docs/agent/tasks/_template/review.md`
- Create: `shared/docs/agent/tasks/_template/final-report.md`
- Apply same template changes under all three `assets/project-template` variants.

**Interfaces:**

```text
relay_state.py status --repo PATH
relay_state.py wait-user --task ID --expected-revision N --question-file PATH --resume-role ROLE
relay_state.py answer --task ID --expected-revision N --question-id ID --answer-file PATH
relay_state.py verdict --task ID --expected-revision N --verdict PASS|CHANGES_REQUESTED|REPLAN_REQUIRED --evidence PATH
relay_state.py report-done --task ID --expected-revision N --report PATH
relay_state.py cancel --task ID --expected-revision N --authorization TEXT
```

**Steps:**

1. [ ] 写失败测试，确保 question ID/revision 不匹配不恢复、无 review 证据不能 PASS、无 final report 不能 DONE、超过返修/重规划/运行成本上限进入 BLOCKED。
2. [ ] 运行 `python3 -m unittest tests.test_relay_state_cli -v`，确认失败。
3. [ ] 实现 CLI；所有成功结果输出一行 JSON，业务冲突退出码 3，格式错误退出码 2。
4. [ ] WAITING_USER 创建不可覆盖 `questions/Q-xxx.md`；回答写入 `decisions.md` 的新记录并恢复 `suspended_status`，不得重跑已完成阶段。
5. [ ] `PASS` 只允许进入 REPORTING；`report-done` 校验最终报告包含目标、交付、测试、Reviewer 证据、限制、使用方式和未执行高风险动作后进入 DONE。
6. [ ] 运行 `python3 -m unittest tests.test_relay_state_cli tests.test_automation_transitions -v`，预期通过。
7. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts shared/docs/agent/tasks shared/.agents/skills/agent-relay/assets/project-template tests/test_relay_state_cli.py
git commit -m "feat: add automated relay transition commands"
```

## Phase Acceptance

1. [ ] 运行 `python3 -m unittest discover -s tests -v`。
2. [ ] 运行 `bash .github/scripts/validate-release.sh`。
3. [ ] 运行 `git diff --check`。
4. [ ] 验证旧命令：`python3 shared/.agents/skills/agent-relay/scripts/workflow_state.py --help`。
5. [ ] 从 zh-CN 与 en-US 模板各初始化一个临时目录，确认 schema 验证均通过。
6. [ ] 确认未启动 Runner、未安装 launchd、未推送远端。
