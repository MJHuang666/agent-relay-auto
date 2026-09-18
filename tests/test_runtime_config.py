import unittest

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

    def test_snapshot_is_immutable_after_defaults_change(self):
        runtime = config.RuntimeConfig.defaults()
        snapshot = runtime.snapshot()
        changed = config.RuntimeConfig(
            policy=config.AutomationPolicy(max_rework_rounds=1), cost=runtime.cost
        )
        self.assertEqual(snapshot["policy"]["max_rework_rounds"], 3)
        self.assertEqual(changed.policy.max_rework_rounds, 1)


if __name__ == "__main__":
    unittest.main()
