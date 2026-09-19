#!/usr/bin/env python3
"""Safe management command surface for the Runner service."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from agent_relay_runtime.adapters.factory import AdapterConfigurationError, load_agent_policy  # noqa: E402
from agent_relay_runtime.registry import ProjectRegistry  # noqa: E402


LABEL = "com.agent-relay-auto.runner"


class RunnerControlError(RuntimeError):
    pass


class RunnerController:
    def __init__(
        self,
        registry_path: Path,
        plist_path: Path,
        uid: int | None = None,
        run_command=None,
    ):
        self.registry = ProjectRegistry(registry_path)
        self.plist_path = Path(plist_path).expanduser().resolve()
        self.uid = os.getuid() if uid is None else uid
        self.run_command = run_command or subprocess.run

    @property
    def domain(self) -> str:
        return f"gui/{self.uid}"

    @property
    def service(self) -> str:
        return f"{self.domain}/{LABEL}"

    def _run(self, *arguments: str):
        return self.run_command(
            ("launchctl", *arguments),
            capture_output=True,
            text=True,
            check=False,
        )

    def status(self, repo: Path) -> dict[str, object]:
        repo = Path(repo).resolve()
        try:
            roles = load_agent_policy(repo)
            configuration = "complete"
            problem = None
        except AdapterConfigurationError as error:
            roles = {}
            configuration = "incomplete"
            problem = str(error)
        service = self._run("print", self.service)
        state_match = re.search(r"^\s*state = (.+)$", service.stdout, re.MULTILINE)
        active_match = re.search(r"^\s*active count = (\d+)$", service.stdout, re.MULTILINE)
        exit_match = re.search(r"^\s*last exit code = (-?\d+)$", service.stdout, re.MULTILINE)
        service_state = state_match.group(1).strip() if state_match else None
        active_count = int(active_match.group(1)) if active_match else None
        last_exit_code = int(exit_match.group(1)) if exit_match else None
        if service.returncode != 0:
            runner_status = "not-loaded"
        elif service_state == "running" and (active_count is None or active_count > 0):
            runner_status = "running"
        elif last_exit_code not in {None, 0} or service_state == "spawn scheduled":
            runner_status = "failed"
        else:
            runner_status = "loaded"
        project_status = "blocked" if configuration == "incomplete" else runner_status
        return {
            "status": project_status,
            "service_status": runner_status,
            "repo": str(repo),
            "configuration": configuration,
            "configuration_error": problem,
            "roles": {role: item.agent for role, item in roles.items()},
            "service_state": service_state,
            "active_count": active_count,
            "last_exit_code": last_exit_code,
            "stderr_log": str(self.plist_path.parent.parent / "Logs/AgentRelay/runner.error.log"),
        }

    def start(self, repo: Path) -> dict[str, object]:
        repo = Path(repo).resolve()
        try:
            roles = load_agent_policy(repo)
        except AdapterConfigurationError as error:
            raise RunnerControlError(str(error)) from error
        if not self.plist_path.is_file():
            raise RunnerControlError(f"Runner service is not installed: missing {self.plist_path}")
        self.registry.register(repo)
        current = self._run("print", self.service)
        if current.returncode != 0:
            loaded = self._run("bootstrap", self.domain, str(self.plist_path))
            if loaded.returncode != 0:
                raise RunnerControlError(loaded.stderr.strip() or "launchctl bootstrap failed")
        started = self._run("kickstart", "-k", self.service)
        if started.returncode != 0:
            raise RunnerControlError(started.stderr.strip() or "launchctl kickstart failed")
        health = self.status(repo)
        if health["status"] != "running":
            raise RunnerControlError(
                "Runner failed after startup "
                f"(status={health['status']}, service_state={health['service_state']}, "
                f"last_exit_code={health['last_exit_code']}); inspect {health['stderr_log']}"
            )
        return {
            "status": "started",
            "repo": str(repo),
            "roles": {role: item.agent for role, item in roles.items()},
        }

    def stop(self) -> dict[str, object]:
        stopped = self._run("bootout", self.domain, str(self.plist_path))
        if stopped.returncode != 0 and "Could not find service" not in stopped.stderr:
            raise RunnerControlError(stopped.stderr.strip() or "launchctl bootout failed")
        return {"status": "stopped"}

    def restart(self, repo: Path) -> dict[str, object]:
        current = self._run("print", self.service)
        if current.returncode != 0:
            return self.start(repo)
        load_agent_policy(Path(repo).resolve())
        self.registry.register(repo)
        restarted = self._run("kickstart", "-k", self.service)
        if restarted.returncode != 0:
            raise RunnerControlError(restarted.stderr.strip() or "launchctl kickstart failed")
        return {"status": "restarted", "repo": str(Path(repo).resolve())}


def command_status(repo: Path, dry_run: bool = False) -> dict[str, object]:
    if dry_run:
        return {"status": "dry-run", "actions": [f"inspect runner for {Path(repo).resolve()}"]}
    home = Path.home()
    controller = RunnerController(
        home / ".config/agent-relay-auto/projects.json",
        home / "Library/LaunchAgents/com.agent-relay-auto.runner.plist",
    )
    return controller.status(repo)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "start", "stop", "restart", "logs"))
    parser.add_argument("--repo", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    if args.dry_run:
        result = {"status": "dry-run", "actions": [f"{args.command} runner for {repo.resolve()}"]}
    else:
        home = Path.home()
        controller = RunnerController(
            home / ".config/agent-relay-auto/projects.json",
            home / "Library/LaunchAgents/com.agent-relay-auto.runner.plist",
        )
        try:
            if args.command == "status":
                result = controller.status(repo)
            elif args.command == "start":
                result = controller.start(repo)
            elif args.command == "stop":
                result = controller.stop()
            elif args.command == "restart":
                result = controller.restart(repo)
            else:
                result = {
                    "status": "available",
                    "stdout": str(home / "Library/Logs/AgentRelay/runner.log"),
                    "stderr": str(home / "Library/Logs/AgentRelay/runner.error.log"),
                }
        except (RunnerControlError, AdapterConfigurationError) as error:
            print(f"Agent Relay Auto Runner error: {error}", file=sys.stderr)
            return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
