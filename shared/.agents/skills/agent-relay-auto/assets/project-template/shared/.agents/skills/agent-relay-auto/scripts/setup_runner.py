#!/usr/bin/env python3
"""Install a versioned Agent Relay Auto Runner copy and launchd plist."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as platform_module
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallPaths:
    data_root: Path
    config_root: Path
    launch_agents: Path


class RunnerInstaller:
    def __init__(self, source_skill: Path, version: str, paths: InstallPaths, platform: str | None = None):
        self.source_skill = Path(source_skill).resolve()
        self.version = version
        self.paths = paths
        self.platform = platform or platform_module.system()

    @property
    def version_path(self) -> Path:
        return self.paths.data_root / "versions" / self.version

    @property
    def current_path(self) -> Path:
        return self.paths.data_root / "current"

    def _manifest(self, root: Path) -> dict[str, str]:
        result = {}
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def _plist(self) -> str:
        runner = self.current_path / "scripts/agent_relay_runner.py"
        log_root = self.paths.launch_agents.parent / "Logs" / "AgentRelay"
        registry = self.paths.config_root / "projects.json"
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.agent-relay-auto.runner</string>
<key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>{runner}</string><string>--registry</string><string>{registry}</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{log_root / 'runner.log'}</string>
<key>StandardErrorPath</key><string>{log_root / 'runner.error.log'}</string>
</dict></plist>
'''

    def install(self, dry_run: bool = False) -> dict[str, object]:
        actions = [
            f"copy {self.source_skill} -> {self.version_path}",
            f"switch {self.current_path} -> {self.version_path}",
            f"write {self.paths.launch_agents / 'com.agent-relay-auto.runner.plist'}",
        ]
        if dry_run:
            return {"status": "dry-run", "actions": actions}
        if self.platform != "Darwin":
            raise InstallError("launchd installation is supported only on macOS")
        if not self.source_skill.is_dir():
            raise InstallError(f"skill source is missing: {self.source_skill}")
        self.version_path.parent.mkdir(parents=True, exist_ok=True)
        if self.version_path.exists():
            shutil.rmtree(self.version_path)
        shutil.copytree(self.source_skill, self.version_path)
        manifest = self._manifest(self.version_path)
        (self.version_path / "MANIFEST.sha256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.paths.data_root.mkdir(parents=True, exist_ok=True)
        if self.current_path.is_symlink() or self.current_path.exists():
            self.current_path.unlink()
        self.current_path.symlink_to(self.version_path)
        self.paths.launch_agents.mkdir(parents=True, exist_ok=True)
        (self.paths.launch_agents.parent / "Logs" / "AgentRelay").mkdir(parents=True, exist_ok=True)
        (self.paths.launch_agents / "com.agent-relay-auto.runner.plist").write_text(self._plist(), encoding="utf-8")
        return {"status": "installed", "version": self.version, "manifest_entries": len(manifest)}

    def uninstall(self, keep_config: bool = True, dry_run: bool = False) -> dict[str, object]:
        actions = [f"remove {self.paths.launch_agents / 'com.agent-relay-auto.runner.plist'}", f"remove {self.paths.data_root}"]
        if not keep_config:
            actions.append(f"remove {self.paths.config_root}")
        if dry_run:
            return {"status": "dry-run", "actions": actions}
        plist = self.paths.launch_agents / "com.agent-relay-auto.runner.plist"
        if plist.exists():
            plist.unlink()
        if self.paths.data_root.exists():
            shutil.rmtree(self.paths.data_root)
        if not keep_config and self.paths.config_root.exists():
            shutil.rmtree(self.paths.config_root)
        return {"status": "uninstalled", "kept_config": keep_config}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "upgrade", "uninstall"))
    parser.add_argument("--source-skill", default=".")
    parser.add_argument("--version", default="dev")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-config", action="store_true")
    args = parser.parse_args(argv)
    home = Path.home()
    paths = InstallPaths(home / ".local/share/agent-relay-auto", home / ".config/agent-relay-auto", home / "Library/LaunchAgents")
    installer = RunnerInstaller(Path(args.source_skill), args.version, paths)
    result = installer.uninstall(args.keep_config, args.dry_run) if args.action == "uninstall" else installer.install(args.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
