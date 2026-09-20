"""Validated Runner policy and immutable per-task configuration snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AutomationPolicy:
    max_rework_rounds: int = 3
    max_auto_replans: int = 1
    max_agent_retries: int = 1
    allow_same_role_fallback: bool = False

    def __post_init__(self):
        for field in ("max_rework_rounds", "max_auto_replans", "max_agent_retries"):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ConfigError(f"{field} must be a non-negative integer")


@dataclass(frozen=True)
class CostControl:
    mode: str = "balanced"
    warn_after_agent_runs: int = 8
    stop_after_agent_runs: int = 12
    require_confirmation_after_warning: bool = False
    record_provider_usage: bool = True

    def __post_init__(self):
        if self.mode not in {"economy", "balanced", "quality", "custom"}:
            raise ConfigError(f"unsupported cost mode: {self.mode}")
        for field in ("warn_after_agent_runs", "stop_after_agent_runs"):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ConfigError(f"{field} must be a positive integer")
        if self.stop_after_agent_runs < self.warn_after_agent_runs:
            raise ConfigError("stop_after_agent_runs must be >= warn_after_agent_runs")


@dataclass(frozen=True)
class RuntimeLimits:
    agent_timeout_minutes: float = 30
    heartbeat_interval_seconds: float = 10
    heartbeat_stale_seconds: float = 45
    interrupt_grace_seconds: float = 30

    def __post_init__(self):
        for name in (
            "agent_timeout_minutes",
            "heartbeat_interval_seconds",
            "heartbeat_stale_seconds",
            "interrupt_grace_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ConfigError(f"{name} must be a positive number")
        if self.heartbeat_stale_seconds <= self.heartbeat_interval_seconds:
            raise ConfigError("heartbeat_stale_seconds must be greater than heartbeat_interval_seconds")


@dataclass(frozen=True)
class ReportingPolicy:
    enabled: bool = True
    poll_interval_seconds: float = 45
    reopen_original_conversation: bool = True
    launch_application_if_closed: bool = True
    require_same_conversation: bool = True
    model_retry_limit: int = 1
    presentation_retry_limit: int = 3
    presentation_retry_interval_seconds: float = 10

    def __post_init__(self):
        for name in ("poll_interval_seconds", "presentation_retry_interval_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ConfigError(f"{name} must be a positive number")
        for name in ("model_retry_limit", "presentation_retry_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConfigError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class RuntimeConfig:
    policy: AutomationPolicy
    cost: CostControl
    limits: RuntimeLimits = field(default_factory=RuntimeLimits)
    reporting: ReportingPolicy = field(default_factory=ReportingPolicy)

    @classmethod
    def defaults(cls) -> "RuntimeConfig":
        return cls(AutomationPolicy(), CostControl(), RuntimeLimits(), ReportingPolicy())

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy": {
                "max_rework_rounds": self.policy.max_rework_rounds,
                "max_auto_replans": self.policy.max_auto_replans,
                "max_agent_retries": self.policy.max_agent_retries,
                "allow_same_role_fallback": self.policy.allow_same_role_fallback,
            },
            "cost": {
                "mode": self.cost.mode,
                "warn_after_agent_runs": self.cost.warn_after_agent_runs,
                "stop_after_agent_runs": self.cost.stop_after_agent_runs,
                "require_confirmation_after_warning": self.cost.require_confirmation_after_warning,
                "record_provider_usage": self.cost.record_provider_usage,
            },
            "limits": {
                "agent_timeout_minutes": self.limits.agent_timeout_minutes,
                "heartbeat_interval_seconds": self.limits.heartbeat_interval_seconds,
                "heartbeat_stale_seconds": self.limits.heartbeat_stale_seconds,
                "interrupt_grace_seconds": self.limits.interrupt_grace_seconds,
            },
            "reporting": {
                "enabled": self.reporting.enabled,
                "poll_interval_seconds": self.reporting.poll_interval_seconds,
                "reopen_original_conversation": self.reporting.reopen_original_conversation,
                "launch_application_if_closed": self.reporting.launch_application_if_closed,
                "require_same_conversation": self.reporting.require_same_conversation,
                "model_retry_limit": self.reporting.model_retry_limit,
                "presentation_retry_limit": self.reporting.presentation_retry_limit,
                "presentation_retry_interval_seconds": self.reporting.presentation_retry_interval_seconds,
            },
        }


def _policy_sections(path: Path) -> dict[str, dict[str, object]]:
    sections: dict[str, dict[str, object]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, separator, value = raw.strip().partition(":")
        if not separator:
            continue
        if indent == 0:
            current = key if not value.strip() else None
            if current:
                sections.setdefault(current, {})
            continue
        if indent != 2 or current not in {"automation", "cost_control", "runtime", "reporting"}:
            continue
        scalar: object = value.strip()
        if scalar in {"true", "false"}:
            scalar = scalar == "true"
        else:
            try:
                scalar = float(str(scalar)) if "." in str(scalar) else int(str(scalar))
            except ValueError:
                pass
        sections[current][key] = scalar
    return sections


def load_runtime_config(repo: Path) -> RuntimeConfig:
    path = Path(repo) / "docs/agent/automation-policy.yaml"
    if not path.is_file():
        return RuntimeConfig.defaults()
    sections = _policy_sections(path)
    return RuntimeConfig(
        AutomationPolicy(**sections.get("automation", {})),
        CostControl(**sections.get("cost_control", {})),
        RuntimeLimits(**sections.get("runtime", {})),
        ReportingPolicy(**sections.get("reporting", {})),
    )
