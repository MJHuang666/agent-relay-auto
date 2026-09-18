import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


registry_module = load_runtime_module("registry")


class ProjectRegistryTests(unittest.TestCase):
    def test_register_is_idempotent_and_persists_normalized_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            registry = registry_module.ProjectRegistry(root / "projects.json")
            registry.register(project)
            registry.register(project / ".")
            self.assertEqual(registry.enabled_projects(), (project.resolve(),))

    def test_unregister_disables_only_requested_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one"
            second = root / "two"
            first.mkdir()
            second.mkdir()
            registry = registry_module.ProjectRegistry(root / "projects.json")
            registry.register(first)
            registry.register(second)
            registry.unregister(first)
            self.assertEqual(registry.enabled_projects(), (second.resolve(),))


if __name__ == "__main__":
    unittest.main()
