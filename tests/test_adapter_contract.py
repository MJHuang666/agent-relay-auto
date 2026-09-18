import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


base = load_runtime_module("base", "adapters/base.py")


class AdapterContractTests(unittest.TestCase):
    def test_capability_contract_requires_noninteractive_flag(self):
        capabilities = base.AdapterCapabilities(True, True, False, True, True)
        self.assertTrue(capabilities.noninteractive)

    def test_launch_request_keeps_repo_and_claim_identity(self):
        request = base.LaunchRequest(Path("/tmp/repo"), "TASK-001", "planner", "p1", "model", None, "run-1", 4)
        self.assertEqual(request.expected_revision, 4)
        self.assertEqual(request.task_id, "TASK-001")


if __name__ == "__main__":
    unittest.main()
