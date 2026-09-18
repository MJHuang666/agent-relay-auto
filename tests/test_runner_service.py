import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


base = load_runtime_module("runner_service_base", "adapters/base.py")
factory = load_runtime_module("runner_service_factory", "adapters/factory.py")
registry_module = load_runtime_module("runner_service_registry", "registry.py")
runner_entry = load_runtime_module("runner_service_entry", "../agent_relay_runner.py")


PROJECT = """# Project Status

```yaml
project: Demo
active_task: null
tasks:
  active: []
  queued: []
  blocked: []
  completed: []
```
"""


POLICY = """language: zh-CN
mode: automatic
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


class RunnerServiceTests(unittest.TestCase):
    def make_repo(self, directory: str, policy: str = POLICY) -> Path:
        repo = Path(directory) / "repo"
        (repo / "docs/agent").mkdir(parents=True)
        (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
        (repo / "docs/agent/automation-policy.yaml").write_text(policy, encoding="utf-8")
        return repo

    def test_factory_routes_each_role_with_configured_model_and_reasoning(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            router = factory.create_adapter_factory()(repo)
            planner = base.LaunchRequest(repo, "TASK-001", "planner", "planner-codex", "ignored", None, "run-1", 1)
            implementer = base.LaunchRequest(repo, "TASK-001", "implementer", "implementer-opencode", "ignored", None, "run-2", 1)
            reviewer = base.LaunchRequest(repo, "TASK-001", "reviewer", "reviewer-claude", "ignored", None, "run-3", 1)

            planner_command = router.build_command(planner)
            implementer_command = router.build_command(implementer)
            reviewer_command = router.build_command(reviewer)

            self.assertIn("gpt-test", planner_command)
            self.assertIn('model_reasoning_effort="high"', planner_command)
            self.assertIn("openai/gpt-test", implementer_command)
            self.assertIn("--variant", implementer_command)
            self.assertIn("claude-test", reviewer_command)
            self.assertIn("--effort", reviewer_command)

    def test_factory_rejects_missing_unknown_and_mismatched_role_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "missing"
            with self.assertRaisesRegex(factory.AdapterConfigurationError, "automation-policy.yaml"):
                factory.create_adapter_factory()(repo)

            repo = self.make_repo(directory, POLICY.replace("agent: opencode", "agent: unknown-tool"))
            with self.assertRaisesRegex(factory.AdapterConfigurationError, "implementer.*unknown-tool"):
                factory.create_adapter_factory()(repo)

        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory, POLICY.replace("  reviewer:\n", "  missing-reviewer:\n"))
            with self.assertRaisesRegex(factory.AdapterConfigurationError, "reviewer"):
                factory.create_adapter_factory()(repo)

        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            router = factory.create_adapter_factory()(repo)
            request = base.LaunchRequest(repo, "TASK-001", "planner", "planner-other", "ignored", None, "run-1", 1)
            with self.assertRaisesRegex(factory.AdapterConfigurationError, "planner-other"):
                router.build_command(request)

    def test_once_entry_uses_real_factory_for_registered_idle_project(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            registry_path = Path(directory) / "projects.json"
            registry = registry_module.ProjectRegistry(registry_path)
            registry.register(repo)
            self.assertEqual(runner_entry.main(["--registry", str(registry_path), "--once"]), 0)

    def test_once_entry_returns_clear_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/PROJECT_STATUS.md").write_text(PROJECT, encoding="utf-8")
            registry_path = Path(directory) / "projects.json"
            registry_module.ProjectRegistry(registry_path).register(repo)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = runner_entry.main(["--registry", str(registry_path), "--once"])
            self.assertNotEqual(result, 0)
            self.assertIn(str(repo), stderr.getvalue())
            self.assertIn("automation-policy.yaml", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
