# Agent Relay 自动闭环阶段 4：Skill、launchd 与发行 Implementation Plan

> **执行要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（当前会话）或 `superpowers:executing-plans`（独立会话），逐任务执行、验证和提交。

**Goal:** 把 Runner 以可确认、可升级、可卸载的 macOS launchd 服务随 Skill 分发，完成中英文初始化/管理体验、兼容迁移和可复现发行验证。

**Architecture:** Skill 目录是源码真源；安装器把带版本的只读运行时复制到 `~/.local/share/agent-relay/versions/<version>/`，用原子 current 指针切换。launchd 只引用稳定运行目录。项目内只提交策略与运行快照，本机和用户级配置分别留在忽略目录与 `~/.config/agent-relay/`。

**Tech Stack:** Python 3 标准库、macOS launchd/plist、Markdown、Bash release validation、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-09-19-agent-relay-automation-design.md`

**Global Constraints:** 安装 Skill 不自动常驻；首次初始化必须先说明影响并获得确认；不记录密钥；旧手动模式可降级；发布工作只生成本地包与校验，不自动 push/Release。

---

## Task 1: 稳定运行目录与 launchd 生命周期

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/setup_runner.py`
- Create: `shared/.agents/skills/agent-relay/scripts/runnerctl.py`
- Create: `shared/.agents/skills/agent-relay/assets/launchd/com.agent-relay.runner.plist.in`
- Create: `tests/test_runner_installer.py`
- Create: `tests/test_runnerctl.py`

**Interfaces:**

```text
setup_runner.py install --source-skill PATH --version VERSION [--dry-run]
setup_runner.py upgrade --source-skill PATH --version VERSION [--dry-run]
setup_runner.py uninstall [--keep-config] [--dry-run]

runnerctl.py status|start|stop|restart
runnerctl.py register-project --repo PATH
runnerctl.py unregister-project --repo PATH
runnerctl.py logs [--follow] [--project PATH] [--task ID]
runnerctl.py pause|interrupt|resume --repo PATH --task ID
```

**Steps:**

1. [ ] 写失败测试，所有 home/Library 路径通过显式参数注入临时目录；测试不得触碰真实 LaunchAgents。
2. [ ] 测试 install 复制到 `versions/<version>`、校验 manifest SHA-256、原子切换 current、生成 plist；upgrade 失败保留旧 current。
3. [ ] 测试 stop/start/restart 命令和 launchctl 退出码；uninstall 默认保留用户配置并删除服务/运行时，行为可恢复说明明确。
4. [ ] 实现 dry-run 输出 JSON action list；非 dry-run 前验证平台为 Darwin、源目录完整和目标不是仓库根目录。
5. [ ] plist 仅引用稳定 Python 入口、用户日志路径和最小环境；不内嵌 token 或项目列表。
6. [ ] 运行 `python3 -m unittest tests.test_runner_installer tests.test_runnerctl -v`。
7. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay/scripts shared/.agents/skills/agent-relay/assets/launchd tests/test_runner_installer.py tests/test_runnerctl.py
git commit -m "feat: add versioned runner installation and launchd controls"
```

## Task 2: 初始化向导、角色模型配置和项目注册

**Files:**
- Create: `shared/.agents/skills/agent-relay/scripts/configure_runtime.py`
- Create: `tests/test_configure_runtime.py`
- Create: `shared/docs/agent/automation-policy.yaml`
- Modify: all `PROJECT_STATUS.md`, `role-bindings.md`, `integrations.md`, `.gitignore` templates under `shared/` and `assets/project-template/`.

**Interfaces:**

```python
class RuntimeConfigurator:
    def inspect_existing(self, repo: Path) -> ConfigurationSummary: ...
    def discover_options(self, tool_id: str) -> ToolOptions: ...
    def apply(self, answers: ConfigurationAnswers) -> ConfigurationResult: ...
```

**Steps:**

1. [ ] 写失败测试覆盖语言先选、默认策略提示、三角色 Agent/model/reasoning、备用 Agent 默认关闭、成本档位 balanced、通知和 Runner 确认。
2. [ ] 已有配置测试必须完整显示三角色与问题，并只提供“确认并继续/修改”；CLI 缺失或配置损坏时禁止无条件确认。
3. [ ] 模型选项调用适配器动态发现；失败时允许输入稳定 ID，但写 `validation_status: pending`。
4. [ ] 项目策略写入可提交文件；CLI 路径/session/主机能力写 `.agent-relay/local.yaml`；共享运行 profile 写用户配置。任何 secret value 均拒绝写入。
5. [ ] 初始化把 `.agent-relay/` 加入 `.gitignore`，保存活动任务的 runtime snapshot，并注册项目；Runner 未获安装确认时保持 manual mode。
6. [ ] 运行 `python3 -m unittest tests.test_configure_runtime tests.test_agent_relay_contract -v`。
7. [ ] 提交：

```bash
git add shared tests/test_configure_runtime.py
git commit -m "feat: add automated relay initialization wizard"
```

## Task 3: 更新 Skill 协议、中英文命令和手动降级

**Files:**
- Modify: `shared/.agents/skills/agent-relay/SKILL.md`
- Modify: `shared/.agents/skills/agent-relay/references/initialization.md`
- Modify: `shared/.agents/skills/agent-relay/references/protocol.md`
- Modify: `shared/.agents/skills/agent-relay/references/state-helper.md`
- Create: `shared/.agents/skills/agent-relay/references/runner.md`
- Modify: corresponding Skill mirror files under `assets/project-template/shared/.agents/skills/agent-relay/`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/AGENT_RELAY_USAGE.md`
- Modify: `docs/AGENT_RELAY_USAGE.en-US.md`
- Modify: `docs/migration-v1.5.md`
- Test: `tests/test_agent_relay_contract.py`

