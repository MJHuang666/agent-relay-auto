#!/usr/bin/env python3
"""Non-secret project initialization and role/model configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


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
    def __init__(self, repo: Path):
        self.repo = Path(repo).resolve()

    def inspect_existing(self) -> dict[str, object]:
        policy = self.repo / "docs/agent/automation-policy.yaml"
        local = self.repo / ".agent-relay/local.yaml"
        roles = {"planner": {}, "implementer": {}, "reviewer": {}}
        if policy.is_file():
            text = policy.read_text(encoding="utf-8")
            for role in roles:
                marker = f"  {role}:"
                if marker in text:
                    roles[role] = {"configured": True}
        return {"exists": policy.is_file() or local.is_file(), "roles": roles, "policy": str(policy), "local": str(local)}

    def discover_options(self, tool_id: str) -> dict[str, object]:
        return {"tool": tool_id, "models": [], "validation_status": "pending"}

    def apply(self, answers: Mapping[str, object]) -> dict[str, object]:
        _assert_no_secrets(answers)
        language = str(answers.get("language", "en-US"))
        if language not in {"zh-CN", "en-US"}:
            raise ConfigurationError("language must be zh-CN or en-US")
        roles = answers.get("roles")
        if not isinstance(roles, Mapping) or set(roles) != {"planner", "implementer", "reviewer"}:
            raise ConfigurationError("planner, implementer, and reviewer configurations are required")
        automation_mode = "automatic" if answers.get("runner_confirmed") is True else "manual"
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
            f"cost_mode: {answers.get('cost_mode', 'balanced')}",
            "roles:",
        ]
        for role in ("planner", "implementer", "reviewer"):
            role_config = roles[role]
            if not isinstance(role_config, Mapping):
                raise ConfigurationError(f"invalid role configuration: {role}")
            lines.extend(
                [
                    f"  {role}:",
                    f"    agent: {role_config.get('agent', '')}",
                    f"    model: {role_config.get('model', '')}",
                    f"    reasoning: {role_config.get('reasoning', 'medium')}",
                ]
            )
        policy_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        local_path = self.repo / ".agent-relay/local.yaml"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(f"mode: {automation_mode}\nlanguage: {language}\n", encoding="utf-8")
        return {"mode": automation_mode, "language": language, "policy": str(policy_path), "local": str(local_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    print(json.dumps(RuntimeConfigurator(Path(args.repo)).inspect_existing(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
