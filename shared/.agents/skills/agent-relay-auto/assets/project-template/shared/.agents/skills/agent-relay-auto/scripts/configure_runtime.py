#!/usr/bin/env python3
"""Non-secret project initialization and role/model configuration."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from agent_relay_runtime.adapters.factory import (  # noqa: E402
    AdapterConfigurationError,
    load_agent_policy,
)
from agent_relay_runtime.adapters.claude_code import ClaudeCodeAdapter  # noqa: E402
from agent_relay_runtime.adapters.codex import CodexAdapter  # noqa: E402
from agent_relay_runtime.adapters.opencode import OpenCodeAdapter  # noqa: E402
from agent_relay_runtime.planner_channel import (  # noqa: E402
    PlannerChannel,
    PlannerChannelError,
    PlannerChannelStore,
)


class ConfigurationError(ValueError):
    pass


_SECRET_WORDS = ("token", "secret", "password", "api_key", "apikey", "cookie")


def _assert_no_secrets(value: object, path: str = "answers") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(word in key_text for word in _SECRET_WORDS):
                raise ConfigurationError(f"secret field is not allowed in project config: {path}.{key}")
            _assert_no_secrets(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_secrets(item, f"{path}[{index}]")


class RuntimeConfigurator:
    def __init__(self, repo: Path, adapter_builders=None):
        self.repo = Path(repo).resolve()
        self.adapter_builders = (
            {
                "codex": CodexAdapter,
                "opencode": OpenCodeAdapter,
                "claude-code": ClaudeCodeAdapter,
            }
            if adapter_builders is None
            else dict(adapter_builders)
        )

    def inspect_existing(self) -> dict[str, object]:
        policy = self.repo / "docs/agent/automation-policy.yaml"
        local = self.repo / ".agent-relay-auto/local.yaml"
        roles = {"planner": {}, "implementer": {}, "reviewer": {}}
        problems = []
        mode = "missing"
        if policy.is_file():
            for line in policy.read_text(encoding="utf-8").splitlines():
                if line.startswith("mode:"):
                    mode = line.split(":", 1)[1].strip()
                    break
            try:
                configured = load_agent_policy(self.repo, require_automatic=False)
                roles = {
                    role: {
                        "participant_id": item.participant_id,
                        "agent": item.agent,
                        "model": item.model,
                        "reasoning": item.reasoning,
                        "validation_status": item.validation_status,
                        "execution_mode": item.execution_mode,
                    }
                    for role, item in configured.items()
                }
            except AdapterConfigurationError as error:
                problems.append(str(error))
        channel = None
        try:
            channel = PlannerChannelStore(self.repo).load()
        except PlannerChannelError as error:
            problems.append(str(error))
        reporting: dict[str, object]
        if channel is None:
            reporting = {
                "registered": False,
                "action": "register_planner_channel",
                "instruction": "Run $agent-relay-auto continue in the intended Planner conversation.",
                "poll_interval_seconds": 45,
            }
        else:
            suffix = channel.conversation_id[-6:]
            capabilities = {
                "codex": ("verified", "verified", "experimental"),
                "opencode": ("verified", "verified", "verified"),
                "claude-code": ("verified", "verified", "verified"),
                "deepseek-harness": ("static_only", "static_only", "experimental"),
            }[channel.tool]
            reporting = {
                "registered": True,
                "tool": channel.tool,
                "participant_id": channel.participant_id,
                "conversation_id_masked": f"***{suffix}",
                "project_path": channel.project_path,
                "resume_original_conversation": capabilities[0],
                "submit_turn": capabilities[1],
                "reopen_original_ui": capabilities[2],
                "poll_interval_seconds": 45,
                "model_retry_limit": 1,
                "presentation_retry_limit": 3,
            }
        complete = policy.is_file() and not problems
        return {
            "exists": policy.is_file() or local.is_file(),
            "complete": complete,
            "mode": mode,
            "ready_to_start": complete and mode == "automatic" and channel is not None,
            "roles": roles,
            "problems": problems,
            "policy": str(policy),
            "local": str(local),
            "reporting": reporting,
        }

    def discover_options(self, tool_id: str) -> dict[str, object]:
        reasoning_key = {
            "codex": "reasoning_effort",
            "opencode": "variant",
            "claude-code": "effort",
        }.get(tool_id)
        builder = self.adapter_builders.get(tool_id)
        if builder is None:
            return {
                "tool": tool_id,
                "automatic_supported": False,
                "models": [],
                "reasoning_key": reasoning_key,
                "validation_status": "manual-only",
            }
        adapter = builder()
        capabilities = adapter.capabilities()
        models = []
        status = "pending"
        if capabilities.model_discovery and hasattr(adapter, "list_models"):
            try:
                for option in adapter.list_models():
                    model_id = getattr(option, "model_id", str(option))
                    display_name = getattr(option, "display_name", model_id)
                    models.append({"id": model_id, "name": display_name})
                status = "verified" if models else "pending"
            except Exception as error:  # discovery failure remains visible and permits a stable manual ID
                return {
                    "tool": tool_id,
                    "automatic_supported": capabilities.noninteractive,
                    "models": [],
                    "reasoning_key": reasoning_key,
                    "validation_status": "pending",
                    "discovery_error": str(error),
                }
        return {
            "tool": tool_id,
            "automatic_supported": capabilities.noninteractive,
            "models": models,
            "reasoning_key": reasoning_key,
            "validation_status": status,
        }

    def apply(self, answers: Mapping[str, object]) -> dict[str, object]:
        _assert_no_secrets(answers)
        language = str(answers.get("language", "en-US"))
        if language not in {"zh-CN", "en-US"}:
            raise ConfigurationError("language must be zh-CN or en-US")
        roles = answers.get("roles")
        if not isinstance(roles, Mapping) or set(roles) != {"planner", "implementer", "reviewer"}:
            raise ConfigurationError("planner, implementer, and reviewer configurations are required")
        automation_mode = "automatic" if answers.get("runner_confirmed") is True else "manual"
        normalized_roles = {}
        for role in ("planner", "implementer", "reviewer"):
            role_config = roles[role]
            if not isinstance(role_config, Mapping):
                raise ConfigurationError(f"invalid role configuration: {role}")
            agent = str(role_config.get("agent", "")).strip()
            model = str(role_config.get("model", "")).strip()
            participant_id = str(role_config.get("participant_id", "")).strip()
            reasoning = str(role_config.get("reasoning", "medium")).strip()
            execution_mode = "foreground" if role == "planner" else "background"
            if automation_mode == "automatic":
                if not participant_id:
                    raise ConfigurationError(f"{role}.participant_id is required before Runner installation")
                if execution_mode == "background" and agent not in {"codex", "opencode", "claude-code"}:
                    raise ConfigurationError(f"{role}.agent does not support automatic execution: {agent or 'missing'}")
                if not model or model == "default" or model.startswith("<"):
                    raise ConfigurationError(f"{role}.model must be explicitly selected before Runner installation")
                if not reasoning or reasoning.startswith("<"):
                    raise ConfigurationError(f"{role}.reasoning must be explicitly selected before Runner installation")
            normalized_roles[role] = {
                "participant_id": participant_id,
                "agent": agent,
                "model": model,
                "reasoning": reasoning,
                "validation_status": str(role_config.get("validation_status", "pending")),
                "execution_mode": execution_mode,
            }
        channel_answers = answers.get("planner_channel")
        prepared_channel = None
        if channel_answers is not None:
            if not isinstance(channel_answers, Mapping):
                raise ConfigurationError("planner_channel must be an object")
            planner = normalized_roles["planner"]
            try:
                prepared_channel = PlannerChannel(
                    participant_id=str(planner["participant_id"]),
                    tool=str(channel_answers.get("tool", planner["agent"])),
                    conversation_id=str(channel_answers.get("conversation_id", "")).strip(),
                    project_path=str(self.repo),
                    registered_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                )
            except PlannerChannelError as error:
                raise ConfigurationError(str(error)) from error
            if prepared_channel.tool != planner["agent"]:
                raise ConfigurationError("planner_channel.tool must match planner.agent")
        policy_path = self.repo / "docs/agent/automation-policy.yaml"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"language: {language}",
            f"mode: {automation_mode}",
            "automation:",
            "  max_rework_rounds: 3",
            "  max_auto_replans: 1",
            "  max_agent_retries: 1",
            f"  allow_same_role_fallback: {str(bool(answers.get('allow_same_role_fallback', False))).lower()}",
            "cost_control:",
            f"  mode: {answers.get('cost_mode', 'balanced')}",
            "  warn_after_agent_runs: 8",
            "  stop_after_agent_runs: 12",
            "  require_confirmation_after_warning: false",
            "  record_provider_usage: true",
            "runtime:",
            "  agent_timeout_minutes: 30",
            "  heartbeat_interval_seconds: 10",
            "  heartbeat_stale_seconds: 45",
            "  interrupt_grace_seconds: 30",
            "reporting:",
            "  enabled: true",
            "  poll_interval_seconds: 45",
            "  reopen_original_conversation: true",
            "  launch_application_if_closed: true",
            "  require_same_conversation: true",
            "  model_retry_limit: 1",
            "  presentation_retry_limit: 3",
            "  presentation_retry_interval_seconds: 10",
            "roles:",
        ]
        for role in ("planner", "implementer", "reviewer"):
            role_config = normalized_roles[role]
            reasoning_key = {
                "codex": "reasoning_effort",
                "opencode": "variant",
                "claude-code": "effort",
            }.get(role_config["agent"], "reasoning")
            lines.extend(
                [
                    f"  {role}:",
                    f"    execution_mode: {role_config['execution_mode']}",
                    f"    participant_id: {role_config['participant_id']}",
                    f"    agent: {role_config['agent']}",
                    f"    model: {role_config['model']}",
                    f"    {reasoning_key}: {role_config['reasoning']}",
                    f"    validation_status: {role_config['validation_status']}",
                ]
            )
        policy_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        local_path = self.repo / ".agent-relay-auto/local.yaml"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(f"mode: {automation_mode}\nlanguage: {language}\n", encoding="utf-8")
        channel_registered = False
        if prepared_channel is not None:
            PlannerChannelStore(self.repo).save(prepared_channel)
            channel_registered = True
        return {
            "mode": automation_mode,
            "language": language,
            "policy": str(policy_path),
            "local": str(local_path),
            "planner_channel_registered": channel_registered,
            "next_action": None if channel_registered or automation_mode != "automatic" else "register_planner_channel",
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("inspect", "discover", "apply"), default="inspect")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--answers-json")
    parser.add_argument("--tool")
    args = parser.parse_args(argv)
    configurator = RuntimeConfigurator(Path(args.repo))
    if args.command == "apply":
        if not args.answers_json:
            parser.error("apply requires --answers-json")
        answers_source = Path(args.answers_json)
        answers = json.loads(
            answers_source.read_text(encoding="utf-8") if answers_source.is_file() else args.answers_json
        )
        result = configurator.apply(answers)
    elif args.command == "discover":
        if not args.tool:
            parser.error("discover requires --tool")
        result = configurator.discover_options(args.tool)
    else:
        result = configurator.inspect_existing()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
