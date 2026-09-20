import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


installer = load_runtime_module("setup_runner_migration", "../setup_runner.py")


PROJECT = "# Project\n\n```yaml\nactive_task: TASK-001\n```\n"


class V17MigrationTests(unittest.TestCase):
    def make_installer(self, root):
        source = root / "skill"
        source.mkdir()
        paths = installer.InstallPaths(root / "data", root / "config", root / "launch")
        return installer.RunnerInstaller(source, "1.7.0", paths, platform="Darwin")

    def write_state(self, root, run_id, run_status="running", role="planner"):
        repo = root / "repo"
        task = repo / "docs/agent/tasks/TASK-001"
        task.mkdir(parents=True)
        (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT)
        (task / "STATE.md").write_text(
            f"# State\n\n```yaml\nstatus: PLANNING\ncurrent_role: {role}\n"
            f"run_id: {run_id}\nrun_status: {run_status}\n```\n"
        )
        return repo

    def test_live_legacy_background_planner_blocks_upgrade_without_killing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.make_installer(root)
            repo = self.write_state(root, "run-live")
            run_dir = repo / ".agent-relay-auto/runs/TASK-001/run-live"
            run_dir.mkdir(parents=True)
            (run_dir / "process.json").write_text(json.dumps({"run_id": "run-live", "worker_pid": os.getpid()}))
            result = service.preflight(repo)
            self.assertEqual(result.status, "wait_for_active_run")
            self.assertEqual(result.role, "planner")

    def test_stopped_legacy_planner_lease_requires_explicit_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.make_installer(root)
            repo = self.write_state(root, "run-stale")
            self.assertEqual(service.preflight(repo).status, "repair_required")

    def test_live_agent_blocks_upgrade_when_worker_pid_is_gone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.make_installer(root)
            repo = self.write_state(root, "run-agent-live")
            run_dir = repo / ".agent-relay-auto/runs/TASK-001/run-agent-live"
            run_dir.mkdir(parents=True)
            (run_dir / "process.json").write_text(json.dumps({
                "run_id": "run-agent-live", "worker_pid": 99999999,
                "agent_pid": os.getpid(), "process_group_id": os.getpid(),
            }))
            self.assertEqual(service.preflight(repo).status, "wait_for_active_run")

    def test_idle_project_is_safe_to_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.make_installer(root)
            repo = self.write_state(root, "null", "idle")
            self.assertEqual(service.preflight(repo).status, "safe_to_upgrade")


if __name__ == "__main__":
    unittest.main()
