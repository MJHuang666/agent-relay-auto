import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


config = load_runtime_module("config")


class RuntimeConfigTests(unittest.TestCase):
    def test_balanced_defaults_match_approved_policy(self):
        runtime = config.RuntimeConfig.defaults()
        self.assertEqual(runtime.policy.max_rework_rounds, 3)
        self.assertEqual(runtime.policy.max_auto_replans, 1)
        self.assertEqual(runtime.policy.max_agent_retries, 1)
        self.assertFalse(runtime.policy.allow_same_role_fallback)
        self.assertEqual(runtime.cost.warn_after_agent_runs, 8)
        self.assertEqual(runtime.cost.stop_after_agent_runs, 12)

    def test_negative_limits_are_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.AutomationPolicy(max_rework_rounds=-1)

    def test_runtime_limit_defaults_are_bounded(self):
        limits = config.RuntimeLimits()
        self.assertEqual(limits.agent_timeout_minutes, 30)
        self.assertEqual(limits.heartbeat_interval_seconds, 10)
        self.assertEqual(limits.heartbeat_stale_seconds, 45)
        self.assertEqual(limits.interrupt_grace_seconds, 30)

    def test_invalid_runtime_limits_are_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.RuntimeLimits(agent_timeout_minutes=0)

    def test_snapshot_is_immutable_after_defaults_change(self):
        runtime = config.RuntimeConfig.defaults()
        snapshot = runtime.snapshot()
        changed = config.RuntimeConfig(
            policy=config.AutomationPolicy(max_rework_rounds=1), cost=runtime.cost
        )
        self.assertEqual(snapshot["policy"]["max_rework_rounds"], 3)
        self.assertEqual(changed.policy.max_rework_rounds, 1)

    def test_project_policy_overrides_retry_and_runtime_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            policy = repo / "docs/agent/automation-policy.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                "automation:\n"
                "  max_agent_retries: 2\n"
                "runtime:\n"
                "  agent_timeout_minutes: 5\n"
                "  heartbeat_interval_seconds: 2\n"
                "  heartbeat_stale_seconds: 8\n"
                "  interrupt_grace_seconds: 3\n",
                encoding="utf-8",
            )
            runtime = config.load_runtime_config(repo)
            self.assertEqual(runtime.policy.max_agent_retries, 2)
            self.assertEqual(runtime.limits.agent_timeout_minutes, 5)


if __name__ == "__main__":
    unittest.main()
