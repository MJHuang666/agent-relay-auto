"""Validated Runner policy and immutable per-task configuration snapshots."""

from __future__ import annotations

from dataclasses import dataclass
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
class RuntimeConfig:
    policy: AutomationPolicy
    cost: CostControl

    @classmethod
    def defaults(cls) -> "RuntimeConfig":
        return cls(AutomationPolicy(), CostControl())

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
        }