**Steps:**

1. [ ] 先扩展契约测试，断言所有中英文 Runner 命令、WAITING_USER/BLOCKED/DONE 边界、manual fallback 和“DONE 不授权 merge/push/release/deploy”同时存在于 canonical 与镜像 Skill。
2. [ ] 运行 `python3 -m unittest tests.test_agent_relay_contract -v`，确认失败。
3. [ ] 更新 Skill：初始化或继续时检测 automation mode；自动模式只通过状态命令/runnerctl 操作，不直接伪造 transition；manual mode 保留原三角色接力。
4. [ ] 写清 Planner 是用户入口；后台 Planner/Implementer/Reviewer 都可由 CLI 启动；需要决策时进入 WAITING_USER 并通知，不抢焦点。
5. [ ] 添加全部中英文等价命令：Runner 状态、启动、停止、重启、升级、运行状态、查看/跟踪日志、暂停、中断、恢复。
6. [ ] 修正规格文件中重复的 `## 7` 标题和重复上下文优化条目，不改变已批准语义。
7. [ ] 运行契约测试和 `rg -n '\$project-role-workflow' README* docs/AGENT_RELAY_USAGE*`，公开文档不得恢复旧品牌命令。
8. [ ] 提交：

```bash
git add shared/.agents/skills/agent-relay README.md README.zh-CN.md docs tests/test_agent_relay_contract.py
git commit -m "docs: teach agent relay automated runner workflow"
```

## Task 4: 端到端验收、CI 与本地发行包

**Files:**
- Create: `tests/test_automated_relay_e2e.py`
- Modify: `tests/test_clone_recovery.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/scripts/validate-release.sh`
- Modify: `distribution/VERSION`
- Modify: `distribution/INSTALL.md`
- Modify: `distribution/INSTALL_PROMPT.md`
- Create: `docs/verification/automated-runner-v2.md`
- Create: `docs/migration-automation-v2.md`

**Steps:**

1. [ ] 编写隔离仓库 E2E：初始化→排队两个任务→fake CLI 完成第一任务→第二任务激活；覆盖返修、重规划、WAITING_USER、暂停恢复、成本硬停止和跨项目并发。
2. [ ] 扩展 clone recovery，证明提交的任务/队列/快照在新 clone 可恢复，而 `.agent-relay/runs` 与原生 session 不进入 Git。
3. [ ] CI 在 macOS 执行 unit/E2E/dry-run launchd；其他 runner 仅运行平台无关状态机与适配器 fixture 测试。
4. [ ] `validate-release.sh` 增加 canonical/mirror SHA 一致性、模板 schema、禁止 secret fixture、无占位符、版本一致性和 zip 清单校验。
5. [ ] 运行真实只读/隔离验证并记录每个适配器为 `verified`、`static-only` 或 `unavailable`；不得因缺少凭证写成成功。
6. [ ] 更新版本号为实施时确定的下一个语义版本；生成 `agent-relay-skill-pack-v<version>.zip` 和同名 `.sha256`，压缩包不得包含 `.git`、`.agent-relay`、日志或凭证。
7. [ ] 运行：

```bash
python3 -m unittest discover -s tests -v
bash .github/scripts/validate-release.sh
git diff --check
```

8. [ ] 解压发行包到临时目录，再运行包内 `setup_runner.py install --dry-run` 和模板初始化验证。
9. [ ] 提交但不推送：

```bash
git add .github distribution docs shared tests
git commit -m "release: package automated agent relay runner"
```

## Phase Acceptance

1. [ ] 全部测试和发行检查通过，保存命令与数量到验证文档。
2. [ ] launchd dry-run 与临时 HOME 测试通过；任何真实服务安装只在用户明确确认后执行。
3. [ ] Skill canonical 与模板镜像逐文件一致。
4. [ ] zh-CN/en-US 初始化、继续、日志、暂停、中断、恢复用法均可独立照文档执行。
5. [ ] 老项目无 Runner 时仍可 manual mode 继续；迁移不会静默改写活动任务。
6. [ ] `git status --short --branch` 只显示预期本地提交；不 push、不创建 GitHub Release。
