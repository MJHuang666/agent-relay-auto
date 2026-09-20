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
from html import escape
from dataclasses import dataclass
from pathlib import Path


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallPaths:
    data_root: Path
    config_root: Path
    launch_agents: Path


@dataclass(frozen=True)
class UpgradePreflight:
    status: str
    repo: str
    task_id: str | None = None
    run_id: str | None = None
    role: str | None = None


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
        home = Path.home()
        codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
        discovered_codex = shutil.which("codex")
        path_entries = [
            str(Path(discovered_codex).resolve().parent) if discovered_codex else "",
            str(home / ".local/node/node-v22.14.0-darwin-arm64/bin"),
            "/Applications/ChatGPT.app/Contents/Resources",
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
        path_entries = [entry for entry in path_entries if entry]
        for entry in os.environ.get("PATH", "").split(os.pathsep):
            if entry and entry not in path_entries:
                path_entries.append(entry)
        runner_path = os.pathsep.join(path_entries)
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.agent-relay-auto.runner</string>
<key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>{runner}</string><string>--registry</string><string>{registry}</string></array>
<key>EnvironmentVariables</key><dict>
<key>HOME</key><string>{escape(str(home))}</string>
<key>CODEX_HOME</key><string>{escape(str(codex_home))}</string>
<key>PATH</key><string>{escape(runner_path)}</string>
</dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{log_root / 'runner.log'}</string>
<key>StandardErrorPath</key><string>{log_root / 'runner.error.log'}</string>
</dict></plist>
'''

    @staticmethod
    def _parse_scalar_state(path: Path) -> dict[str, str | None]:
        values: dict[str, str | None] = {}
        if not path.is_file():
            return values
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.startswith(" ") or ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            value = value.strip()
            values[key] = None if value in {"", "null", "~"} else value.strip("\"'")
        return values

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, ValueError):
            return False
        except PermissionError:
            return True
        return True

    def preflight(self, repo: Path) -> UpgradePreflight:
        repo = Path(repo).resolve()
        project = self._parse_scalar_state(repo / "docs/agent/PROJECT_STATUS.md")
        task_id = project.get("active_task")
        if not task_id:
            return UpgradePreflight("safe_to_upgrade", str(repo))
        state = self._parse_scalar_state(repo / "docs/agent/tasks" / task_id / "STATE.md")
        run_id = state.get("run_id")
        role = state.get("current_role")
        if not run_id or state.get("run_status") not in {"starting", "running"}:
            return UpgradePreflight("safe_to_upgrade", str(repo), task_id, role=role)
        process_path = repo / ".agent-relay-auto/runs" / task_id / run_id / "process.json"
        if process_path.is_file():
            try:
                process = json.loads(process_path.read_text(encoding="utf-8"))
                if process.get("run_id") == run_id and self._pid_is_alive(int(process["worker_pid"])):
                    return UpgradePreflight("wait_for_active_run", str(repo), task_id, run_id, role)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass
        return UpgradePreflight("repair_required", str(repo), task_id, run_id, role)

    def _registered_preflights(self) -> tuple[UpgradePreflight, ...]:
        registry = self.paths.config_root / "projects.json"
        if not registry.is_file():
            return ()
        payload = json.loads(registry.read_text(encoding="utf-8"))
        return tuple(
            self.preflight(Path(item["repo"]))
            for item in payload
            if item.get("enabled") is True and item.get("repo")
        )

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
        blocked = [item for item in self._registered_preflights() if item.status != "safe_to_upgrade"]
        if blocked:
            summary = ", ".join(f"{item.repo}: {item.status}" for item in blocked)
            raise InstallError(f"Runner upgrade preflight refused installation: {summary}")
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
