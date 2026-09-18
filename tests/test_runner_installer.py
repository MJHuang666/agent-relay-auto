import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


installer = load_runtime_module("setup_runner", "../setup_runner.py")


class RunnerInstallerTests(unittest.TestCase):
    def test_install_copies_version_and_writes_stable_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "skill"
            (source / "scripts").mkdir(parents=True)
            (source / "scripts/agent_relay_runner.py").write_text("runner\n", encoding="utf-8")
            paths = installer.InstallPaths(root / "data", root / "config", root / "launch-agents")
            service = installer.RunnerInstaller(source, "2.0.0", paths, platform="Darwin")
            result = service.install(dry_run=False)
            self.assertEqual(result["status"], "installed")
            self.assertTrue((root / "data/versions/2.0.0/scripts/agent_relay_runner.py").is_file())
            self.assertTrue((root / "launch-agents/com.agent-relay-auto.runner.plist").is_file())
            self.assertTrue((root / "data/current").is_symlink())

    def test_non_darwin_install_is_rejected_but_dry_run_describes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "skill"
            source.mkdir()
            paths = installer.InstallPaths(root / "data", root / "config", root / "launch-agents")
            service = installer.RunnerInstaller(source, "2.0.0", paths, platform="Linux")
            self.assertEqual(service.install(dry_run=True)["status"], "dry-run")
            with self.assertRaises(installer.InstallError):
                service.install(dry_run=False)


if __name__ == "__main__":
    unittest.main()
