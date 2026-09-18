"""Build project adapters from the repository's validated role policy."""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping


class AdapterConfigurationError(ValueError):
    """Raised when a project cannot produce a safe automatic adapter."""


def _load_sibling(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"agent_relay_adapter_factory_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load adapter module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from .base import AdapterCapabilities, LaunchRequest
    from .claude_code import ClaudeCodeAdapter
    from .codex import CodexAdapter
    from .opencode import OpenCodeAdapter
except ImportError:
    _base = _load_sibling("base")
    AdapterCapabilities = _base.AdapterCapabilities
    LaunchRequest = _base.LaunchRequest
    ClaudeCodeAdapter = _load_sibling("claude_code").ClaudeCodeAdapter
    CodexAdapter = _load_sibling("codex").CodexAdapter
    OpenCodeAdapter = _load_sibling("opencode").OpenCodeAdapter


_ROLE_NAMES = ("planner", "implementer", "reviewer")
_KEY_VALUE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_-]+):(?:\s*(?P<value>.*))?$")
_REASONING_KEYS = {
    "codex": "reasoning_effort",
    "opencode": "variant",
    "claude-code": "effort",
}


@dataclass(frozen=True)
class RoleAdapterConfiguration:
    role: str
    participant_id: str
    agent: str
    model: str
    reasoning: str
    validation_status: str


def _scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_policy(path: Path) -> tuple[str, dict[str, dict[str, str]]]:
    mode = ""
    roles: dict[str, dict[str, str]] = {}
    in_roles = False
    current_role: str | None = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _KEY_VALUE.match(raw)
        if match is None:
            raise AdapterConfigurationError(f"{path}: unsupported YAML at line {line_number}: {raw}")
        indent = len(match.group("indent"))
        key = match.group("key")
        value = _scalar(match.group("value") or "")
        if indent == 0:
            current_role = None
            in_roles = key == "roles" and value == ""
            if key == "mode":
                mode = value
            continue
        if not in_roles:
            continue
        if indent == 2 and value == "":
            current_role = key
            roles.setdefault(key, {})
            continue
        if indent == 4 and current_role is not None:
            roles[current_role][key] = value
            continue
        raise AdapterConfigurationError(f"{path}: unsupported roles YAML at line {line_number}: {raw}")
    return mode, roles


def load_agent_policy(repo: Path, require_automatic: bool = True) -> dict[str, RoleAdapterConfiguration]:
    repo = Path(repo).resolve()
    path = repo / "docs/agent/automation-policy.yaml"
    if not path.is_file():
        raise AdapterConfigurationError(f"{repo}: missing {path.relative_to(repo)}")
    mode, raw_roles = _parse_policy(path)
    if require_automatic and mode != "automatic":
        raise AdapterConfigurationError(f"{repo}: automation-policy.yaml mode must be automatic, found {mode or 'missing'}")
    result: dict[str, RoleAdapterConfiguration] = {}
    for role in _ROLE_NAMES:
        values = raw_roles.get(role)
        if values is None:
            raise AdapterConfigurationError(f"{repo}: role {role} is missing from automation-policy.yaml")
        agent = values.get("agent", "")
        reasoning_key = _REASONING_KEYS.get(agent)
        if reasoning_key is None:
            raise AdapterConfigurationError(f"{repo}: role {role} uses unsupported automatic agent {agent or 'missing'}")
        required = {
            "participant_id": values.get("participant_id", ""),
            "model": values.get("model", ""),
            reasoning_key: values.get(reasoning_key, ""),
        }
        for field, value in required.items():
            if not value or value == "default" or value.startswith("<"):
                raise AdapterConfigurationError(f"{repo}: role {role} requires an explicit {field}")
        result[role] = RoleAdapterConfiguration(
            role=role,
            participant_id=required["participant_id"],
            agent=agent,
            model=required["model"],
            reasoning=required[reasoning_key],
            validation_status=values.get("validation_status", "pending"),
        )
    return result


class RoleRoutingAdapter:
    """Route each launch request to the adapter configured for its role."""

    def __init__(self, repo: Path, roles: Mapping[str, RoleAdapterConfiguration], adapters: Mapping[str, object]):
        self.repo = Path(repo).resolve()
        self.roles = dict(roles)
        self.adapters = dict(adapters)

    def _resolved(self, request: LaunchRequest):
        config = self.roles.get(request.role)
        if config is None:
            raise AdapterConfigurationError(f"{self.repo}: request uses unconfigured role {request.role}")
        if request.participant_id != config.participant_id:
            raise AdapterConfigurationError(
                f"{self.repo}: role {request.role} expects participant {config.participant_id}, found {request.participant_id}"
            )
        adapter = self.adapters[config.agent]
        configured = replace(request, model=config.model, reasoning=config.reasoning)
        return adapter, configured

    def capabilities(self) -> AdapterCapabilities:
        capabilities = [adapter.capabilities() for adapter in self.adapters.values()]
        return AdapterCapabilities(
            noninteractive=all(item.noninteractive for item in capabilities),
            model_discovery=all(item.model_discovery for item in capabilities),
            native_resume=all(item.native_resume for item in capabilities),
            structured_usage=all(item.structured_usage for item in capabilities),
            graceful_interrupt=all(item.graceful_interrupt for item in capabilities),
        )

    def capabilities_for(self, request: LaunchRequest) -> AdapterCapabilities:
        adapter, _ = self._resolved(request)
        return adapter.capabilities()

    def build_command(self, request: LaunchRequest) -> tuple[str, ...]:
        adapter, configured = self._resolved(request)
        return adapter.build_command(configured)

    def resume_command(self, request: LaunchRequest, session_id: str) -> tuple[str, ...]:
        adapter, configured = self._resolved(request)
        resume = getattr(adapter, "resume_command", None)
        if resume is None:
            raise AdapterConfigurationError(f"{self.repo}: role {request.role} adapter does not support resume")
        return resume(configured, session_id)


def create_adapter_factory(
    builders: Mapping[str, Callable[[], object]] | None = None,
) -> Callable[[Path], RoleRoutingAdapter]:
    configured_builders = dict(
        builders
        or {
            "codex": CodexAdapter,
            "opencode": OpenCodeAdapter,
            "claude-code": ClaudeCodeAdapter,
        }
    )

    def build(repo: Path) -> RoleRoutingAdapter:
        roles = load_agent_policy(repo)
        agents = {config.agent for config in roles.values()}
        missing = sorted(agents.difference(configured_builders))
        if missing:
            raise AdapterConfigurationError(f"{Path(repo).resolve()}: no adapter builder for {', '.join(missing)}")
        adapters = {agent: configured_builders[agent]() for agent in agents}
        return RoleRoutingAdapter(repo, roles, adapters)

    return build
