import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


configurator = load_runtime_module("configure_runtime", "../configure_runtime.py")


class ConfigureRuntimeTests(unittest.TestCase):
    def test_apply_writes_project_policy_and_local_runtime_without_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            result = configurator.RuntimeConfigurator(repo).apply(
                {
                    "language": "zh-CN",
                    "roles": {
                        "planner": {"agent": "codex", "model": "gpt-test", "reasoning": "high"},
                        "implementer": {"agent": "opencode", "model": "openai/test", "reasoning": "medium"},
                        "reviewer": {"agent": "claude-code", "model": "claude-test", "reasoning": "high"},
                    },
                    "allow_same_role_fallback": False,
                    "cost_mode": "balanced",
                    "runner_confirmed": False,
                }
            )
            self.assertEqual(result["mode"], "manual")
            self.assertTrue((repo / "docs/agent/automation-policy.yaml").is_file())
            self.assertTrue((repo / ".agent-relay-auto/local.yaml").is_file())
            self.assertNotIn("token", (repo / "docs/agent/automation-policy.yaml").read_text().lower())

    def test_existing_configuration_is_reported_for_confirm_or_modify(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs/agent").mkdir(parents=True)
            (repo / "docs/agent/automation-policy.yaml").write_text("language: en-US\n", encoding="utf-8")
            summary = configurator.RuntimeConfigurator(repo).inspect_existing()
            self.assertTrue(summary["exists"])
            self.assertIn("roles", summary)


if __name__ == "__main__":
    unittest.main()
