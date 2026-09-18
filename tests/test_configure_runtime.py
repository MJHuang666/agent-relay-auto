import tempfile
import unittest
import contextlib
import io
import json
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


configurator = load_runtime_module("configure_runtime", "../configure_runtime.py")


class DiscoverableAdapter:
    def capabilities(self):
        return type(
            "Capabilities",
            (),
            {"noninteractive": True, "model_discovery": True},
        )()

    def list_models(self):
        return (
            type("Model", (), {"model_id": "provider/model-a", "display_name": "Model A"})(),
            type("Model", (), {"model_id": "provider/model-b", "display_name": "Model B"})(),
        )


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

    def test_automatic_configuration_requires_explicit_role_runtime_values(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            with self.assertRaisesRegex(configurator.ConfigurationError, "planner.*participant_id"):
                configurator.RuntimeConfigurator(repo).apply(
                    {
                        "language": "zh-CN",
                        "roles": {
                            "planner": {"agent": "codex", "model": "default", "reasoning": "high"},
                            "implementer": {"agent": "opencode", "model": "openai/test", "reasoning": "high"},
                            "reviewer": {"agent": "claude-code", "model": "claude-test", "reasoning": "high"},
                        },
                        "runner_confirmed": True,
                    }
                )

    def test_automatic_configuration_writes_provider_specific_role_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            result = configurator.RuntimeConfigurator(repo).apply(
                {
                    "language": "zh-CN",
                    "roles": {
                        "planner": {
                            "participant_id": "planner-codex",
                            "agent": "codex",
                            "model": "gpt-test",
                            "reasoning": "high",
                        },
                        "implementer": {
                            "participant_id": "implementer-opencode",
                            "agent": "opencode",
                            "model": "openai/test",
                            "reasoning": "high",
                        },
                        "reviewer": {
                            "participant_id": "reviewer-claude",
                            "agent": "claude-code",
                            "model": "claude-test",
                            "reasoning": "high",
                        },
                    },
                    "runner_confirmed": True,
                }
            )
            self.assertEqual(result["mode"], "automatic")
            policy = (repo / "docs/agent/automation-policy.yaml").read_text(encoding="utf-8")
            self.assertIn("participant_id: planner-codex", policy)
            self.assertIn("reasoning_effort: high", policy)
            self.assertIn("variant: high", policy)
            self.assertIn("effort: high", policy)
            summary = configurator.RuntimeConfigurator(repo).inspect_existing()
            self.assertEqual(summary["roles"]["planner"]["model"], "gpt-test")
            self.assertEqual(summary["roles"]["implementer"]["participant_id"], "implementer-opencode")
            self.assertEqual(summary["mode"], "automatic")
            self.assertTrue(summary["ready_to_start"])

    def test_discover_options_returns_selectable_models_and_reasoning_key(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = configurator.RuntimeConfigurator(
                Path(directory), adapter_builders={"opencode": DiscoverableAdapter}
            )
            options = runtime.discover_options("opencode")
            self.assertTrue(options["automatic_supported"])
            self.assertEqual(options["reasoning_key"], "variant")
            self.assertEqual(options["models"][0]["id"], "provider/model-a")
            self.assertEqual(options["validation_status"], "verified")

    def test_discover_options_marks_tools_without_an_adapter_as_manual_only(self):
        with tempfile.TemporaryDirectory() as directory:
            options = configurator.RuntimeConfigurator(Path(directory), adapter_builders={}).discover_options("cursor")
            self.assertFalse(options["automatic_supported"])
            self.assertEqual(options["validation_status"], "manual-only")

    def test_cli_apply_accepts_inline_non_secret_answers_after_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            answers = {
                "language": "en-US",
                "roles": {
                    "planner": {"participant_id": "planner-codex", "agent": "codex", "model": "gpt-test", "reasoning": "high"},
                    "implementer": {"participant_id": "implementer-opencode", "agent": "opencode", "model": "openai/test", "reasoning": "high"},
                    "reviewer": {"participant_id": "reviewer-claude", "agent": "claude-code", "model": "claude-test", "reasoning": "high"},
                },
                "runner_confirmed": True,
            }
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = configurator.main(
                    ["apply", "--repo", directory, "--answers-json", json.dumps(answers)]
                )
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "automatic")


if __name__ == "__main__":
    unittest.main()
