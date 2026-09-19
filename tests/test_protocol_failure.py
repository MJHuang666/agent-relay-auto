import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.shared.agent_relay_runtime_loader import load_runtime_module


config = load_runtime_module("config")
markdown = load_runtime_module("markdown_state")
state_store = load_runtime_module("state_store")
supervisor_module = load_runtime_module("supervisor")


PROJECT = """# Project Status

```yaml
project: Demo
active_task: TASK-001
tasks:
  active: ["TASK-001"]
  queued: []
  blocked: []
  completed: []
```
"""

STATE = """# Task State

```yaml
task: TASK-001
title: Demo
status: IMPLEMENTING
revision: 1
stage_round: 1
run_id: null
run_status: idle
run_attempt: 0
rework_round: 0
auto_replan_count: 0
agent_failure_count: 0
blocked_reason: null
unblock_condition: null
current_role: implementer
current_participant: impl-a
writer_session: null
execution: idle
```
"""


class ExitOnlyAdapter:
    def __init__(self, sleep=0.0):
        self.sleep = sleep

    def capabilities(self):
        return SimpleNamespace(noninteractive=True)

    def build_command(self, request, context):
        fixture = Path(__file__).resolve().parent / "fixtures/fake_agent_cli.py"
        return (sys.executable, str(fixture), "--sleep", str(self.sleep))


class ProtocolFailureTests(unittest.TestCase):
    def make_repo(self, directory):
        repo = Path(directory)
        (repo / ".git").mkdir()
        task = repo / "docs/agent/tasks/TASK-001"
        task.mkdir(parents=True)
        (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
        (task / "STATE.md").write_text(STATE, encoding="utf-8")
        return repo

    def wait_for_nonrunning(self, supervisor, timeout=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            decision = supervisor.tick()
            if decision.action not in {"already_running", "started"}:
                return decision
            time.sleep(0.01)
        self.fail("background run did not finish")

    def read_state(self, repo):
        text = (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text(encoding="utf-8")
        return markdown.parse_fenced_yaml(text)

    def test_exit_zero_without_transition_retries_once_then_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            supervisor = supervisor_module.ProjectSupervisor(repo, ExitOnlyAdapter())

            self.assertEqual(supervisor.tick().action, "started")
            first = self.wait_for_nonrunning(supervisor)
            self.assertEqual(first.action, "retry_scheduled")
            self.assertEqual(self.read_state(repo)["agent_failure_count"], 1)

            self.assertEqual(supervisor.tick().action, "started")
            second = self.wait_for_nonrunning(supervisor)
            self.assertEqual(second.action, "blocked")
            state = self.read_state(repo)
            self.assertIn("protocol_failure: no_handoff", state["blocked_reason"])
            self.assertEqual(state["agent_failure_count"], 2)
            self.assertEqual(len(list((repo / ".agent-relay-auto/runs/TASK-001").iterdir())), 2)

    def test_legal_transition_then_exit_finalizes_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            store = state_store.StateStore(repo)
            claim = store.claim(state_store.ClaimKey("TASK-001", 1, "impl-a", 1), "run-1")
            path = repo / "docs/agent/tasks/TASK-001/STATE.md"
            text = path.read_text(encoding="utf-8")
            text = markdown.set_yaml_value(text, ("status",), "REVIEWING")
            text = markdown.set_yaml_value(text, ("revision",), claim.output_revision + 1)
            markdown.atomic_write_text(path, text)

            first = store.finish_run("TASK-001", "run-1", 0, "IMPLEMENTING", "exit")
            second = store.finish_run("TASK-001", "run-1", 0, "IMPLEMENTING", "exit")
            self.assertEqual(first.action, "completed")
            self.assertTrue(second.idempotent_replay)

    def test_timeout_interrupts_and_schedules_bounded_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            runtime = config.RuntimeConfig(
                config.AutomationPolicy(max_agent_retries=1),
                config.CostControl(),
                config.RuntimeLimits(
                    agent_timeout_minutes=0.001,
                    heartbeat_interval_seconds=0.01,
                    heartbeat_stale_seconds=0.2,
                    interrupt_grace_seconds=0.1,
                ),
            )
            supervisor = supervisor_module.ProjectSupervisor(repo, ExitOnlyAdapter(sleep=5), runtime=runtime)
            self.assertEqual(supervisor.tick().action, "started")
            decision = self.wait_for_nonrunning(supervisor)
            self.assertEqual(decision.action, "retry_scheduled")
            state = self.read_state(repo)
            self.assertIsNone(state["run_id"])
            self.assertIsNone(state["writer_session"])
            self.assertEqual(state["last_run_result"], "timeout")


if __name__ == "__main__":
    unittest.main()
