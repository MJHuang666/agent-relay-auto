import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.shared.agent_relay_runtime_loader import load_runtime_module


runnerctl = load_runtime_module("runnerctl", "../runnerctl.py")


class RunnerCtlTests(unittest.TestCase):
    def test_dry_run_actions_are_json_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runnerctl.command_status(Path(directory), dry_run=True)
            self.assertEqual(result["status"], "dry-run")
            self.assertIn("actions", result)

    def test_start_validates_configuration_registers_project_and_loads_service(self):
        policy = """mode: automatic
roles:
  planner:
    participant_id: planner-codex
    agent: codex
    model: gpt-test
    reasoning_effort: high
  implementer:
    participant_id: implementer-opencode
    agent: opencode
    model: openai/gpt-test
    variant: high
  reviewer:
    participant_id: reviewer-claude
    agent: claude-code
    model: claude-test
    effort: high
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/automation-policy.yaml").write_text(policy, encoding="utf-8")
            plist = root / "LaunchAgents/com.agent-relay-auto.runner.plist"
            plist.parent.mkdir(parents=True)
            plist.write_text("plist", encoding="utf-8")
            calls = []

            def run(command, **kwargs):
                calls.append(tuple(command))
                if "print" in command:
                    if any("kickstart" in call for call in calls):
                        return SimpleNamespace(returncode=0, stdout="state = running\nactive count = 1\n", stderr="")
                    return SimpleNamespace(returncode=113, stdout="", stderr="not loaded")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            controller = runnerctl.RunnerController(
                registry_path=root / "config/projects.json",
                plist_path=plist,
                uid=501,
                run_command=run,
            )
            result = controller.start(repo)
            self.assertEqual(result["status"], "started")
            self.assertTrue(any("bootstrap" in command for command in calls))
            self.assertTrue(any("kickstart" in command for command in calls))
            projects = (root / "config/projects.json").read_text(encoding="utf-8")
            self.assertIn(str(repo), projects)
            self.assertTrue(any(command[:2] == ("launchctl", "print") for command in calls))

    def test_start_rejects_incomplete_role_configuration_before_launchctl(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/automation-policy.yaml").write_text(
                "mode: automatic\nroles:\n  planner:\n    agent: codex\n",
                encoding="utf-8",
            )
            calls = []

            def run(command, **kwargs):
                calls.append(tuple(command))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            controller = runnerctl.RunnerController(
                registry_path=root / "config/projects.json",
                plist_path=root / "LaunchAgents/com.agent-relay-auto.runner.plist",
                uid=501,
                run_command=run,
            )
            with self.assertRaisesRegex(runnerctl.RunnerControlError, "planner"):
                controller.start(repo)
            self.assertEqual(calls, [])

    def test_status_marks_incomplete_project_blocked_even_when_service_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/automation-policy.yaml").write_text(
                "mode: automatic\nroles:\n  planner:\n    agent: codex\n",
                encoding="utf-8",
            )

            def run(command, **kwargs):
                return SimpleNamespace(returncode=0, stdout="state = running\nactive count = 1\n", stderr="")

            controller = runnerctl.RunnerController(root / "config/projects.json", root / "runner.plist", 501, run)
            result = controller.status(repo)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["service_status"], "running")

    def test_status_distinguishes_crash_loop_from_running_service(self):
        policy = """mode: automatic
roles:
  planner:
    participant_id: planner-codex
    agent: codex
    model: gpt-test
    reasoning_effort: high
  implementer:
    participant_id: implementer-codex
    agent: codex
    model: gpt-test
    reasoning_effort: medium
  reviewer:
    participant_id: reviewer-codex
    agent: codex
    model: gpt-test
    reasoning_effort: medium
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/automation-policy.yaml").write_text(policy, encoding="utf-8")

            def run(command, **kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stdout="state = spawn scheduled\nactive count = 0\nlast exit code = 1\n",
                    stderr="",
                )

            controller = runnerctl.RunnerController(
                registry_path=root / "config/projects.json",
                plist_path=root / "LaunchAgents/com.agent-relay-auto.runner.plist",
                uid=501,
                run_command=run,
            )
            result = controller.status(repo)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["last_exit_code"], 1)
            self.assertEqual(result["active_count"], 0)

    def test_start_rejects_service_that_crashes_after_kickstart(self):
        policy = """mode: automatic
roles:
  planner:
    participant_id: planner-codex
    agent: codex
    model: gpt-test
    reasoning_effort: high
  implementer:
    participant_id: implementer-codex
    agent: codex
    model: gpt-test
    reasoning_effort: medium
  reviewer:
    participant_id: reviewer-codex
    agent: codex
    model: gpt-test
    reasoning_effort: medium
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/automation-policy.yaml").write_text(policy, encoding="utf-8")
            plist = root / "LaunchAgents/com.agent-relay-auto.runner.plist"
            plist.parent.mkdir(parents=True)
            plist.write_text("plist", encoding="utf-8")
            kickstarted = False

            def run(command, **kwargs):
                nonlocal kickstarted
                if "kickstart" in command:
                    kickstarted = True
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if "print" in command and kickstarted:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="state = spawn scheduled\nactive count = 0\nlast exit code = 1\n",
                        stderr="",
                    )
                if "print" in command:
                    return SimpleNamespace(returncode=113, stdout="", stderr="not loaded")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            controller = runnerctl.RunnerController(root / "config/projects.json", plist, uid=501, run_command=run)
            with self.assertRaisesRegex(runnerctl.RunnerControlError, "failed after startup"):
                controller.start(repo)


if __name__ == "__main__":
    unittest.main()
